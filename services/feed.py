"""Сбор ленты: ранжирование, пагинация и состояние постов для текущего пользователя."""
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import selectinload

import config
import models
from services import social

POST_LOAD = (selectinload(models.Post.author), selectinload(models.Post.likes), selectinload(models.Post.whales),
             selectinload(models.Post.comments), selectinload(models.Post.media_items), selectinload(models.Post.reactions),
             selectinload(models.Post.poll).selectinload(models.Poll.options).selectinload(models.PollOption.votes))


def with_loads(q):
    return q.options(*POST_LOAD)


def score(post, fids, now):
    age_h = max((now - post.created_at).total_seconds() / 3600, 0.1)
    engagement = len(post.likes) * 3 + len(post.comments) * 4 + len(post.whales) * 2 + len(post.reactions) * 2 + (post.views or 0) * 0.05
    bonus = 40 if post.user_id in fids else 0
    if post.image or post.media_items:
        bonus += 5
    return (engagement + bonus + 20) / ((age_h + 2) ** 1.4)


def get_feed(db, user, tab="foryou", page=1):
    per = config.POSTS_PER_PAGE
    now = datetime.utcnow()
    q = with_loads(social.visible_posts(db, user))
    if tab == "following" and user:
        fids = social.following_ids(db, user) | {user.id}
        q = q.filter(models.Post.user_id.in_(fids))
        posts = q.order_by(models.Post.created_at.desc()).offset((page - 1) * per).limit(per + 1).all()
    elif tab == "latest":
        posts = q.order_by(models.Post.created_at.desc()).offset((page - 1) * per).limit(per + 1).all()
    elif tab == "media":
        q = q.filter(models.Post.image != "", models.Post.image != None)
        posts = q.order_by(models.Post.created_at.desc()).offset((page - 1) * per).limit(per + 1).all()
    else:
        fids = social.following_ids(db, user)
        pool = q.filter(models.Post.created_at > now - timedelta(days=21)).order_by(models.Post.created_at.desc()).limit(400).all()
        if len(pool) < 40:
            pool = q.order_by(models.Post.created_at.desc()).limit(400).all()
        pool.sort(key=lambda p: score(p, fids, now), reverse=True)
        posts = pool[(page - 1) * per:(page - 1) * per + per + 1]
    has_more = len(posts) > per
    return posts[:per], has_more


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
    st["voted"] = {v.poll_id: v.option_id for v in db.query(models.PollVote).filter(models.PollVote.user_id == user.id)}
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


def feed_context(db, user, posts):
    orig = originals(db, posts, user)
    all_posts = posts + list(orig.values())
    return {"posts": posts, "st": post_state(db, user, all_posts), "originals": orig,
            "repost_counts": repost_counts(db, all_posts)}
