"""Секретные чаты со сквозным шифрованием по ГОСТ.

Вся криптография выполняется в браузере (static/js/secret.js + static/js/gost.js):
- у каждого участника для каждого чата своя пара ключей ГОСТ Р 34.10-2012 (256 бит), закрытый ключ не покидает устройство;
- общий ключ — VKO ГОСТ Р 34.10-2012, из него через HMAC «Стрибог» (ГОСТ Р 34.11-2012) получаются ключ шифрования и ключ имитовставки;
- сообщения шифруются «Кузнечиком» (ГОСТ Р 34.12-2015) в режиме гаммирования CTR и защищаются имитовставкой MAC (ГОСТ Р 34.13-2015).

Сервер видит только открытые ключи, время отправки и непрозрачный шифротекст — прочитать переписку он не может.
"""
import base64
import re
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

import config
import models
from database import get_db
from deps import current_user, json_error, login_redirect, redirect, render
from routers.posts import read_payload
from services import push, ratelimit, social

router = APIRouter()

HEX_PUB = re.compile(r"^[0-9a-f]{128}$")
TTLS = [(0, "Выключен"), (30, "30 секунд"), (300, "5 минут"), (3600, "1 час"), (86400, "1 день"), (604800, "1 неделя")]
TTL_KEYS = {t for t, _ in TTLS}
MAX_PAYLOAD = 64 * 1024  # base64; текст сообщения до 10 000 символов


def _chat_for(db, user, chat_id):
    chat = db.get(models.SecretChat, chat_id)
    if not chat or not user or user.id not in (chat.a_id, chat.b_id) or chat.status == "closed":
        return None
    return chat


def _peer_id(chat, user):
    return chat.b_id if chat.a_id == user.id else chat.a_id


def purge(db):
    """Самоуничтожение: истёкшие сообщения скрываются сразу, а удаляются с сервера через SECRET_RETAIN_DAYS."""
    now = datetime.utcnow()
    db.query(models.SecretMessage).filter(models.SecretMessage.expires_at != None, models.SecretMessage.expires_at <= now,
                                          models.SecretMessage.hidden == False).update({"hidden": True}, synchronize_session=False)
    keep = now - timedelta(days=config.SECRET_RETAIN_DAYS)
    db.query(models.SecretMessage).filter(models.SecretMessage.hidden == True,
                                          or_(models.SecretMessage.expires_at == None, models.SecretMessage.expires_at <= keep)
                                          ).delete(synchronize_session=False)
    db.commit()


def _disabled():
    return not config.SECRET_CHATS_ENABLED


@router.get("/secret")
def secret_list(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    chats = (db.query(models.SecretChat).filter(or_(models.SecretChat.a_id == user.id, models.SecretChat.b_id == user.id),
                                                models.SecretChat.status != "closed")
             .order_by(models.SecretChat.last_at.desc()).limit(100).all())
    peers = {u.id: u for u in db.query(models.User).filter(models.User.id.in_([_peer_id(c, user) for c in chats] or [-1]))}
    return render(request, db, "secret_list.html", chats=chats, peers=peers, ttls=TTLS, disabled=_disabled(),
                  start=request.query_params.get("u", ""))


@router.post("/secret/start")
async def secret_start(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("Войдите в аккаунт", 401)
    if _disabled():
        return json_error("Секретные чаты отключены администратором")
    data = await read_payload(request)
    pub = str(data.get("pub", "")).lower()
    ukm = secrets.token_hex(8)
    try:
        ttl = int(data.get("ttl") or 0)
    except (TypeError, ValueError):
        ttl = 0
    if not HEX_PUB.match(pub):
        return json_error("Некорректный открытый ключ")
    if ttl not in TTL_KEYS:
        ttl = 0
    from sqlalchemy import func as _f
    peer = db.query(models.User).filter(_f.lower(models.User.username) == str(data.get("username", "")).strip().lstrip("@").lower()).first()
    if not peer:
        return json_error("Пользователь не найден")
    ok, why = social.can_message(db, user, peer)
    if not ok:
        return json_error(why)
    if not ratelimit.hit(f"secret-start:{user.id}", 20, 3600):
        return json_error("Слишком много новых секретных чатов. Попробуйте позже", 429)
    chat = models.SecretChat(a_id=user.id, b_id=peer.id, a_pub=pub, ukm=ukm, ttl=ttl)
    db.add(chat)
    db.commit()
    push.send_push_to_user(peer.id, db, "Секретный чат", f"@{user.username} приглашает в секретный чат", f"/secret/{chat.id}")
    return {"ok": True, "id": chat.id, "ukm": ukm}


@router.get("/secret/{chat_id}")
def secret_page(chat_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    chat = _chat_for(db, user, chat_id)
    if not chat:
        return redirect("/secret")
    peer = db.get(models.User, _peer_id(chat, user))
    if _disabled():
        return render(request, db, "secret_list.html", chats=[chat], peers={peer.id: peer} if peer else {}, ttls=TTLS, disabled=True, start="")
    return render(request, db, "secret_chat.html", chat=chat, peer=peer, ttl_label=dict(TTLS).get(chat.ttl, ""), ttls=TTLS)


@router.get("/secret/{chat_id}/state")
def secret_state(chat_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    chat = _chat_for(db, user, chat_id)
    if not chat:
        return json_error("Чат не найден", 404)
    return {"ok": True, "id": chat.id, "status": chat.status, "a_pub": chat.a_pub, "b_pub": chat.b_pub, "ukm": chat.ukm,
            "me": user.id, "a_id": chat.a_id, "b_id": chat.b_id, "ttl": chat.ttl}


@router.post("/secret/{chat_id}/accept")
async def secret_accept(chat_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    chat = _chat_for(db, user, chat_id)
    if not chat:
        return json_error("Чат не найден", 404)
    if _disabled():
        return json_error("Секретные чаты отключены администратором")
    if chat.b_id != user.id or chat.status != "pending":
        return json_error("Чат уже начат")
    pub = str((await read_payload(request)).get("pub", "")).lower()
    if not HEX_PUB.match(pub) or pub == chat.a_pub:
        return json_error("Некорректный открытый ключ")
    chat.b_pub, chat.status, chat.last_at = pub, "active", datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.get("/secret/{chat_id}/messages")
def secret_messages(chat_id: int, request: Request, after: int = 0, db: Session = Depends(get_db)):
    user = current_user(request, db)
    chat = _chat_for(db, user, chat_id)
    if not chat:
        return json_error("Чат не найден", 404)
    purge(db)
    rows = (db.query(models.SecretMessage).filter(models.SecretMessage.chat_id == chat.id, models.SecretMessage.id > after,
                                                  models.SecretMessage.hidden == False)
            .order_by(models.SecretMessage.id).limit(200).all())
    alive = [m.id for m in db.query(models.SecretMessage.id).filter(models.SecretMessage.chat_id == chat.id,
                                                                    models.SecretMessage.hidden == False)]
    return {"ok": True, "status": chat.status, "b_pub": chat.b_pub, "alive": alive,
            "messages": [{"id": m.id, "sender": m.sender_id, "payload": m.payload, "at": m.created_at.isoformat() + "Z",
                          "expires": m.expires_at.isoformat() + "Z" if m.expires_at else None} for m in rows]}


@router.post("/secret/{chat_id}/send")
async def secret_send(chat_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    chat = _chat_for(db, user, chat_id)
    if not chat:
        return json_error("Чат не найден", 404)
    if _disabled():
        return json_error("Секретные чаты отключены администратором")
    if chat.status != "active":
        return json_error("Собеседник ещё не принял приглашение")
    peer = db.get(models.User, _peer_id(chat, user))
    if not peer or social.is_blocked_between(db, user, peer):
        return json_error("Пользователь недоступен")
    payload = str((await read_payload(request)).get("payload", ""))
    try:
        raw = base64.b64decode(payload, validate=True)
    except ValueError:
        return json_error("Сообщение повреждено")
    if len(payload) > MAX_PAYLOAD or len(raw) < 8 + 16 + 1:
        return json_error("Сообщение слишком длинное" if len(payload) > MAX_PAYLOAD else "Сообщение повреждено")
    if not ratelimit.hit(f"secret-send:{user.id}", 60, 60):
        return json_error("Слишком часто. Подождите немного", 429)
    now = datetime.utcnow()
    msg = models.SecretMessage(chat_id=chat.id, sender_id=user.id, payload=payload, created_at=now,
                               expires_at=now + timedelta(seconds=chat.ttl) if chat.ttl else None)
    chat.last_at = now
    db.add(msg)
    db.commit()
    # текст зашифрован — в пуше его быть не может
    push.send_push_to_user(peer.id, db, "Секретный чат", "Новое сообщение", f"/secret/{chat.id}")
    return {"ok": True, "id": msg.id}


@router.post("/secret/{chat_id}/ttl")
async def secret_ttl(chat_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    chat = _chat_for(db, user, chat_id)
    if not chat:
        return json_error("Чат не найден", 404)
    try:
        ttl = int((await read_payload(request)).get("ttl") or 0)
    except (TypeError, ValueError):
        ttl = -1
    if ttl not in TTL_KEYS:
        return json_error("Недопустимый таймер")
    chat.ttl = ttl
    db.commit()
    return {"ok": True, "ttl": ttl}


@router.post("/secret/{chat_id}/delete")
def secret_delete(chat_id: int, request: Request, db: Session = Depends(get_db)):
    """Удаляет чат у обоих участников (как в Telegram)."""
    user = current_user(request, db)
    chat = _chat_for(db, user, chat_id)
    if chat:
        chat.status = "closed"
        now = datetime.utcnow()
        db.query(models.SecretMessage).filter(models.SecretMessage.chat_id == chat.id).update(
            {"hidden": True, "expires_at": now}, synchronize_session=False)
        db.commit()
        purge(db)
    if "application/json" in request.headers.get("accept", "") or request.headers.get("x-requested-with"):
        return JSONResponse({"ok": True})
    return redirect("/secret")
