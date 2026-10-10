from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

import config
import models
from database import get_db
from deps import current_user, json_error, unread_counts
from routers.explore import _like_escape
from routers.posts import read_payload
from services import social

router = APIRouter(prefix="/api")


@router.get("/ping")
def ping(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if user:
        user.last_seen = datetime.utcnow()
        db.commit()
    return JSONResponse({"ok": True})


@router.get("/counters")
def counters(request: Request, bg: int = 0, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    if not bg:  # фоновая проверка из Android-приложения не делает пользователя «в сети»
        user.last_seen = datetime.utcnow()
        db.commit()
    notif, msgs = unread_counts(user, db)
    reqs = db.query(models.FollowRequest).filter_by(target_id=user.id).count()
    return JSONResponse({"ok": True, "notifications": notif, "messages": msgs, "requests": reqs})


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    return JSONResponse({"ok": True, "username": user.username, "name": user.name, "avatar": user.avatar, "points": user.total_points,
                         "level": user.level, "streak": user.streak_days, "plus": social.is_plus(user)})


@router.get("/users/suggest")
def suggest_users(request: Request, q: str = "", db: Session = Depends(get_db)):
    user = current_user(request, db)
    q = q.strip().lstrip("@")[:30]
    if not q:
        if not user:
            return JSONResponse({"ok": True, "users": []})
        users = db.query(models.User).filter(models.User.id.in_(social.following_ids(db, user) or {-1})).limit(8).all()
    else:
        term = f"{_like_escape(q)}%"
        users = (db.query(models.User).filter(or_(models.User.username.ilike(term, escape="\\"), models.User.name.ilike(term, escape="\\")))
                 .order_by(models.User.total_points.desc()).limit(8).all())
    hidden = social.blocked_ids(db, user)
    return JSONResponse({"ok": True, "users": [{"username": u.username, "name": u.name or u.username, "avatar": u.avatar or "",
                                                 "verified": bool(u.is_verified_badge)} for u in users if u.id not in hidden]})


@router.get("/hashtags/suggest")
def suggest_tags(q: str = "", db: Session = Depends(get_db)):
    q = q.strip().lstrip("#").lower()[:30]
    query = db.query(models.Trend).filter(models.Trend.count > 0)
    if q:
        query = query.filter(models.Trend.tag.ilike(f"{_like_escape(q)}%", escape="\\"))
    return JSONResponse({"ok": True, "tags": [{"tag": t.tag, "count": t.count} for t in query.order_by(models.Trend.count.desc()).limit(8)]})


@router.get("/vapid-public-key")
def vapid_key():
    return JSONResponse({"key": config.VAPID_PUBLIC_KEY})


@router.post("/push/subscribe")
async def push_subscribe(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    data = await read_payload(request)
    endpoint = (data.get("endpoint") or "")[:1000]
    if not endpoint.startswith("https://"):
        return json_error("bad endpoint")
    ex = db.query(models.PushSubscription).filter_by(endpoint=endpoint).first()
    if ex:
        ex.user_id, ex.p256dh, ex.auth = user.id, data.get("p256dh", ""), data.get("auth", "")
    else:
        db.add(models.PushSubscription(user_id=user.id, endpoint=endpoint, p256dh=data.get("p256dh", ""), auth=data.get("auth", "")))
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/push/unsubscribe")
async def push_unsubscribe(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    data = await read_payload(request)
    db.query(models.PushSubscription).filter_by(user_id=user.id, endpoint=data.get("endpoint", "")).delete()
    db.commit()
    return JSONResponse({"ok": True})
