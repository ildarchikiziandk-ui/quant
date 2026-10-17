"""Рекомендательная модель ленты «Рекомендации».

Как это работает:
1. Профиль интересов. Из действий пользователя (лайки, реакции, киты, комментарии, закладки,
   репосты) собираются веса авторов, хэштегов и слов, причём свежие действия весят больше.
   «Не интересно» и скрытые авторы дают отрицательный вес.
2. Кандидаты. Посты за последние 3 недели, которые пользователь может видеть.
3. Оценка поста = релевантность (похожесть на интересы) + качество (вовлечённость относительно
   возраста) + свежесть + немного «исследования» нового. Просмотренные, уже лайкнутые и
   «неинтересные» посты штрафуются.
4. Разнообразие. Финальный список собирается так, чтобы один автор или одна тема не шли подряд.

Всё считается за один проход по SQL без тяжёлых библиотек; профиль кэшируется на минуту.
"""
import math
import re
import time
import zlib
from datetime import datetime, timedelta

import models
from services import prefs
from services.text import extract_hashtags

_STOP = set("""это этот эта эти что как так вот уже еще ещё или для при без над под про все всё всех когда тоже только
очень просто было были будет есть нет ну да мне меня тебя тебе тебя него неё нее они она оно мы вы ты мой моя мои твой
свой своя наш ваш кто где куда зачем почему чтобы потом сейчас сегодня вчера завтра здесь там тут даже если чем""".split())
_WORD = re.compile(r"[а-яёa-z]{4,}", re.I)

# вес сигнала: насколько действие говорит об интересе
W_LIKE, W_REACT, W_WHALE, W_COMMENT, W_BOOKMARK, W_REPOST, W_NOT = 1.0, 1.0, 1.5, 2.0, 3.0, 3.0, -4.0
HALF_LIFE_DAYS = 30
_cache = {}


def tokens(text):
    out = set()
    for w in _WORD.findall((text or "").lower().replace("ё", "е")):
        if w not in _STOP:
            out.add(w[:6])  # грубый стемминг: «котики», «котиков» → «котики»/«котико» ≈ одна основа
    return out


def _norm(d):
    s = math.sqrt(sum(v * v for v in d.values() if v > 0)) or 1.0
    return {k: v / s for k, v in d.items()}


def interest_profile(db, user):
    """{'authors': {...}, 'tags': {...}, 'tokens': {...}, 'media': x, 'n': число сигналов}"""
    hit = _cache.get(user.id)
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    signals = []  # (post_id, weight)
    for model, w, lim in ((models.Like, W_LIKE, 300), (models.Reaction, W_REACT, 200), (models.Whale, W_WHALE, 100),
                          (models.Bookmark, W_BOOKMARK, 200)):
        signals += [(r.post_id, w) for r in db.query(model.post_id).filter(model.user_id == user.id).order_by(model.id.desc()).limit(lim)]
    signals += [(r.post_id, W_COMMENT) for r in db.query(models.Comment.post_id).filter(models.Comment.user_id == user.id)
                .order_by(models.Comment.id.desc()).limit(200)]
    signals += [(r.repost_id, W_REPOST) for r in db.query(models.Post.repost_id).filter(models.Post.user_id == user.id,
                models.Post.is_repost == True).order_by(models.Post.id.desc()).limit(100)]
    nots = db.query(models.NotInterested).filter_by(user_id=user.id).order_by(models.NotInterested.id.desc()).limit(200).all()
    signals += [(n.post_id, W_NOT) for n in nots]
    ids = {pid for pid, _ in signals if pid}
    posts = {p.id: p for p in db.query(models.Post.id, models.Post.user_id, models.Post.content, models.Post.image,
                                       models.Post.created_at).filter(models.Post.id.in_(ids or {-1}))}
    now = datetime.utcnow()
    authors, tags, toks, media = {}, {}, {}, 0.0
    for pid, w in signals:
        p = posts.get(pid)
        if not p or p.user_id == user.id:
            continue
        age = max(0.0, (now - (p.created_at or now)).total_seconds() / 86400)
        w *= 0.5 ** (age / HALF_LIFE_DAYS)
        authors[p.user_id] = authors.get(p.user_id, 0) + w
        for t in extract_hashtags(p.content):
            tags[t] = tags.get(t, 0) + w
        for t in tokens(p.content):
            toks[t] = toks.get(t, 0) + w * 0.5
        media += w if p.image else -w * 0.3
    for n in nots:
        authors[n.author_id] = authors.get(n.author_id, 0) + W_NOT * 0.5
    for t in db.query(models.HashtagFollow.tag).filter_by(user_id=user.id).limit(100):
        tags[t.tag] = tags.get(t.tag, 0) + 4.0
    for t in _user_interests(user):
        tags[t] = tags.get(t, 0) + 1.5
    total = sum(1 for _, w in signals if w > 0) + len(tags)
    prof = {"authors": _norm(authors), "tags": _norm(tags), "tokens": _norm(toks), "media": max(-1.0, min(1.0, media / (total or 1))),
            "n": total, "not_posts": {n.post_id for n in nots}, "not_authors": {n.author_id for n in nots}}
    _cache[user.id] = (time.time(), prof)
    return prof


def _user_interests(user):
    from services.extras import interests
    return interests(user)


def invalidate(user_id):
    _cache.pop(user_id, None)


def _noise(user_id, post_id):
    return (zlib.crc32(f"{user_id}:{post_id}:{datetime.utcnow():%Y%m%d}".encode()) % 1000) / 1000


FRESH = {"fresh": (1.0, 0.25), "normal": (0.6, 0.45), "popular": (0.3, 0.8)}
EXPLORE = {"low": 0.05, "normal": 0.18, "high": 0.4}


def rank(db, user, pool, fids):
    """Возвращает [(post, score, reason)] по убыванию интереса."""
    now = datetime.utcnow()
    prof = interest_profile(db, user) if user else None
    w_fresh, w_quality = FRESH[prefs.get(user, "rec_freshness")] if user else FRESH["normal"]
    explore = EXPLORE[prefs.get(user, "rec_explore")] if user else 0.15
    seen, liked = {}, set()
    if user:
        ids = [p.id for p in pool]
        if prefs.get(user, "rec_hide_seen"):
            cutoff = now - timedelta(minutes=30)  # только что показанное не штрафуем — иначе поедет пагинация
            for s in db.query(models.SeenPost.post_id, models.SeenPost.created_at).filter(
                    models.SeenPost.user_id == user.id, models.SeenPost.post_id.in_(ids or [-1])):
                if s.created_at < cutoff:
                    seen[s.post_id] = seen.get(s.post_id, 0) + 1
        liked = {r.post_id for r in db.query(models.Like.post_id).filter(models.Like.user_id == user.id, models.Like.post_id.in_(ids or [-1]))}
    eng = {p.id: len(p.likes) * 1 + len(p.comments) * 2 + len(p.whales) * 1.5 + len(p.reactions) + (p.views or 0) * 0.02 for p in pool}
    max_q = max([math.log1p(e) for e in eng.values()] + [1.0])
    out = []
    for p in pool:
        age_h = max(0.1, (now - p.created_at).total_seconds() / 3600)
        quality = math.log1p(eng[p.id]) / max_q / (1 + age_h / 72) ** 0.5
        fresh = 1 / (1 + age_h / 18) ** 0.7
        rel, reason = 0.0, ""
        if prof and prof["n"]:
            a = prof["authors"].get(p.user_id, 0)
            ptags = extract_hashtags(p.content)
            t = sum(prof["tags"].get(x, 0) for x in ptags)
            ptoks = tokens(p.content)
            k = sum(prof["tokens"].get(x, 0) for x in ptoks) / math.sqrt(len(ptoks) or 1)
            m = prof["media"] * (0.15 if p.image else -0.05)
            rel = 1.6 * a + 1.2 * t + 0.8 * k + m
            if a > 0.25:
                reason = f"Вы часто оцениваете @{p.author.username}"
            elif t > 0.15:
                best = max(ptags, key=lambda x: prof["tags"].get(x, 0))
                reason = f"Вам нравится #{best}"
            elif k > 0.2:
                reason = "Похоже на то, что вам нравится"
        if p.user_id in fids:
            rel += 0.35
            reason = reason or "Из ваших подписок"
        score = rel + w_quality * quality + w_fresh * fresh + explore * _noise(user.id if user else 0, p.id)
        if not reason and quality > 0.6:
            reason = "Популярное сейчас"
        if prof:
            if p.id in prof["not_posts"]:
                continue
            if p.user_id in prof["not_authors"]:
                score *= 0.3
        if p.id in liked:
            score *= 0.25
        if seen.get(p.id):
            score *= 0.4 ** seen[p.id]
        out.append((p, score, reason))
    out.sort(key=lambda x: x[1], reverse=True)
    return diversify(out)


def diversify(ranked, window=4):
    """Жадно собирает ленту: штраф за автора/тему, которые только что были."""
    result, recent = [], []
    pool = list(ranked)
    while pool:
        best_i, best_s = 0, None
        for i, (p, s, _) in enumerate(pool[:30]):
            tags = extract_hashtags(p.content)
            pen = 1.0
            for q in recent:
                if q.user_id == p.user_id:
                    pen *= 0.55
                if tags & extract_hashtags(q.content):
                    pen *= 0.8
            if best_s is None or s * pen > best_s:
                best_i, best_s = i, s * pen
        item = pool.pop(best_i)
        result.append(item)
        recent = (recent + [item[0]])[-window:]
    return result


def mark_seen(db, user, posts):
    if not user or not posts:
        return
    now = datetime.utcnow()
    rows = [{"user_id": user.id, "post_id": p.id, "created_at": now} for p in posts]
    if rows:  # одним запросом, а не по строке на пост
        db.execute(models.SeenPost.__table__.insert(), rows)
    if zlib.crc32(str(time.time()).encode()) % 50 == 0:  # изредка чистим старое
        db.query(models.SeenPost).filter(models.SeenPost.created_at < datetime.utcnow() - timedelta(days=30)).delete(synchronize_session=False)
    db.commit()


def apply_filters(q, user):
    """Фильтры ленты из настроек (репосты, опросы, длинные, медиа)."""
    if not user:
        return q
    if prefs.get(user, "feed_hide_reposts"):
        q = q.filter(models.Post.is_repost == False)
    if prefs.get(user, "feed_hide_long"):
        q = q.filter(models.Post.is_long != True)
    if prefs.get(user, "feed_hide_media"):
        q = q.filter((models.Post.image == "") | (models.Post.image == None))
    if prefs.get(user, "feed_hide_polls"):
        q = q.filter(~models.Post.poll.has())
    if prefs.get(user, "feed_only_media"):
        q = q.filter(models.Post.image != "", models.Post.image != None)
    return q


def post_filter(db, user, posts):
    """Фильтры, которые проще проверить в Python: скрытые слова, уже лайкнутое, авторы, скрытые из поиска."""
    if not user:
        return posts
    words = prefs.muted_words(user)
    liked = set()
    if prefs.get(user, "feed_hide_liked"):
        liked = {r.post_id for r in db.query(models.Like.post_id).filter(models.Like.user_id == user.id,
                                                                         models.Like.post_id.in_([p.id for p in posts] or [-1]))}
    out = []
    for p in posts:
        text = ((p.content or "") + " " + (p.original_comment or "")).lower()
        if words and any(w in text for w in words):
            continue
        if p.id in liked:
            continue
        out.append(p)
    return out


def guests_hidden_filter(q, user):
    """Посты пользователей с настройкой «скрыть от гостей» не показываются без входа."""
    if user:
        return q
    hidden = [u.id for u in q.session.query(models.User.id, models.User.prefs).filter(models.User.prefs.like('%"guests_hidden": true%'))]
    return q.filter(~models.Post.user_id.in_(hidden)) if hidden else q

