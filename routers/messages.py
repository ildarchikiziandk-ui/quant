from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, selectinload

import config
import models
from database import get_db
from deps import current_user, json_error, login_redirect, redirect, render, templates
from routers.posts import read_payload
from services import gamification, prefs, push, ratelimit, social
from services.text import censor
from services.uploads import save_file

router = APIRouter()

MSG_REACTIONS = ["❤️", "🐋"]  # только сердце и кит


def _get_user(db, username):
    return db.query(models.User).filter(func.lower(models.User.username) == (username or "").lower()).first()


def dialog_filter(a_id, b_id):
    return and_(models.Message.group_id == None, or_(
        and_(models.Message.sender_id == a_id, models.Message.receiver_id == b_id),
        and_(models.Message.sender_id == b_id, models.Message.receiver_id == a_id)))


def _alive():
    now = datetime.utcnow()
    return or_(models.Message.disappear_at == None, models.Message.disappear_at > now)


def preview_of(m):
    if m.is_deleted:
        return "Сообщение удалено"
    if m.content:
        return m.content[:60]
    if m.image:
        return "Видеосообщение" if m.is_video_circle else "Фото"
    if m.voice:
        return "Голосовое сообщение"
    if m.file_url:
        return m.file_name or "Файл"
    if m.gif_url:
        return "GIF"
    return "Сообщение"


@router.get("/messages")
def messages_list(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    last_ids = (db.query(func.max(models.Message.id))
                .filter(models.Message.group_id == None, or_(models.Message.sender_id == user.id, models.Message.receiver_id == user.id))
                .group_by(func.coalesce(func.nullif(models.Message.sender_id, user.id), models.Message.receiver_id)).all())
    last_msgs = db.query(models.Message).filter(models.Message.id.in_([r[0] for r in last_ids] or [-1])).all()
    unread_rows = dict(db.query(models.Message.sender_id, func.count(models.Message.id)).filter(
        models.Message.receiver_id == user.id, models.Message.is_read == False, models.Message.is_deleted == False,
        models.Message.group_id == None).group_by(models.Message.sender_id).all())
    pinned = {p.pinned_user_id for p in db.query(models.PinnedChat).filter_by(user_id=user.id) if p.pinned_user_id}
    muted = {m.muted_user_id for m in db.query(models.MutedChat).filter_by(user_id=user.id) if m.muted_user_id}
    hidden_cleared = set()
    chats = []
    for m in last_msgs:
        other_id = m.receiver_id if m.sender_id == user.id else m.sender_id
        if other_id in hidden_cleared:
            continue
        other = db.get(models.User, other_id)
        if not other:
            continue
        chats.append({"other": other, "preview": preview_of(m), "mine": m.sender_id == user.id, "time": m.created_at,
                      "unread": unread_rows.get(other_id, 0), "muted": other_id in muted, "pinned": other_id in pinned,
                      "read": m.is_read, "online": social.is_online(other)})
    chats.sort(key=lambda c: (not c["pinned"], -c["time"].timestamp()))
    groups = []
    for gm in db.query(models.GroupMember).filter_by(user_id=user.id).all():
        g = gm.group
        if not g:
            continue
        last = db.query(models.GroupMessage).filter_by(group_id=g.id).order_by(models.GroupMessage.id.desc()).first()
        groups.append({"group": g, "last": last, "time": last.created_at if last else g.created_at})
    groups.sort(key=lambda x: -x["time"].timestamp())
    contacts = db.query(models.User).filter(models.User.id.in_(social.following_ids(db, user) or {-1})).limit(30).all()
    return render(request, db, "messages.html", chats=chats, groups=groups, contacts=contacts)


@router.get("/messages/search")
def message_search(request: Request, q: str = "", db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    results = []
    needle = q.strip().lower()
    if needle:
        # сообщения зашифрованы, поэтому ищем после расшифровки (последние 5000 сообщений пользователя)
        recent = (db.query(models.Message).filter(or_(models.Message.sender_id == user.id, models.Message.receiver_id == user.id),
                                                  models.Message.group_id == None, models.Message.is_deleted == False)
                  .order_by(models.Message.id.desc()).limit(5000).all())
        results = [m for m in recent if m.content and needle in m.content.lower()][:100]
    return render(request, db, "message_search.html", query=q, results=results)


def _load_dialog(db, user, other, after=0, limit=200):
    q = (db.query(models.Message).options(selectinload(models.Message.msg_reactions), selectinload(models.Message.reply_to))
         .filter(dialog_filter(user.id, other.id), _alive()))
    if after:
        q = q.filter(models.Message.id > after)
        return q.order_by(models.Message.id.asc()).all()
    msgs = q.order_by(models.Message.id.desc()).limit(limit).all()
    return list(reversed(msgs))


def _mark_read(db, user, other):
    n = db.query(models.Message).filter(models.Message.sender_id == other.id, models.Message.receiver_id == user.id,
                                        models.Message.group_id == None, models.Message.is_read == False).update(
        {"is_read": True, "is_delivered": True}, synchronize_session=False)
    if n:
        db.commit()


@router.get("/messages/{username}")
def conversation_page(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    other = _get_user(db, username)
    if not other or other.id == user.id:
        return redirect("/messages")
    msgs = _load_dialog(db, user, other)
    _mark_read(db, user, other)
    allowed, reason = social.can_message(db, user, other)
    pinned_msg = db.query(models.Message).filter(dialog_filter(user.id, other.id), models.Message.is_pinned == True,
                                                 models.Message.is_deleted == False).order_by(models.Message.id.desc()).first()
    return render(request, db, "conversation.html", sidebar=False, other=other, messages=msgs, can_send=allowed, block_reason=reason,
                  pinned_msg=pinned_msg, msg_reactions=MSG_REACTIONS,
                  is_muted=db.query(models.MutedChat).filter_by(user_id=user.id, muted_user_id=other.id).first() is not None,
                  is_pinned=db.query(models.PinnedChat).filter_by(user_id=user.id, pinned_user_id=other.id).first() is not None)


def _deliver(db, user, other, msg):
    db.add(msg)
    db.commit()
    gamification.complete_task(user, db, "message")
    muted = db.query(models.MutedChat).filter_by(user_id=other.id, muted_user_id=user.id).first()
    if other.notify_messages is not False and not muted:
        push.send_push_to_user(other.id, db, user.name or user.username, preview_of(msg), f"/messages/{user.username}")
    return JSONResponse({"ok": True, "id": msg.id})


def _precheck(db, user, other):
    if not other:
        return json_error("Пользователь не найден", 404)
    if social.is_active_block(user):
        return json_error("Аккаунт заблокирован", 403)
    if social.needs_email(user):
        return json_error(social.VERIFY_MSG, 403)
    ok, reason = social.can_message(db, user, other)
    if not ok:
        return json_error(reason, 403)
    if not ratelimit.hit(f"msg:{user.id}", 40, 60):
        return json_error("Слишком много сообщений, подождите", 429)
    return None


def _ttl(value):
    try:
        sec = int(value or 0)
    except (TypeError, ValueError):
        return None
    return datetime.utcnow() + timedelta(seconds=sec) if 0 < sec <= 7 * 86400 else None


@router.post("/messages/send")
async def send_message(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    data = await read_payload(request)
    other = _get_user(db, data.get("receiver"))
    err = _precheck(db, user, other)
    if err:
        return err
    content = censor((data.get("sticker_emoji") or data.get("content") or "").strip()[:4000], social.stop_words(db))
    if not content:
        return json_error("Пустое сообщение")
    reply_to = data.get("reply_to_id")
    reply_id = None
    if reply_to and str(reply_to).isdigit():
        r = db.get(models.Message, int(reply_to))
        if r and r.group_id is None and {r.sender_id, r.receiver_id} == {user.id, other.id}:
            reply_id = r.id
    msg = models.Message(sender_id=user.id, receiver_id=other.id, content=content, reply_to_id=reply_id,
                         disappear_at=_ttl(data.get("ttl")), is_delivered=social.is_online(other))
    return _deliver(db, user, other, msg)


@router.post("/messages/send-media")
@router.post("/messages/send-image")
@router.post("/messages/send-voice")
@router.post("/messages/send-file")
async def send_media(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    form = await request.form()
    other = _get_user(db, form.get("receiver"))
    err = _precheck(db, user, other)
    if err:
        return err
    upload = form.get("file") or form.get("image") or form.get("voice") or form.get("video")
    url, mt = save_file(upload)
    if not url:
        return json_error(mt)
    msg = models.Message(sender_id=user.id, receiver_id=other.id, content=(form.get("caption") or "").strip()[:1000],
                         disappear_at=_ttl(form.get("ttl")))
    if mt == "image":
        msg.image = url
    elif mt == "video":
        msg.image = url
        msg.is_video_circle = bool(form.get("circle"))
        if not msg.is_video_circle:
            msg.file_url, msg.file_name, msg.image = url, upload.filename or "video", ""
    elif mt == "audio":
        msg.voice = url
    else:
        msg.file_url, msg.file_name = url, (upload.filename or "file")[:120]
        msg.file_size = 0
    return _deliver(db, user, other, msg)


def render_messages(request, user, msgs):
    return templates.get_template("partials/messages.html").render(request=request, user=user, messages=msgs,
                                                                   msg_reactions=MSG_REACTIONS)


@router.get("/messages/poll/{username}")
def poll_messages(username: str, request: Request, after: int = 0, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return JSONResponse({"ok": False, "messages": []}, status_code=401)
    other = _get_user(db, username)
    if not other:
        return JSONResponse({"ok": False, "messages": []}, status_code=404)
    msgs = _load_dialog(db, user, other, after=after)
    _mark_read(db, user, other)
    last_read = db.query(func.max(models.Message.id)).filter(models.Message.sender_id == user.id, models.Message.receiver_id == other.id,
                                                             models.Message.group_id == None, models.Message.is_read == True).scalar() or 0
    if not prefs.get(other, "read_receipts"):
        last_read = 0
    typing = db.query(models.TypingStatus).filter_by(user_id=other.id, target_id=user.id).first()
    is_typing = bool(typing and (datetime.utcnow() - typing.updated_at).total_seconds() < 6)
    return JSONResponse({"ok": True, "html": render_messages(request, user, msgs) if msgs else "", "ids": [m.id for m in msgs],
                         "last_id": max([after] + [m.id for m in msgs]), "read_upto": last_read, "typing": is_typing,
                         "online": social.is_online(other)})


@router.get("/messages/fragment/{msg_id}")
def message_fragment(msg_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    m = db.get(models.Message, msg_id)
    if not user or not m or user.id not in (m.sender_id, m.receiver_id):
        return json_error("not found", 404)
    return JSONResponse({"ok": True, "html": render_messages(request, user, [m])})


@router.post("/messages/typing/{username}")
def typing(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    other = _get_user(db, username)
    if not user or not other:
        return JSONResponse({"ok": False})
    if not prefs.get(user, "typing_status"):
        return JSONResponse({"ok": True})
    t = db.query(models.TypingStatus).filter_by(user_id=user.id, target_id=other.id).first()
    if t:
        t.updated_at = datetime.utcnow()
    else:
        db.add(models.TypingStatus(user_id=user.id, target_id=other.id))
    db.commit()
    return JSONResponse({"ok": True})


def _own_msg(db, user, msg_id, any_party=False):
    m = db.get(models.Message, msg_id)
    if not m or m.group_id is not None:
        return None
    if any_party and user.id in (m.sender_id, m.receiver_id):
        return m
    return m if m.sender_id == user.id else None


@router.post("/messages/{msg_id}/delete")
def delete_msg(msg_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    m = _own_msg(db, user, msg_id)
    if m:
        m.is_deleted, m.content, m.image, m.voice, m.file_url, m.is_pinned = True, "", "", "", "", False
        db.query(models.MessageReaction).filter_by(message_id=m.id).delete()
        db.commit()
    return JSONResponse({"ok": True})


@router.post("/messages/{msg_id}/edit")
async def edit_msg(msg_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    m = _own_msg(db, user, msg_id)
    if not m or m.is_deleted:
        return json_error("not found", 404)
    if (datetime.utcnow() - m.created_at) > timedelta(hours=48):
        return json_error("Сообщение можно редактировать только 48 часов")
    data = await read_payload(request)
    content = censor((data.get("content") or "").strip()[:4000], social.stop_words(db))
    if not content:
        return json_error("Пустое сообщение")
    m.content, m.is_edited, m.edited_at = content, True, datetime.utcnow()
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/messages/{msg_id}/react")
async def react_msg(msg_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    m = _own_msg(db, user, msg_id, any_party=True)
    if not m or m.is_deleted:
        return json_error("not found", 404)
    data = await read_payload(request)
    emoji = data.get("emoji")
    if emoji not in MSG_REACTIONS:
        return json_error("bad emoji")
    ex = db.query(models.MessageReaction).filter_by(message_id=m.id, user_id=user.id).first()
    if ex and ex.emoji == emoji:
        db.delete(ex)
    elif ex:
        ex.emoji = emoji
    else:
        db.add(models.MessageReaction(message_id=m.id, user_id=user.id, emoji=emoji))
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/messages/{msg_id}/pin")
def pin_msg(msg_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    m = _own_msg(db, user, msg_id, any_party=True)
    if not m:
        return json_error("not found", 404)
    pin = not m.is_pinned
    db.query(models.Message).filter(dialog_filter(m.sender_id, m.receiver_id)).update({"is_pinned": False}, synchronize_session=False)
    m.is_pinned = pin
    db.commit()
    return JSONResponse({"ok": True, "pinned": pin})


@router.post("/messages/{msg_id}/forward")
async def forward_msg(msg_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    m = _own_msg(db, user, msg_id, any_party=True)
    if not m or m.is_deleted:
        return json_error("not found", 404)
    data = await read_payload(request)
    other = _get_user(db, data.get("to"))
    err = _precheck(db, user, other)
    if err:
        return err
    fwd = models.Message(sender_id=user.id, receiver_id=other.id, content=m.content, image=m.image, voice=m.voice,
                         file_url=m.file_url, file_name=m.file_name, is_video_circle=m.is_video_circle,
                         forwarded_from_id=m.forwarded_from_id or m.sender_id)
    return _deliver(db, user, other, fwd)


def _toggle_chat(db, model, user, field, other_id):
    ex = db.query(model).filter(model.user_id == user.id, getattr(model, field) == other_id).first()
    if ex:
        db.delete(ex)
        state = False
    else:
        db.add(model(user_id=user.id, **{field: other_id}))
        state = True
    db.commit()
    return state


@router.post("/chats/pin/{username}")
def pin_chat(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    other = _get_user(db, username)
    if not user or not other:
        return json_error("not found", 404)
    return JSONResponse({"ok": True, "pinned": _toggle_chat(db, models.PinnedChat, user, "pinned_user_id", other.id)})


@router.post("/chats/mute/{username}")
def mute_chat(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    other = _get_user(db, username)
    if not user or not other:
        return json_error("not found", 404)
    return JSONResponse({"ok": True, "muted": _toggle_chat(db, models.MutedChat, user, "muted_user_id", other.id)})


@router.post("/chats/clear/{username}")
def clear_chat(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    other = _get_user(db, username)
    if not user or not other:
        return json_error("not found", 404)
    # удаляем только свои сообщения у обоих, чужие помечаем прочитанными
    db.query(models.Message).filter(dialog_filter(user.id, other.id), models.Message.sender_id == user.id).update(
        {"is_deleted": True, "content": "", "image": "", "voice": "", "file_url": "", "is_pinned": False}, synchronize_session=False)
    db.commit()
    return JSONResponse({"ok": True})
