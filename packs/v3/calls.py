"""Звонки 1 на 1 с видео (WebRTC).

Видео и звук идут напрямую между браузерами собеседников. Сервер только передаёт короткие сигналы
(«звоню» с описанием соединения, «ответил», сетевые адреса, «положил трубку») и мгновенно будит ожидающий
запрос получателя. Если напрямую соединиться нельзя (NAT оператора), браузеры идут через ретранслятор
coturn — ему выдаётся временный пароль на сутки (TURN REST API, общий секрет TURN_SECRET).
"""
import asyncio
import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import config
import models
from database import SessionLocal, get_db
from deps import current_user, json_error
from routers.messages import _get_user, _precheck
from routers.posts import read_payload
from services import chatstyle, push, ratelimit

from . import models as m
from .common import router, s

RING_SECONDS = 45  # сколько звонит, прежде чем стать пропущенным
ALIVE_SECONDS = 120  # разговор без сигналов «на связи» дольше этого считается оборванным
LIVE = ("ringing", "active")

# --------------------------------------------------------------------------- мгновенное пробуждение
_loop = None
_wake_ev = {}  # id пользователя → asyncio.Event: в этом процессе появился сигнал для него


def _wake(uid):
    if _loop is None:
        return

    def _set():
        ev = _wake_ev.get(uid)
        if ev:
            ev.set()
    try:
        _loop.call_soon_threadsafe(_set)
    except RuntimeError:  # цикл уже остановлен (выключение сервера)
        pass


def _signal(db, call, to_id, kind, data=None):
    db.add(m.CallSignal(call_id=call.id, to_id=to_id, kind=kind, data=json.dumps(data or {}, ensure_ascii=False)[:60000]))


def ice_servers(user):
    servers = [{"urls": config.STUN_URLS}] if config.STUN_URLS else []
    if config.TURN_SECRET:
        host = config.TURN_HOST or urlparse(config.SITE_URL).hostname or "localhost"
        name = f"{int(time.time()) + 86400}:{user.id}"
        cred = base64.b64encode(hmac.new(config.TURN_SECRET.encode(), name.encode(), hashlib.sha1).digest()).decode()
        servers.append({"urls": [f"turn:{host}:3478?transport=udp", f"turn:{host}:3478?transport=tcp"], "username": name, "credential": cred})
    return servers


def _who(db, viewer, u):
    names = chatstyle.load_names(db, viewer)
    return {"username": u.username, "name": names.get(u.id) or u.name or u.username, "avatar": u.avatar or ""}


# --------------------------------------------------------------------------- завершение звонка
def _finish(db, call, status, by_id=None):
    """Закрыть звонок: сигнал «конец» обоим, запись в переписке, уведомление о пропущенном."""
    if call.status not in LIVE:
        return
    was_active = call.status == "active"
    call.status = "ended" if was_active else status
    call.ended_at = datetime.utcnow()
    for uid in (call.caller_id, call.callee_id):
        _signal(db, call, uid, "end", {"call": call.id, "status": call.status, "by": by_id})
    n = db.get(models.Notification, call.notif_id) if call.notif_id else None
    if n:
        if call.status == "missed":
            n.text = "пропущенный видеозвонок" if call.video else "пропущенный звонок"
        else:
            db.delete(n)
    db.add(models.Message(sender_id=call.caller_id, receiver_id=call.callee_id, content=f"[[v3:call:{call.id}]]",
                          is_delivered=True, silent=True, is_read=call.status != "missed"))
    db.commit()
    _wake(call.caller_id)
    _wake(call.callee_id)


def _expire(db):
    """Звонки, на которые не ответили, и разговоры, где оба пропали со связи."""
    now = datetime.utcnow()
    for c in db.query(m.Call).filter(m.Call.status == "ringing", m.Call.created_at < now - timedelta(seconds=RING_SECONDS + 10)).all():
        _finish(db, c, "missed")
    for c in db.query(m.Call).filter(m.Call.status == "active", m.Call.alive_at < now - timedelta(seconds=ALIVE_SECONDS)).all():
        _finish(db, c, "ended")
    db.query(m.CallSignal).filter(m.CallSignal.created_at < now - timedelta(hours=1)).delete()
    db.commit()


def expire_job(db):
    _expire(db)


def _busy(db, uid):
    return db.query(m.Call.id).filter(m.Call.status.in_(LIVE), or_(m.Call.caller_id == uid, m.Call.callee_id == uid)).first() is not None


# --------------------------------------------------------------------------- маршруты
@router.post("/v3/call/{username}/start")
async def call_start(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    if not config.CALLS_ENABLED:
        return json_error("Звонки временно недоступны", 403)
    other = _get_user(db, username)
    if not other or other.id == user.id:
        return json_error("Пользователь не найден", 404)
    err = _precheck(db, user, other)
    if err:
        return err
    if not ratelimit.hit(f"call:{user.id}", 12, 600):
        return json_error("Слишком много звонков подряд, подождите немного", 429)
    data = await read_payload(request)
    offer = data.get("offer")
    if not isinstance(offer, dict) or offer.get("type") != "offer" or not isinstance(offer.get("sdp"), str) or len(offer["sdp"]) > 30000:
        return json_error("Не удалось начать звонок")
    _expire(db)
    if _busy(db, user.id):
        return json_error("Сначала завершите текущий звонок")
    video = s(data.get("video")) in ("1", "true", "True")
    if _busy(db, other.id):
        call = m.Call(caller_id=user.id, callee_id=other.id, video=video, status="busy", ended_at=datetime.utcnow())
        db.add(call)
        db.flush()
        db.add(models.Message(sender_id=user.id, receiver_id=other.id, content=f"[[v3:call:{call.id}]]", is_delivered=True, silent=True, is_read=True))
        db.commit()
        return json_error(f"{other.name or other.username} сейчас разговаривает")
    call = m.Call(caller_id=user.id, callee_id=other.id, video=video)
    db.add(call)
    db.flush()
    n = models.Notification(user_id=other.id, from_user_id=user.id, type="call", text="видеозвонок — нажмите, чтобы ответить" if video else "звонит вам — нажмите, чтобы ответить")
    db.add(n)
    db.flush()
    call.notif_id = n.id
    _signal(db, call, other.id, "ring", {"call": call.id, "video": video, "offer": {"type": "offer", "sdp": offer["sdp"]},
                                         "from": _who(db, other, user)})
    db.commit()
    _wake(other.id)
    push.send_push_to_user(other.id, db, user.name or user.username, "Видеозвонок" if video else "Звонок", f"/messages/{user.username}?call={call.id}")
    return JSONResponse({"ok": True, "call": call.id, "peer": _who(db, user, other)})


@router.post("/v3/call/{call_id}/signal")
async def call_signal(call_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    call = db.get(m.Call, call_id)
    if not user or not call or user.id not in (call.caller_id, call.callee_id):
        return json_error("Звонок не найден", 404)
    data = await read_payload(request)
    kind = s(data.get("kind"))
    tab = s(data.get("tab"))[:40]
    other_id = call.callee_id if user.id == call.caller_id else call.caller_id
    if call.status not in LIVE:
        return JSONResponse({"ok": True, "ended": True, "status": call.status})
    if kind == "answer":
        ans = data.get("answer")
        if user.id != call.callee_id or call.status != "ringing" or not isinstance(ans, dict) or not isinstance(ans.get("sdp"), str) or len(ans["sdp"]) > 30000:
            return json_error("Звонок уже не активен")
        call.status, call.answered_at, call.alive_at = "active", datetime.utcnow(), datetime.utcnow()
        n = db.get(models.Notification, call.notif_id) if call.notif_id else None
        if n:
            db.delete(n)
            call.notif_id = None
        _signal(db, call, other_id, "answer", {"call": call.id, "answer": {"type": "answer", "sdp": ans["sdp"]}})
        _signal(db, call, user.id, "taken", {"call": call.id, "tab": tab})  # другие вкладки перестают звонить
    elif kind == "ice":
        cands = data.get("candidates")
        if not isinstance(cands, list):
            return json_error("bad")
        cands = [c for c in cands if isinstance(c, dict) and isinstance(c.get("candidate"), str) and len(c["candidate"]) < 600][:40]
        _signal(db, call, other_id, "ice", {"call": call.id, "candidates": cands, "from_tab": tab})
    elif kind == "media":
        _signal(db, call, other_id, "media", {"call": call.id, "cam": bool(data.get("cam")), "mic": bool(data.get("mic"))})
    elif kind == "ping":
        call.alive_at = datetime.utcnow()
    elif kind == "decline" and user.id == call.callee_id and call.status == "ringing":
        _finish(db, call, "declined", user.id)
        return JSONResponse({"ok": True})
    elif kind == "hangup":
        _finish(db, call, "missed", user.id)
        return JSONResponse({"ok": True})
    else:
        return json_error("bad")
    db.commit()
    _wake(other_id)
    if kind == "answer":
        _wake(user.id)
    return JSONResponse({"ok": True})


@router.get("/v3/call/poll")
async def call_poll(request: Request, since: int = -1, wait: int = 25):
    """Долгий запрос: отвечает сразу, как только для пользователя появился сигнал звонка (или через 25 секунд)."""
    global _loop
    _loop = asyncio.get_running_loop()
    db = SessionLocal()
    try:
        user = current_user(request, db)
        if not user:
            return JSONResponse({"ok": False}, status_code=401)
        uid = user.id
        if since < 0:  # первая проверка: текущий конец очереди, но звонок, который уже идёт, показываем
            ring = (db.query(m.CallSignal.id).join(m.Call, m.Call.id == m.CallSignal.call_id)
                    .filter(m.CallSignal.to_id == uid, m.CallSignal.kind == "ring", m.Call.status == "ringing",
                            m.Call.created_at > datetime.utcnow() - timedelta(seconds=RING_SECONDS)).order_by(m.CallSignal.id.desc()).first())
            since = ring[0] - 1 if ring else (db.query(func.max(m.CallSignal.id)).scalar() or 0)
            if not ring:
                return JSONResponse({"ok": True, "last": since, "events": [], "ice": ice_servers(user)})
    finally:
        db.close()

    def fetch():
        d = SessionLocal()
        try:
            return [{"id": r.id, "kind": r.kind, **json.loads(r.data or "{}")}
                    for r in d.query(m.CallSignal).filter(m.CallSignal.to_id == uid, m.CallSignal.id > since).order_by(m.CallSignal.id).limit(50)]
        finally:
            d.close()

    ev = _wake_ev.setdefault(uid, asyncio.Event())
    deadline = _loop.time() + max(1, min(wait, 25))
    while True:
        ev.clear()
        rows = await _loop.run_in_executor(None, fetch)
        left = deadline - _loop.time()
        if rows or left <= 0 or await request.is_disconnected():
            return JSONResponse({"ok": True, "last": rows[-1]["id"] if rows else since, "events": rows})
        try:  # проснуться от сигнала в этом процессе; раз в 4 секунды — проверка базы (на случай нескольких процессов)
            await asyncio.wait_for(ev.wait(), timeout=min(4, left))
        except asyncio.TimeoutError:
            pass


@router.get("/v3/call/ice")
def call_ice(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    return JSONResponse({"ok": True, "ice": ice_servers(user)})


# --------------------------------------------------------------------------- карточка в переписке
def card_data(db, call, user):
    out = user and user.id == call.caller_id
    dur = int((call.ended_at - call.answered_at).total_seconds()) if call.answered_at and call.ended_at else 0
    label = {"ended": "", "missed": "Пропущенный" if not out else "Не ответили", "declined": "Отклонён", "busy": "Занято"}.get(call.status, "Идёт звонок")
    title = ("Исходящий " if out else "Входящий ") + ("видеозвонок" if call.video else "звонок")
    return {"title": title, "label": label, "dur": f"{dur // 60}:{dur % 60:02d}" if dur else "", "out": out,
            "bad": call.status in ("missed", "declined", "busy"), "video": call.video}
