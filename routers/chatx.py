"""Дополнительные возможности чатов: оформление, свои имена контактов, архив, «непрочитано», медиа чата,
статистика и экспорт переписки, «удалить у меня», доставка отложенных сообщений."""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import current_user, json_error, login_redirect, redirect, render
from routers.messages import _alive, _get_user, _visible_for, dialog_filter, preview_of
from routers.posts import read_payload
from services import chatstyle, push, social, streaks
from services.uploads import save_file

router = APIRouter()


def _peer(db, request, username):
    user = current_user(request, db)
    other = _get_user(db, username)
    if not user or not other or other.id == user.id:
        return user, None
    return user, other


# ---------------------------------------------------------------- оформление чата
@router.post("/chats/{username}/look")
async def chat_look(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    form = await request.form()
    every = form.get("scope") == "all"
    if username == "_all":
        every = True
    other = None if every else _get_user(db, username)
    if not every and not other:
        return json_error("Чат не найден", 404)
    row = chatstyle.setting(db, user, 0 if every else other.id, None, create=True)
    wp = form.get("wallpaper")
    if form.get("wallpaper_file") is not None and getattr(form.get("wallpaper_file"), "filename", ""):
        url, err = save_file(form.get("wallpaper_file"), allowed=("image",))
        if not url:
            return json_error(err)
        wp = url
    if wp is not None and (wp in chatstyle.WP or wp.startswith("/uploads/")):
        row.wallpaper = wp
    if form.get("bubble") is not None and form.get("bubble") in chatstyle.BUBBLE:
        row.bubble = form.get("bubble")
    if form.get("font") is not None and form.get("font") in chatstyle.FONT_KEYS:
        row.font = form.get("font")
    if form.get("reset"):
        row.wallpaper, row.bubble, row.font = "", "", ""
    db.commit()
    return JSONResponse({"ok": True, "look": chatstyle.look(db, user, None if every else other.id)})


# ---------------------------------------------------------------- свои имена
@router.post("/contacts/{username}/name")
async def contact_name(username: str, request: Request, db: Session = Depends(get_db)):
    user, other = _peer(db, request, username)
    if not user or not other:
        return json_error("Пользователь не найден", 404)
    data = await read_payload(request)
    chatstyle.set_name(db, user, other, data.get("name"))
    return JSONResponse({"ok": True, "name": str(data.get("name") or "").strip()[:60] or other.name or other.username})


# ---------------------------------------------------------------- архив и «непрочитано»
@router.post("/chats/{username}/archive")
def chat_archive(username: str, request: Request, db: Session = Depends(get_db)):
    user, other = _peer(db, request, username)
    if not user or not other:
        return json_error("Чат не найден", 404)
    row = chatstyle.setting(db, user, other.id, None, create=True)
    row.archived = not row.archived
    db.commit()
    return JSONResponse({"ok": True, "archived": row.archived})


@router.post("/chats/{username}/unread")
def chat_unread(username: str, request: Request, db: Session = Depends(get_db)):
    user, other = _peer(db, request, username)
    if not user or not other:
        return json_error("Чат не найден", 404)
    row = chatstyle.setting(db, user, other.id, None, create=True)
    row.marked_unread = not row.marked_unread
    db.commit()
    return JSONResponse({"ok": True, "marked": row.marked_unread})


# ---------------------------------------------------------------- «удалить у меня»
@router.post("/messages/{msg_id}/hide")
def hide_for_me(msg_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    m = db.get(models.Message, msg_id)
    if not user or not m or user.id not in (m.sender_id, m.receiver_id):
        return json_error("not found", 404)
    if m.deleted_for and m.deleted_for != user.id:  # собеседник уже скрыл у себя — удаляем совсем
        m.is_deleted, m.content, m.image, m.voice, m.file_url = True, "", "", "", ""
    else:
        m.deleted_for = user.id
    db.commit()
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------- медиа и файлы чата
@router.get("/messages/{username}/media")
def chat_media(username: str, request: Request, tab: str = "photo", db: Session = Depends(get_db)):
    user, other = _peer(db, request, username)
    if not user:
        return login_redirect(request)
    if not other:
        return redirect("/messages")
    q = db.query(models.Message).filter(dialog_filter(user.id, other.id), models.Message.is_deleted == False,
                                        or_(models.Message.deleted_for == None, models.Message.deleted_for != user.id),
                                        models.Message.scheduled_pending != True, _alive())
    counts = {
        "photo": q.filter(models.Message.image != "", models.Message.image != None).count(),
        "voice": q.filter(models.Message.voice != "", models.Message.voice != None).count(),
        "file": q.filter(models.Message.file_url != "", models.Message.file_url != None).count(),
    }
    items, links = [], []
    if tab == "photo":
        items = q.filter(models.Message.image != "", models.Message.image != None).order_by(models.Message.id.desc()).limit(300).all()
    elif tab == "voice":
        items = q.filter(models.Message.voice != "", models.Message.voice != None).order_by(models.Message.id.desc()).limit(200).all()
    elif tab == "file":
        items = q.filter(models.Message.file_url != "", models.Message.file_url != None).order_by(models.Message.id.desc()).limit(200).all()
    elif tab == "link":
        import re
        for m in q.order_by(models.Message.id.desc()).limit(3000):
            for url in re.findall(r"https?://[^\s<>\"']+", m.content or ""):
                links.append((url, m))
            if len(links) >= 200:
                break
    counts["link"] = len(links) if tab == "link" else None
    return render(request, db, "chat_media.html", other=other, tab=tab, items=items, links=links, counts=counts)


# ---------------------------------------------------------------- статистика переписки
@router.get("/messages/{username}/stats")
def chat_stats(username: str, request: Request, db: Session = Depends(get_db)):
    user, other = _peer(db, request, username)
    if not user or not other:
        return json_error("Чат не найден", 404)
    base = db.query(models.Message).filter(dialog_filter(user.id, other.id), models.Message.is_deleted == False, _alive(),
                                           _visible_for(user.id), models.Message.scheduled_pending != True)
    total = base.count()
    mine = base.filter(models.Message.sender_id == user.id).count()
    first = base.order_by(models.Message.created_at.asc()).first()
    voices = base.filter(models.Message.voice != "", models.Message.voice != None).count()
    media = base.filter(models.Message.image != "", models.Message.image != None).count()
    st = streaks.chat_streaks(db, user, [other.id]).get(other.id)
    return JSONResponse({"ok": True, "total": total, "mine": mine, "theirs": total - mine, "voices": voices, "media": media,
                         "since": first.created_at.strftime("%d.%m.%Y") if first else None, "streak": st[0] if st else 0})


# ---------------------------------------------------------------- экспорт переписки
@router.get("/messages/{username}/export")
def chat_export(username: str, request: Request, fmt: str = "txt", db: Session = Depends(get_db)):
    user, other = _peer(db, request, username)
    if not user:
        return login_redirect(request)
    if not other:
        return redirect("/messages")
    msgs = (db.query(models.Message).filter(dialog_filter(user.id, other.id), models.Message.is_deleted == False,
                                            or_(models.Message.deleted_for == None, models.Message.deleted_for != user.id),
                                            or_(models.Message.scheduled_pending != True, models.Message.sender_id == user.id), _alive())
            .order_by(models.Message.created_at.asc()).limit(50000).all())
    from services import timezones
    names = {user.id: user.name or user.username, other.id: chatstyle.name_of(other)}
    if fmt == "json":
        body = json.dumps([{"from": names.get(m.sender_id), "time": timezones.to_local(m.created_at, user).isoformat(timespec="minutes"),
                            "text": m.content or "", "attachment": m.image or m.voice or m.file_url or ""} for m in msgs],
                          ensure_ascii=False, indent=1)
        media = "application/json"
    else:
        lines = [f"Переписка с {names[other.id]} (@{other.username}) — выгружено {datetime.utcnow():%d.%m.%Y}", ""]
        for m in msgs:
            t = timezones.to_local(m.created_at, user).strftime("%d.%m.%Y %H:%M")
            lines.append(f"[{t}] {names.get(m.sender_id, '?')}: {m.content or preview_of(m)}")
        body, media = "\n".join(lines), "text/plain; charset=utf-8"
    fname = f"chat-{other.username}.{ 'json' if fmt == 'json' else 'txt'}"
    return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ---------------------------------------------------------------- доставка отложенных сообщений
def deliver_scheduled(db):
    """Вызывается фоновой задачей раз в несколько секунд: отложенные сообщения, время которых пришло."""
    now = datetime.utcnow()
    due = (db.query(models.Message).filter(models.Message.scheduled_pending == True, models.Message.deliver_at <= now)
           .limit(200).all())
    for m in due:
        # атомарно «забираем» сообщение, чтобы при нескольких процессах уведомление ушло один раз
        n = db.query(models.Message).filter(models.Message.id == m.id, models.Message.scheduled_pending == True).update(
            {"scheduled_pending": False, "created_at": now, "deliver_at": now}, synchronize_session=False)
        db.commit()
        if not n:
            continue
        db.refresh(m)
        sender, other = db.get(models.User, m.sender_id), db.get(models.User, m.receiver_id)
        if m.is_deleted or (m.disappear_at and m.disappear_at <= now):
            continue
        # за время ожидания получатель мог заблокировать отправителя или закрыть личные сообщения — тогда не доставляем
        if not sender or not other or not social.can_message(db, sender, other)[0]:
            m.is_deleted = True
            db.commit()
            continue
        if m.silent:
            continue
        muted = db.query(models.MutedChat).filter_by(user_id=other.id, muted_user_id=sender.id).first()
        if other.notify_messages is not False and not muted:
            push.send_push_to_user(other.id, db, sender.name or sender.username, preview_of(m), f"/messages/{sender.username}")
    return len(due)
