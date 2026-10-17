from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import config
import models
from database import get_db
from deps import current_user, json_error, unread_counts
from routers.explore import _like_escape
from routers.posts import read_payload
from services import prefs, social

router = APIRouter(prefix="/api")


@router.get("/ping")
def ping(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if user:
        user.last_seen = datetime.utcnow()
        db.commit()
    return JSONResponse({"ok": True})


@router.post("/offline")
def offline(request: Request, db: Session = Depends(get_db)):
    """Страница закрыта или приложение свёрнуто — показываем «не в сети» сразу, а не через 2 минуты."""
    user = current_user(request, db)
    now = datetime.utcnow()
    # сигнал от старой страницы может прийти уже после загрузки новой — его не считаем
    if user and not (user.last_seen and (now - user.last_seen).total_seconds() < 3):
        user.offline_at = now
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
        users = (db.query(models.User).filter(or_(models.User.username.ilike(term, escape="\\"), models.User.name.ilike(term, escape="\\")),
                                              prefs.sql_flag_off(models.User.prefs, "hide_from_search"))
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
    endpoint = str(data.get("endpoint") or "")[:1000]
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


# ---------------------------------------------------------------- мгновенные уведомления для приложения
def _events(db, user, since_notif, since_msg):
    """Новые уведомления и сообщения после указанных id — для фоновой службы Android-приложения."""
    from routers.messages import preview_of
    from services import chatstyle
    names = chatstyle.load_names(db, user)
    out = []
    hide_text = prefs.get(user, "push_hide_text")
    if user.notify_messages is not False:
        muted = {m.muted_user_id for m in db.query(models.MutedChat).filter_by(user_id=user.id) if m.muted_user_id}
        for m in (db.query(models.Message).filter(models.Message.receiver_id == user.id, models.Message.id > since_msg,
                                                  models.Message.group_id == None, models.Message.is_deleted == False,
                                                  models.Message.is_read == False, models.Message.scheduled_pending != True,
                                                  models.Message.silent != True)
                  .order_by(models.Message.id.asc()).limit(30)):
            if m.sender_id in muted:
                continue
            s = m.sender
            out.append({"kind": "message", "id": m.id, "chat": s.username if s else "", "url": f"/messages/{s.username}" if s else "/messages",
                        "title": names.get(m.sender_id) or (s.name or s.username if s else "Сообщение"),
                        "text": "Новое сообщение" if hide_text else preview_of(m)})
    for n in (db.query(models.Notification).filter(models.Notification.user_id == user.id, models.Notification.id > since_notif,
                                                   models.Notification.is_read == False)
              .order_by(models.Notification.id.asc()).limit(30)):
        who = n.from_user
        title = (names.get(who.id) or who.name or who.username) if who else config.BRAND_NAME
        url = (f"/messages/{who.username}" if who and n.type in ("reminder", "birthday")
               else f"/post/{n.post_id}" if n.post_id else "/notifications")
        out.append({"kind": "notification", "id": n.id, "title": title, "text": (n.text or social.NOTIFY_TEXT.get(n.type, "новое уведомление"))[:200], "url": url})
    return out


@router.get("/stream")
async def stream(request: Request, since_notif: int = -1, since_msg: int = -1, wait: int = 25):
    """Long-poll: ждёт до 25 секунд и сразу отвечает, как только появилось новое сообщение или уведомление.
    Первый запрос (since=-1) только возвращает текущие id, чтобы не показывать старое."""
    import asyncio
    from database import SessionLocal

    def check():
        db = SessionLocal()
        try:
            user = current_user(request, db)
            if not user:
                return None
            if since_notif < 0 or since_msg < 0:
                ln = db.query(func.max(models.Notification.id)).filter(models.Notification.user_id == user.id).scalar() or 0
                lm = db.query(func.max(models.Message.id)).filter(models.Message.receiver_id == user.id).scalar() or 0
                return {"ok": True, "events": [], "notif": ln, "msg": lm}
            ev = _events(db, user, since_notif, since_msg)
            n_id = max([since_notif] + [e["id"] for e in ev if e["kind"] == "notification"])
            m_id = max([since_msg] + [e["id"] for e in ev if e["kind"] == "message"])
            return {"ok": True, "events": ev, "notif": n_id, "msg": m_id}
        finally:
            db.close()

    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(1, min(wait, 25))
    while True:
        res = await loop.run_in_executor(None, check)
        if res is None:
            return JSONResponse({"ok": False}, status_code=401)
        if res["events"] or since_notif < 0 or since_msg < 0 or loop.time() >= deadline or await request.is_disconnected():
            return JSONResponse(res)
        await asyncio.sleep(1.5)
