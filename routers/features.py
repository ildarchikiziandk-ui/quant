"""Новые возможности: «Избранное» в сообщениях, напоминания о сообщениях, дни рождения друзей, похожие посты."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import current_user, json_error, login_redirect, render
from routers.messages import preview_of
from routers.posts import read_payload
from services import chatstyle, prefs, social, text

router = APIRouter()


def _own_message(db, user, msg_id):
    m = db.get(models.Message, msg_id)
    if not m or m.is_deleted or user.id not in (m.sender_id, m.receiver_id):
        return None
    return m


def _peer_of(m, user):
    return m.receiver if m.sender_id == user.id else m.sender


# ---------------------------------------------------------------- избранные сообщения
@router.post("/messages/{msg_id}/star")
def star(msg_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    m = _own_message(db, user, msg_id)
    if not m:
        return json_error("Сообщение не найдено", 404)
    row = db.query(models.StarredMessage).filter_by(user_id=user.id, message_id=m.id).first()
    if row:
        db.delete(row)
    else:
        db.add(models.StarredMessage(user_id=user.id, message_id=m.id))
    db.commit()
    return JSONResponse({"ok": True, "starred": not row})


@router.get("/messages/starred")
def starred(request: Request, q: str = "", db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    rows = (db.query(models.StarredMessage).filter_by(user_id=user.id)
            .order_by(models.StarredMessage.created_at.desc()).limit(300).all())
    items = []
    for r in rows:
        m = r.message
        if not m or m.is_deleted or user.id in (m.deleted_for or "").split(","):
            continue
        prev = preview_of(m)
        if q and q.lower() not in (m.content or "").lower():
            continue
        items.append({"m": m, "peer": _peer_of(m, user), "preview": prev, "starred_at": r.created_at})
    return render(request, db, "starred.html", items=items, q=q)


# ---------------------------------------------------------------- напомнить позже
@router.post("/messages/{msg_id}/remind")
async def remind(msg_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    m = _own_message(db, user, msg_id)
    if not m:
        return json_error("Сообщение не найдено", 404)
    data = await read_payload(request)
    try:
        minutes = int(data.get("minutes") or 60)
    except (TypeError, ValueError):
        return json_error("Неверное время")
    if not 1 <= minutes <= 60 * 24 * 30:
        return json_error("Можно напомнить от минуты до 30 дней")
    at = datetime.utcnow() + timedelta(minutes=minutes)
    db.add(models.MessageReminder(user_id=user.id, message_id=m.id, remind_at=at))
    db.commit()
    return JSONResponse({"ok": True, "at": at.isoformat()})


def deliver_reminders(db):
    """Вызывается фоновой задачей: отправляет наступившие напоминания."""
    now = datetime.utcnow()
    sent = 0
    for r in db.query(models.MessageReminder).filter(models.MessageReminder.done == False,
                                                     models.MessageReminder.remind_at <= now).limit(100).all():
        r.done = True
        m = r.message
        user = db.get(models.User, r.user_id)
        if not m or m.is_deleted or not user:
            continue
        peer = _peer_of(m, user)
        snippet = preview_of(m)
        n = models.Notification(user_id=user.id, from_user_id=peer.id if peer else None, type="reminder",
                                text=f"напоминание о сообщении: «{snippet[:120]}»")
        db.add(n)
        from services import push
        push.send_push_to_user(user.id, db, "Напоминание", snippet[:120], f"/messages/{peer.username}#msg-{m.id}" if peer else "/messages")
        sent += 1
    db.commit()
    return sent


# ---------------------------------------------------------------- дни рождения
def _next_birthday(bday, today):
    try:
        month, day = int(bday[5:7]), int(bday[8:10])
    except (TypeError, ValueError):
        return None
    for year in (today.year, today.year + 1):
        try:
            d = today.replace(year=year, month=month, day=day)
        except ValueError:  # 29 февраля в невисокосный год
            d = today.replace(year=year, month=3, day=1)
        if d >= today:
            return d
    return None


def upcoming_birthdays(db, user, days=60):
    ids = social.following_ids(db, user) | {f.follower_id for f in db.query(models.Follow.follower_id).filter(models.Follow.following_id == user.id)}
    if not ids:
        return []
    today = datetime.utcnow().date()
    out = []
    for u in db.query(models.User).filter(models.User.id.in_(ids), models.User.birthday != "", models.User.birthday != None):
        if prefs.get(u, "hide_birthday") or u.is_blocked:
            continue
        d = _next_birthday(u.birthday, today)
        if d and (d - today).days <= days:
            out.append({"user": u, "date": d, "in_days": (d - today).days})
    out.sort(key=lambda x: x["in_days"])
    return out


@router.get("/birthdays")
def birthdays(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    return render(request, db, "birthdays.html", items=upcoming_birthdays(db, user))


def notify_birthdays(db):
    """Раз в день: утром напоминаем подписчикам о дне рождения друга (одно уведомление на друга в день)."""
    today = datetime.utcnow()
    mark = today.strftime("-%m-%d")
    start = today.replace(hour=0, minute=0, second=0, microsecond=0)
    sent = 0
    for u in db.query(models.User).filter(models.User.birthday.like(f"%{mark}")).limit(500):
        if prefs.get(u, "hide_birthday") or u.is_blocked:
            continue
        for f in db.query(models.Follow).filter(models.Follow.following_id == u.id).limit(1000):
            exists = db.query(models.Notification.id).filter(models.Notification.user_id == f.follower_id,
                                                             models.Notification.from_user_id == u.id,
                                                             models.Notification.type == "birthday",
                                                             models.Notification.created_at >= start).first()
            if exists:
                continue
            db.add(models.Notification(user_id=f.follower_id, from_user_id=u.id, type="birthday", text="празднует день рождения сегодня — поздравьте!"))
            sent += 1
    db.commit()
    return sent


# ---------------------------------------------------------------- похожие посты
def similar_posts(db, user, post, limit=6):
    tags = list(dict.fromkeys(text.extract_hashtags(post.content or "")))[:5]
    hidden = social.blocked_ids(db, user)
    base = db.query(models.Post).filter(models.Post.id != post.id, models.Post.is_published != False,
                                        models.Post.is_archived != True)
    found = []
    if tags:
        cond = or_(*[models.Post.content.ilike(f"%#{t}%") for t in tags])
        found = base.filter(cond).order_by(models.Post.created_at.desc()).limit(40).all()
    if len(found) < limit:
        found += base.filter(models.Post.user_id == post.user_id).order_by(models.Post.created_at.desc()).limit(20).all()
    out, seen = [], set()
    for p in found:
        if p.id in seen or p.user_id in hidden or not social.can_view_post(db, user, p):
            continue
        seen.add(p.id)
        out.append(p)
        if len(out) >= limit:
            break
    return out
