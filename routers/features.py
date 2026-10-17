"""Новые возможности: «Избранное» в сообщениях, напоминания о сообщениях, дни рождения друзей, похожие посты."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import current_user, json_error, login_redirect, render
from routers.messages import preview_of, visible_to
from routers.posts import read_payload
from services import chatstyle, prefs, social, text

router = APIRouter()


def _own_message(db, user, msg_id):
    m = db.get(models.Message, msg_id)
    return m if visible_to(m, user.id) else None


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
        if not visible_to(m, user.id):
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
    from sqlalchemy.orm import selectinload
    base = db.query(models.Post).options(selectinload(models.Post.author), selectinload(models.Post.likes)).filter(
        models.Post.id != post.id, models.Post.is_published != False,
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


# ---------------------------------------------------------------- Nuvora 2.0
@router.get("/api/feed/new")
def feed_new(request: Request, after: int = 0, db: Session = Depends(get_db)):
    """Сколько новых постов у тех, на кого вы подписаны, появилось после поста `after` — для плашки «Новые посты»."""
    user = current_user(request, db)
    if not user or after <= 0:
        return JSONResponse({"ok": True, "count": 0})
    fids = social.following_ids(db, user)
    if not fids:
        return JSONResponse({"ok": True, "count": 0})
    n = (social.visible_posts(db, user).filter(models.Post.id > after, models.Post.user_id.in_(fids),
                                               models.Post.user_id != user.id).count())
    return JSONResponse({"ok": True, "count": min(n, 99)})


@router.post("/messages/read-all")
def read_all_chats(request: Request, db: Session = Depends(get_db)):
    """«Прочитать все»: отмечает прочитанными все входящие личные сообщения."""
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    n = db.query(models.Message).filter(models.Message.receiver_id == user.id, models.Message.group_id == None,
                                        models.Message.is_read == False, models.Message.scheduled_pending != True).update(
        {"is_read": True, "is_delivered": True}, synchronize_session=False)
    db.query(models.ChatSetting).filter(models.ChatSetting.user_id == user.id, models.ChatSetting.marked_unread == True).update(
        {"marked_unread": False}, synchronize_session=False)
    db.commit()
    return JSONResponse({"ok": True, "count": n})


@router.post("/chats/{username}/mute-for")
async def mute_for(username: str, request: Request, db: Session = Depends(get_db)):
    """Без звука на время: hours = 1, 8, 24, 168 или 0 — навсегда; off=1 — включить звук."""
    from routers.messages import _get_user
    user = current_user(request, db)
    other = _get_user(db, username)
    if not user or not other or other.id == user.id:
        return json_error("Чат не найден", 404)
    data = await read_payload(request)
    db.query(models.MutedChat).filter_by(user_id=user.id, muted_user_id=other.id).delete()
    if str(data.get("off") or "") not in ("1", "true", "True"):
        try:
            hours = max(0, min(int(str(data.get("hours") or 0)[:4]), 24 * 365))
        except ValueError:
            hours = 0
        db.add(models.MutedChat(user_id=user.id, muted_user_id=other.id, until=datetime.utcnow() + timedelta(hours=hours) if hours else None))
        db.commit()
        return JSONResponse({"ok": True, "muted": True, "until": hours})
    db.commit()
    return JSONResponse({"ok": True, "muted": False})


def cleanup(db):
    """Фоновая уборка: закончившиеся «без звука», старые прочитанные уведомления, выполненные напоминания."""
    now = datetime.utcnow()
    db.query(models.MutedChat).filter(models.MutedChat.until != None, models.MutedChat.until <= now).delete(synchronize_session=False)
    db.query(models.Notification).filter(models.Notification.is_read == True,
                                         models.Notification.created_at < now - timedelta(days=90)).delete(synchronize_session=False)
    db.query(models.MessageReminder).filter(models.MessageReminder.done == True,
                                            models.MessageReminder.remind_at < now - timedelta(days=7)).delete(synchronize_session=False)
    db.commit()


# ---------------------------------------------------------------- перенос настроек
@router.get("/settings/backup/export")
def prefs_export(request: Request, db: Session = Depends(get_db)):
    import json
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    data = {"nuvora_settings": 1, "theme": user.theme, "prefs": prefs.values(user)}
    from fastapi.responses import Response
    return Response(json.dumps(data, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="nuvora-settings.json"'})


@router.post("/settings/backup/import")
async def prefs_import(request: Request, db: Session = Depends(get_db)):
    import json
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    form = await request.form()
    f = form.get("file")
    try:
        raw = await f.read(200_000) if hasattr(f, "read") else str(form.get("json") or "").encode()
        data = json.loads(raw.decode("utf-8"))
        assert isinstance(data, dict) and isinstance(data.get("prefs"), dict)
    except Exception:
        return json_error("Это не файл настроек Nuvora")
    n = prefs.update_many(user, data["prefs"])
    if data.get("theme") in ("light", "dark", "auto"):
        user.theme = data["theme"]
    db.commit()
    return JSONResponse({"ok": True, "count": n})


@router.post("/settings/backup/reset")
def prefs_reset(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    keep = {k: v for k, v in prefs.raw(user).items() if k == "timezone"}  # часовой пояс оставляем
    prefs.replace(user, keep)
    db.commit()
    return JSONResponse({"ok": True})


@router.get("/whats-new")
def whats_new(request: Request, db: Session = Depends(get_db)):
    from services.whatsnew import GROUPS
    total = sum(len(items) for _, _, items in GROUPS)
    return render(request, db, "whats_new.html", groups=GROUPS, total=total)


# ---------------------------------------------------------------- календарь (.ics)
def _ics(lines):
    from fastapi.responses import Response
    body = "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Nuvora//RU", "CALSCALE:GREGORIAN"] + lines + ["END:VCALENDAR"]) + "\r\n"
    return Response(body, media_type="text/calendar; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="nuvora.ics"'})


def _ics_text(s):
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")[:500]


@router.get("/calendar/event/{eid}.ics")
def event_ics(eid: int, request: Request, db: Session = Depends(get_db)):
    """«Добавить в календарь» — файл для Google, Яндекс и Apple Календаря."""
    import config
    ev = db.get(models.Event, eid)
    if not ev or not ev.starts_at:
        return json_error("not found", 404)
    st = ev.starts_at
    return _ics(["BEGIN:VEVENT", f"UID:event-{ev.id}@nuvora", f"DTSTAMP:{datetime.utcnow():%Y%m%dT%H%M%SZ}",
                 f"DTSTART:{st:%Y%m%dT%H%M%SZ}", f"DTEND:{st + timedelta(hours=2):%Y%m%dT%H%M%SZ}",
                 f"SUMMARY:{_ics_text(ev.title)}", f"LOCATION:{_ics_text(ev.place)}",
                 f"DESCRIPTION:{_ics_text((ev.description or '') + chr(10) + config.SITE_URL + '/events/' + str(ev.id))}",
                 "BEGIN:VALARM", "TRIGGER:-PT1H", "ACTION:DISPLAY", "DESCRIPTION:Скоро мероприятие", "END:VALARM", "END:VEVENT"])


@router.get("/calendar/birthdays.ics")
def birthdays_ics(request: Request, db: Session = Depends(get_db)):
    """Дни рождения друзей в календарь телефона — повторяются каждый год."""
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    lines = []
    for it in upcoming_birthdays(db, user, days=366):
        u, d = it["user"], it["date"]
        lines += ["BEGIN:VEVENT", f"UID:bday-{u.id}@nuvora", f"DTSTAMP:{datetime.utcnow():%Y%m%dT%H%M%SZ}",
                  f"DTSTART;VALUE=DATE:{d:%Y%m%d}", "RRULE:FREQ=YEARLY", f"SUMMARY:{_ics_text('День рождения: ' + (u.name or u.username))}",
                  "TRANSP:TRANSPARENT", "END:VEVENT"]
    return _ics(lines)
