"""Лента 3.0: обратный отсчёт в посте, «не показывать автора 30 дней», «Популярное сегодня»."""
import time
from datetime import datetime, timedelta

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from database import SessionLocal, get_db
from deps import current_user, json_error, render
from routers.posts import read_payload
from services import feed as feed_svc
from services import social, timezones
from services.text import censor

from . import models as m
from .common import router, s


# ---------------------------------------------------------------- обратный отсчёт
@router.post("/v3/post/{post_id}/countdown")
async def set_countdown(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    post = db.get(models.Post, post_id)
    if not user or not post or post.user_id != user.id:
        return json_error("Пост не найден", 404)
    data = await read_payload(request)
    row = db.query(m.PostCountdown).filter_by(post_id=post.id).first()
    if s(data.get("remove")):
        if row:
            db.delete(row)
            db.commit()
        _CACHE["t"] = 0
        return JSONResponse({"ok": True, "removed": True})
    title = censor(s(data.get("title")).strip()[:60], social.stop_words(db)) or "До события"
    try:
        local = datetime.strptime(s(data.get("at"))[:16], "%Y-%m-%dT%H:%M")
    except ValueError:
        return json_error("Укажите дату и время")
    at = timezones.from_local(local, user)
    if at <= datetime.utcnow():
        return json_error("Дата должна быть в будущем")
    if at > datetime.utcnow() + timedelta(days=366 * 3):
        return json_error("Не дальше чем на 3 года вперёд")
    if not row:
        row = m.PostCountdown(post_id=post.id)
        db.add(row)
    row.title, row.at = title, at
    db.commit()
    _CACHE["t"] = 0
    return JSONResponse({"ok": True})


_CACHE = {"t": 0, "data": {}}


def countdown(post):
    """Отсчёт для поста (или None). Все активные отсчёты держим в памяти и обновляем раз в 30 секунд —
    лента из 20 постов не делает 20 лишних запросов."""
    if not post:
        return None
    if time.monotonic() - _CACHE["t"] > 30:
        db = SessionLocal()
        try:
            since = datetime.utcnow() - timedelta(days=2)  # закончившиеся ещё пару дней показываем как «Началось!»
            _CACHE["data"] = {c.post_id: (c.title, c.at) for c in db.query(m.PostCountdown).filter(m.PostCountdown.at > since)}
        finally:
            db.close()
        _CACHE["t"] = time.monotonic()
    v = _CACHE["data"].get(post.id)
    return {"title": v[0], "ts": int((v[1] - datetime(1970, 1, 1)).total_seconds())} if v else None


# ---------------------------------------------------------------- не показывать автора 30 дней
@router.post("/v3/hide/{username}")
def hide_author(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    target = db.query(models.User).filter(func.lower(models.User.username) == username.lower()).first()
    if not target or target.id == user.id:
        return json_error("Пользователь не найден", 404)
    if not db.query(models.UserMute).filter_by(user_id=user.id, muted_id=target.id).first():
        db.add(models.UserMute(user_id=user.id, muted_id=target.id))
    db.query(m.TempMute).filter_by(user_id=user.id, muted_id=target.id).delete()
    db.add(m.TempMute(user_id=user.id, muted_id=target.id, until=datetime.utcnow() + timedelta(days=30)))
    db.commit()
    return JSONResponse({"ok": True})


def unmute_expired(db):
    """Фоновая задача: через 30 дней автор снова появляется в ленте."""
    now = datetime.utcnow()
    for t in db.query(m.TempMute).filter(m.TempMute.until <= now).limit(200).all():
        db.query(models.UserMute).filter_by(user_id=t.user_id, muted_id=t.muted_id).delete()
        db.delete(t)
    db.commit()


# ---------------------------------------------------------------- лента «Только друзья»
@router.get("/friends")
def friends_feed(request: Request, page: int = 1, db: Session = Depends(get_db)):
    """Посты только тех, с кем вы подписаны друг на друга — без рекомендаций и случайных людей."""
    from deps import login_redirect
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    page = max(1, min(page, 50))
    mine = social.following_ids(db, user)
    mutual = {f.follower_id for f in db.query(models.Follow.follower_id).filter(
        models.Follow.following_id == user.id, models.Follow.follower_id.in_(mine or {-1}))}
    q = social.visible_posts(db, user).filter(models.Post.user_id.in_(mutual or {-1})).order_by(models.Post.created_at.desc())
    posts = q.offset((page - 1) * 20).limit(21).all()
    has_more = len(posts) > 20
    return render(request, db, "packs/v3/friends.html", friends_n=len(mutual), page=page, has_more=has_more,
                  **feed_svc.feed_context(db, user, posts[:20]))
