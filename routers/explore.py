from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import current_user, login_redirect, redirect, render
from services import feed, prefs, social

router = APIRouter()


def _like_escape(q):
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/search")
def search_page(request: Request, q: str = "", type: str = "all", db: Session = Depends(get_db)):
    user = current_user(request, db)
    q = q.strip()[:100]
    users, posts, tags = [], [], []
    if q:
        hidden = social.blocked_ids(db, user)
        term = f"%{_like_escape(q.lstrip('@'))}%"
        if type in ("all", "users"):
            users = (db.query(models.User).filter(or_(models.User.username.ilike(term, escape="\\"), models.User.name.ilike(term, escape="\\")),
                                                  ~models.User.id.in_(hidden or {-1}), prefs.sql_flag_off(models.User.prefs, "hide_from_search"))
                     .order_by(models.User.total_points.desc()).limit(30).all())
        if type in ("all", "posts"):
            posts = (feed.with_loads(social.visible_posts(db, user)).filter(models.Post.content.ilike(f"%{_like_escape(q)}%", escape="\\"))
                     .order_by(models.Post.created_at.desc()).limit(40).all())
        if type in ("all", "tags"):
            tags = (db.query(models.Trend).filter(models.Trend.tag.ilike(f"%{_like_escape(q.lstrip('#').lower())}%", escape="\\"))
                    .order_by(models.Trend.count.desc()).limit(20).all())
    ctx = feed.feed_context(db, user, posts)
    return render(request, db, "search.html", query=q, type=type, users=users, tags=tags,
                  following=social.following_ids(db, user), **ctx)


@router.get("/hashtag/{tag}")
def hashtag_page(tag: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    tag = tag.lstrip("#").lower()[:64]
    candidates = (feed.with_loads(social.visible_posts(db, user)).filter(models.Post.content.ilike(f"%#{_like_escape(tag)}%", escape="\\"))
                  .order_by(models.Post.created_at.desc()).limit(150).all())
    from services.text import extract_hashtags
    posts = [p for p in candidates if tag in extract_hashtags(p.content)][:60]
    trend = db.query(models.Trend).filter_by(tag=tag).first()
    return render(request, db, "hashtag.html", tag=tag, trend=trend, **feed.feed_context(db, user, posts))


@router.get("/trends")
def trends_page():
    return redirect("/explore", 301)


@router.get("/explore")
def explore_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    since = datetime.utcnow() - timedelta(days=3)
    pool = feed.with_loads(social.visible_posts(db, user)).filter(models.Post.created_at > since).limit(300).all()
    if len(pool) < 10:
        pool = feed.with_loads(social.visible_posts(db, user)).order_by(models.Post.created_at.desc()).limit(300).all()
    pool.sort(key=lambda p: len(p.likes) * 3 + len(p.comments) * 4 + len(p.whales) * 2 + (p.views or 0) * 0.1, reverse=True)
    hot = pool[:15]
    media = [p for p in pool if p.image and p.media_type == "image"][:12]
    hidden = social.blocked_ids(db, user) | ({user.id} if user else set())
    top_users = (db.query(models.User, func.count(models.Follow.id).label("n")).outerjoin(models.Follow, models.Follow.following_id == models.User.id)
                 .filter(~models.User.id.in_(hidden or {-1}), models.User.is_blocked == False).group_by(models.User.id)
                 .order_by(func.count(models.Follow.id).desc()).limit(8).all())
    new_users = (db.query(models.User).filter(~models.User.id.in_(hidden or {-1})).order_by(models.User.created_at.desc()).limit(8).all())
    return render(request, db, "explore.html", hot=hot, media=media, top_users=top_users, new_users=new_users,
                  following=social.following_ids(db, user), **feed.feed_context(db, user, hot))


@router.get("/mentions")
def mentions_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    candidates = (feed.with_loads(social.visible_posts(db, user)).filter(models.Post.content.ilike(f"%@{_like_escape(user.username)}%", escape="\\"))
                  .order_by(models.Post.created_at.desc()).limit(100).all())
    from services.text import extract_mentions
    posts = [p for p in candidates if user.username in extract_mentions(p.content)]
    return render(request, db, "mentions.html", **feed.feed_context(db, user, posts))
