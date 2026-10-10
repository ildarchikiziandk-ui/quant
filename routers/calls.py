"""Аудио/видеозвонки: сигналинг WebRTC через HTTP-поллинг (хранилище в памяти процесса)."""
import secrets
import time
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import config
import models
from database import get_db
from deps import current_user, json_error, login_redirect, redirect, render
from routers.posts import read_payload
from services import push, social

router = APIRouter()
CALLS = {}
RING_TIMEOUT = 45


def ice_servers():
    servers = [{"urls": "stun:stun.l.google.com:19302"}, {"urls": "stun:stun1.l.google.com:19302"}]
    if config.TURN_URL:
        servers.append({"urls": config.TURN_URL, "username": config.TURN_USERNAME, "credential": config.TURN_CREDENTIAL})
    return servers


def _cleanup():
    now = time.time()
    for cid in [c for c, v in CALLS.items() if now - v["created"] > 3 * 3600 or (v["status"] in ("ended", "rejected", "missed") and now - v["updated"] > 120)]:
        CALLS.pop(cid, None)


def _finish(db, call, status):
    if call.get("logged"):
        return
    call["logged"] = True
    duration = int(time.time() - call["started"]) if call.get("started") else 0
    final = "completed" if call.get("started") else ("rejected" if status == "rejected" else "missed")
    db.add(models.CallLog(caller_id=call["caller_id"], receiver_id=call["receiver_id"], call_type=call["type"], status=final, duration=duration))
    if final == "missed":
        caller = db.get(models.User, call["caller_id"])
        db.add(models.Notification(user_id=call["receiver_id"], from_user_id=call["caller_id"], type="call",
                                   text=f"Пропущенный {'видео' if call['type'] == 'video' else 'аудио'}звонок"))
        if caller:
            push.send_push_to_user(call["receiver_id"], db, config.BRAND_NAME, f"Пропущенный звонок от {caller.name or caller.username}", "/calls")
    db.commit()


def _get_call(request, db, call_id):
    user = current_user(request, db)
    call = CALLS.get(call_id)
    if not user or not call or user.id not in (call["caller_id"], call["receiver_id"]):
        return None, None, None
    role = "caller" if user.id == call["caller_id"] else "callee"
    return user, call, role


@router.get("/call/{call_type}/{username}")
def call_page(call_type: str, username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    if call_type not in ("voice", "video"):
        return redirect("/messages")
    other = db.query(models.User).filter(func.lower(models.User.username) == username.lower()).first()
    if not other or other.id == user.id:
        return redirect("/messages")
    ok, reason = social.can_message(db, user, other)
    if not ok:
        return render(request, db, "error.html", status_code=403, code=403, title="Звонок недоступен", text=reason)
    _cleanup()
    call_id = secrets.token_urlsafe(12)
    now = time.time()
    CALLS[call_id] = {"caller_id": user.id, "receiver_id": other.id, "type": call_type, "status": "ringing", "offer": None,
                      "answer": None, "ice": {"caller": [], "callee": []}, "created": now, "updated": now, "started": None}
    push.send_push_to_user(other.id, db, config.BRAND_NAME, f"📞 Входящий звонок от {user.name or user.username}", f"/call/join/{call_id}")
    return render(request, db, "call.html", sidebar=False, other=other, call_type=call_type, call_id=call_id, role="caller",
                  ice_servers=ice_servers())


@router.get("/call/join/{call_id}")
def call_join(call_id: str, request: Request, db: Session = Depends(get_db)):
    user, call, role = _get_call(request, db, call_id)
    if not user or role != "callee" or call["status"] not in ("ringing", "accepted"):
        return redirect("/calls")
    other = db.get(models.User, call["caller_id"])
    return render(request, db, "call.html", sidebar=False, other=other, call_type=call["type"], call_id=call_id, role="callee",
                  ice_servers=ice_servers())


@router.get("/api/calls/incoming")
def incoming(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return JSONResponse({"ok": False})
    now = time.time()
    for cid, c in CALLS.items():
        if c["receiver_id"] == user.id and c["status"] == "ringing":
            if now - c["created"] > RING_TIMEOUT:
                c["status"], c["updated"] = "missed", now
                _finish(db, c, "missed")
                continue
            caller = db.get(models.User, c["caller_id"])
            return JSONResponse({"ok": True, "call": {"id": cid, "type": c["type"], "from": caller.name or caller.username,
                                                      "username": caller.username, "avatar": caller.avatar or ""}})
    return JSONResponse({"ok": True, "call": None})


@router.post("/api/call/{call_id}/offer")
async def call_offer(call_id: str, request: Request, db: Session = Depends(get_db)):
    user, call, role = _get_call(request, db, call_id)
    if not call or role != "caller":
        return json_error("not found", 404)
    data = await read_payload(request)
    call["offer"], call["updated"] = data.get("offer"), time.time()
    return JSONResponse({"ok": True})


@router.post("/api/call/{call_id}/answer")
async def call_answer(call_id: str, request: Request, db: Session = Depends(get_db)):
    user, call, role = _get_call(request, db, call_id)
    if not call or role != "callee" or call["status"] != "ringing":
        return json_error("not found", 404)
    data = await read_payload(request)
    call["answer"], call["status"], call["started"], call["updated"] = data.get("answer"), "accepted", time.time(), time.time()
    return JSONResponse({"ok": True})


@router.post("/api/call/{call_id}/ice")
async def call_ice(call_id: str, request: Request, db: Session = Depends(get_db)):
    user, call, role = _get_call(request, db, call_id)
    if not call:
        return json_error("not found", 404)
    data = await read_payload(request)
    if data.get("candidate") and len(call["ice"][role]) < 200:
        call["ice"][role].append(data["candidate"])
    return JSONResponse({"ok": True})


@router.get("/api/call/{call_id}/status")
def call_status(call_id: str, request: Request, since: int = 0, db: Session = Depends(get_db)):
    user, call, role = _get_call(request, db, call_id)
    if not call:
        return JSONResponse({"ok": True, "status": "ended"})
    if call["status"] == "ringing" and time.time() - call["created"] > RING_TIMEOUT:
        call["status"], call["updated"] = "missed", time.time()
        _finish(db, call, "missed")
    peer = "callee" if role == "caller" else "caller"
    ice = call["ice"][peer][since:]
    return JSONResponse({"ok": True, "status": call["status"], "offer": call["offer"] if role == "callee" else None,
                         "answer": call["answer"] if role == "caller" else None, "ice": ice, "next": since + len(ice)})


@router.post("/api/call/{call_id}/reject")
def call_reject(call_id: str, request: Request, db: Session = Depends(get_db)):
    user, call, role = _get_call(request, db, call_id)
    if call and call["status"] == "ringing":
        call["status"], call["updated"] = "rejected", time.time()
        _finish(db, call, "rejected")
    return JSONResponse({"ok": True})


@router.post("/api/call/{call_id}/end")
def call_end(call_id: str, request: Request, db: Session = Depends(get_db)):
    user, call, role = _get_call(request, db, call_id)
    if call and call["status"] not in ("ended",):
        prev = call["status"]
        call["status"], call["updated"] = "ended", time.time()
        _finish(db, call, "missed" if prev == "ringing" else "ended")
    return JSONResponse({"ok": True})


@router.get("/calls")
def calls_history(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    logs = (db.query(models.CallLog).filter(or_(models.CallLog.caller_id == user.id, models.CallLog.receiver_id == user.id))
            .order_by(models.CallLog.created_at.desc()).limit(100).all())
    return render(request, db, "calls.html", logs=logs)
