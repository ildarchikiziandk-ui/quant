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
5. Люди (3.2): близость к тем, с кем вы переписываетесь, взаимно подписаны и чьи профили открываете;
   «похожие вкусы» — что недавно понравилось людям, которые лайкают то же, что и вы; пост, который
   набирает лайки прямо сейчас; подписки на сообщества и официальное сообщество Nuvora; меньше —
   авторам, которых вы постоянно пролистываете, и постам с жалобами.

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


def _cached(key, ttl, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    v = fn()
    _cache[key] = (time.time(), v)
    return v


def social_affinity(db, user):
    """{author_id: вес} — насколько человек вам близок: переписка (только число сообщений), взаимная подписка, визиты профиля."""
    def calc():
        since = datetime.utcnow() - timedelta(days=60)
        from sqlalchemy import func
        out = {}
        for other, n in (db.query(models.Message.receiver_id, func.count(models.Message.id))
                         .filter(models.Message.sender_id == user.id, models.Message.receiver_id != None, models.Message.created_at >= since)
                         .group_by(models.Message.receiver_id).order_by(func.count(models.Message.id).desc()).limit(60)):
            out[other] = out.get(other, 0) + math.log1p(n)
        for other, n in (db.query(models.Message.sender_id, func.count(models.Message.id))
                         .filter(models.Message.receiver_id == user.id, models.Message.created_at >= since)
                         .group_by(models.Message.sender_id).order_by(func.count(models.Message.id).desc()).limit(60)):
            out[other] = out.get(other, 0) + 0.6 * math.log1p(n)
        mine = {f for (f,) in db.query(models.Follow.following_id).filter(models.Follow.follower_id == user.id)}
        back = {f for (f,) in db.query(models.Follow.follower_id).filter(models.Follow.following_id == user.id, models.Follow.follower_id.in_(mine or {-1}))}
        for u in back:
            out[u] = out.get(u, 0) + 0.8
        from packs.v3.shares import sharers_for
        for sid, n in sharers_for(db, user).items():  # кто делился с вами постами — его посты ближе к вам
            out[sid] = out.get(sid, 0) + 0.7 * math.log1p(n) + 0.5
        for (o,) in db.query(models.ProfileVisit.owner_id).filter(models.ProfileVisit.viewer_id == user.id).order_by(models.ProfileVisit.id.desc()).limit(40):
            out[o] = out.get(o, 0) + 0.25
        top = max(out.values() or [1.0])
        return {k: v / top for k, v in out.items() if k != user.id}
    return _cached(("aff", user.id), 300, calc)


def similar_taste(db, user):
    """{post_id: вес} — недавние лайки людей, у которых лайки похожи на ваши (коллаборативная фильтрация)."""
    def calc():
        from sqlalchemy import func
        mine = [pid for (pid,) in db.query(models.Like.post_id).filter(models.Like.user_id == user.id).order_by(models.Like.id.desc()).limit(150)]
        if len(mine) < 2:
            return {}
        peers = (db.query(models.Like.user_id, func.count(models.Like.id)).filter(models.Like.post_id.in_(mine), models.Like.user_id != user.id)
                 .group_by(models.Like.user_id).order_by(func.count(models.Like.id).desc()).limit(25).all())
        peers = [(u, n) for u, n in peers if n >= 2]
        if not peers:
            return {}
        w = {u: math.log1p(n) for u, n in peers}
        mine_set = set(mine)
        out = {}
        for u, pid in (db.query(models.Like.user_id, models.Like.post_id).filter(models.Like.user_id.in_(list(w)))
                       .order_by(models.Like.id.desc()).limit(600)):
            if pid not in mine_set:
                out[pid] = out.get(pid, 0) + w[u]
        top = max(out.values() or [1.0])
        return {k: v / top for k, v in out.items()}
    return _cached(("cf", user.id), 600, calc)


def extra_candidate_ids(db, user, limit=80):
    """Посты, которые стоит добавить в кандидаты, даже если они не самые свежие: «похожие вкусы»."""
    if not user:
        return []
    cf = similar_taste(db, user)
    return [pid for pid, _ in sorted(cf.items(), key=lambda x: -x[1])[:limit]]


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
    ids = [p.id for p in pool] or [-1]
    from sqlalchemy import func
    # набирает лайки прямо сейчас: лайки за последние 6 часов
    hot = dict(db.query(models.Like.post_id, func.count(models.Like.id)).filter(models.Like.post_id.in_(ids),
               models.Like.created_at >= now - timedelta(hours=6)).group_by(models.Like.post_id))
    max_hot = max(list(hot.values()) + [1])
    reports = dict(db.query(models.PostReport.post_id, func.count(models.PostReport.id)).filter(models.PostReport.post_id.in_(ids))
                   .group_by(models.PostReport.post_id))
    aff = social_affinity(db, user) if user else {}
    cf = similar_taste(db, user) if user else {}
    from packs.v3 import communities as _comm
    my_comms = _comm.member_ids(db, user) if user else set()
    official = (_comm.info_by_slug(_comm.OFFICIAL_SLUG) or {}).get("id")
    # «усталость»: авторы, которых вы много раз видели в рекомендациях за неделю и ни разу не оценили
    fatigue = _cached(("fat", user.id), 300, lambda: dict(
        db.query(models.Post.user_id, func.count(models.SeenPost.id)).join(models.Post, models.Post.id == models.SeenPost.post_id)
        .filter(models.SeenPost.user_id == user.id, models.SeenPost.created_at >= now - timedelta(days=7))
        .group_by(models.Post.user_id).having(func.count(models.SeenPost.id) >= 8))) if user else {}
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
        close = aff.get(p.user_id, 0)
        if close:
            rel += 0.9 * close
            if close > 0.4:
                reason = reason or "Вы часто общаетесь"
        taste = cf.get(p.id, 0)
        if taste:
            rel += 0.8 * taste
            if taste > 0.3:
                reason = reason or "Нравится людям с похожими вкусами"
        if p.community_id:
            if p.community_id == official:
                rel += 0.6
                reason = "Официально от Nuvora"
            elif p.community_id in my_comms:
                rel += 0.4
                reason = reason or "Из ваших сообществ"
        h = hot.get(p.id, 0)
        if h >= 2:
            quality += 0.35 * h / max_hot
            reason = reason or "Набирает лайки прямо сейчас"
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
        if reports.get(p.id):
            score *= 0.6 ** min(3, reports[p.id])
        if fatigue.get(p.user_id) and (not prof or prof["authors"].get(p.user_id, 0) <= 0) and not close:
            score *= 0.75
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

