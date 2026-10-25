"""Сбор ленты: ранжирование, пагинация и состояние постов для текущего пользователя."""
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import selectinload

import config
import models
from services import prefs, social

POST_LOAD = (selectinload(models.Post.author), selectinload(models.Post.likes), selectinload(models.Post.whales),
             selectinload(models.Post.comments), selectinload(models.Post.media_items), selectinload(models.Post.reactions),
             selectinload(models.Post.poll).selectinload(models.Poll.options).selectinload(models.PollOption.votes))


def with_loads(q):
    return q.options(*POST_LOAD)


def get_feed(db, user, tab="foryou", page=1):
    """Возвращает (posts, has_more, reasons). reasons — {post_id: «почему рекомендовано»} для вкладки рекомендаций."""
    from services import recommend
    per = config.POSTS_PER_PAGE
    now = datetime.utcnow()
    q = recommend.guests_hidden_filter(recommend.apply_filters(with_loads(social.visible_posts(db, user)), user), user)
    if tab == "following" and user:
        # «Подписки и подписчики»: посты тех, на кого вы подписаны, и тех, кто подписан на вас
        fids = social.following_ids(db, user) | social.follower_ids(db, user) | {user.id}
        tags = [t.tag for t in db.query(models.HashtagFollow.tag).filter_by(user_id=user.id).limit(30)]
        cond = models.Post.user_id.in_(fids)
        from packs.v3.communities import member_ids
        cids = member_ids(db, user)
        if cids:
            from sqlalchemy import or_ as _or
            cond = _or(cond, models.Post.community_id.in_(cids))
        if tags:  # подписки на темы: посты с этими хэштегами тоже попадают в ленту
            from sqlalchemy import or_
            cond = or_(cond, *[models.Post.content.ilike(f"%#{t}%") for t in tags])
        posts = (q.filter(cond).order_by(models.Post.created_at.desc())
                 .offset((page - 1) * per).limit(per * 2 + 1).all())
        posts = recommend.post_filter(db, user, posts)
        return posts[:per], len(posts) > per, {}
    fids = social.following_ids(db, user)
    q = q.filter(~((models.Post.is_repost == True) & ((models.Post.original_comment == "") | (models.Post.original_comment == None))))
    if user and prefs.get(user, "rec_hide_own"):
        q = q.filter(models.Post.user_id != user.id)
    pool = q.filter(models.Post.created_at > now - timedelta(days=21)).order_by(models.Post.created_at.desc()).limit(500).all()
    if len(pool) < 40:
        pool = q.order_by(models.Post.created_at.desc()).limit(500).all()
    pool = recommend.post_filter(db, user, pool)
    ranked = recommend.rank(db, user, pool, fids)
    chunk = ranked[(page - 1) * per:(page - 1) * per + per + 1]
    show_reasons = user and prefs.get(user, "rec_reasons")
    reasons = {p.id: r for p, _, r in chunk if r and show_reasons}
    posts = [p for p, _, _ in chunk]
    return posts[:per], len(posts) > per, reasons


def post_state(db, user, posts):
    """Множества id для отметок «лайкнул / кит / закладка / репост» и реакции пользователя."""
    ids = [p.id for p in posts if p]
    st = {"liked": set(), "whaled": set(), "bookmarked": set(), "reposted": set(), "my_reactions": {}, "voted": {}}
    if not user or not ids:
        return st
    st["liked"] = {r.post_id for r in db.query(models.Like.post_id).filter(models.Like.user_id == user.id, models.Like.post_id.in_(ids))}
    st["whaled"] = {r.post_id for r in db.query(models.Whale.post_id).filter(models.Whale.user_id == user.id, models.Whale.post_id.in_(ids))}
    st["bookmarked"] = {r.post_id for r in db.query(models.Bookmark.post_id).filter(models.Bookmark.user_id == user.id, models.Bookmark.post_id.in_(ids))}
    st["reposted"] = {r.repost_id for r in db.query(models.Post.repost_id).filter(models.Post.user_id == user.id, models.Post.is_repost == True,
                                                                                  models.Post.repost_id.in_(ids))}
    st["my_reactions"] = {r.post_id: r.emoji for r in db.query(models.Reaction).filter(models.Reaction.user_id == user.id, models.Reaction.post_id.in_(ids))}
    poll_ids = db.query(models.Poll.id).filter(models.Poll.post_id.in_(ids))
    st["voted"] = {v.poll_id: v.option_id for v in db.query(models.PollVote).filter(models.PollVote.user_id == user.id,
                                                                                     models.PollVote.poll_id.in_(poll_ids))}
    st["hidden_users"] = social.blocked_ids(db, user)
    return st


def originals(db, posts, user=None):
    """Загружает доступные пользователю оригиналы репостов: {repost_id: Post}."""
    ids = {p.repost_id for p in posts if p.is_repost and p.repost_id}
    if not ids:
        return {}
    q = with_loads(social.visible_posts(db, user, hide_muted=False)).filter(models.Post.id.in_(ids))
    return {p.id: p for p in q.all()}


def repost_counts(db, posts):
    ids = [p.id for p in posts]
    if not ids:
        return {}
    rows = db.query(models.Post.repost_id, func.count(models.Post.id)).filter(models.Post.repost_id.in_(ids)).group_by(models.Post.repost_id).all()
    return dict(rows)


def feed_context(db, user, posts, reasons=None):
    orig = originals(db, posts, user)
    all_posts = posts + list(orig.values())
    return {"posts": posts, "st": post_state(db, user, all_posts), "originals": orig,
            "repost_counts": repost_counts(db, all_posts), "reasons": reasons or {}}
