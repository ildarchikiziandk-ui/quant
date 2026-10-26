"""Подтверждение входа на телефоне.

Кто включил эту защиту (у владельца она включена сразу), входит в два шага: пароль (и код 2FA, если он есть),
а потом «Да, это я» на уже открытой Nuvora — обычно в приложении на телефоне. На всех открытых сеансах
появляется уведомление «Вход с … Это вы?»; без ответа вход не завершается, «Нет» его отклоняет.

Чтобы не запереть себя:
- если открытых сеансов нет (никто не может подтвердить), вход проходит как обычно;
- с ожидающей страницы можно войти по резервному коду 2FA;
- сеансы, которыми не пользовались 14 дней, не считаются — потерянный телефон перестаёт быть нужен.
"""
import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import Depends, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import config
import models
from database import get_db
from deps import current_user, json_error, redirect, render

from . import models as m
from . import site
from .common import router

COOKIE = "login_wait"
TTL = timedelta(minutes=3)
SESSION_FRESH = timedelta(days=14)


def _h(raw):
    return hashlib.sha256(f"{config.SECRET_KEY}:la:{raw}".encode()).hexdigest()


def enabled(user):
    """Подтверждение входа на телефоне убрано: из-за него владелец не мог войти. Вход — пароль (и код 2FA)."""
    return False


def set_enabled(db, user, on):
    off, yes = set(site.get("login_approve_off") or ()), set(site.get("login_approve_on") or ())
    if on:
        off.discard(user.id)
        if not user.is_owner:
            yes.add(user.id)
    else:
        off.add(user.id)
        yes.discard(user.id)
    site.put(db, "login_approve_off", sorted(off))
    site.put(db, "login_approve_on", sorted(yes))


def _approvers(db, user):
    since = datetime.utcnow() - SESSION_FRESH
    return (db.query(models.UserSession.id)
            .filter(models.UserSession.user_id == user.id, models.UserSession.is_active == True,
                    models.UserSession.last_active >= since).count())


def _ip(request):
    return (request.client.host if request.client else "")[:64]


def intercept(request, db, user, next_url):
    """Вызывается перед созданием сеанса. Возвращает страницу ожидания или None — тогда вход идёт как обычно."""
    if not enabled(user) or not _approvers(db, user):
        return None
    import auth
    raw = secrets.token_urlsafe(24)
    dev = auth._device_from_ua(request.headers.get("user-agent", ""))[:120] or "неизвестное устройство"
    row = m.LoginApproval(user_id=user.id, token_hash=_h(raw), device=dev, ip=_ip(request), next_url=(next_url or "/")[:300])
    db.add(row)
    db.flush()
    n = models.Notification(user_id=user.id, type="login_approve",
                            text=f"Вход с устройства «{dev}». Это вы? Нажмите, чтобы ответить")
    db.add(n)
    db.flush()
    row.notif_id = n.id
    db.commit()
    resp = render(request, db, "packs/v3/login_wait.html", sidebar=False, device=dev,
                  backup=bool(user.two_factor_enabled))
    resp.set_cookie(COOKIE, raw, max_age=int(TTL.total_seconds()) + 60, httponly=True, samesite="lax", secure=config.COOKIE_SECURE)
    resp.delete_cookie("pending_2fa")
    return resp


def _waiting(request, db):
    raw = request.cookies.get(COOKIE, "")
    if not raw:
        return None
    return db.query(m.LoginApproval).filter_by(token_hash=_h(raw)).first()


def _expired(row):
    return row.status == "pending" and datetime.utcnow() - row.created_at > TTL


def _close(db, row, status):
    row.status = status
    row.decided_at = datetime.utcnow()
    n = db.get(models.Notification, row.notif_id) if row.notif_id else None
    if n:
        n.is_read = True
        n.text = {"approved": "Вход подтверждён", "denied": "Вход отклонён", "expired": "Запрос на вход истёк"}.get(status, n.text) + f": {row.device}"


# ---------------------------------------------------------------- устройство, которое входит
@router.get("/login/wait/status")
def wait_status(request: Request, db: Session = Depends(get_db)):
    row = _waiting(request, db)
    if not row:
        return JSONResponse({"state": "gone"})
    if _expired(row):
        _close(db, row, "expired")
        db.commit()
    return JSONResponse({"state": row.status})


@router.post("/login/wait/finish")
def wait_finish(request: Request, db: Session = Depends(get_db)):
    row = _waiting(request, db)
    if not row or row.status != "approved":
        return redirect("/login")
    user = db.get(models.User, row.user_id)
    row.status = "used"  # одно подтверждение — один вход
    db.commit()
    from routers.auth_routes import _finish_login
    resp = _finish_login(request, db, user, row.next_url, approved=True)
    resp.delete_cookie(COOKIE)
    return resp


@router.post("/login/wait/backup")
def wait_backup(request: Request, code: str = Form(...), db: Session = Depends(get_db)):
    """Нет доступа к телефону — вход по резервному коду 2FA."""
    from services import ratelimit
    row = _waiting(request, db)
    if not row or row.status != "pending" or _expired(row):
        return redirect("/login")
    user = db.get(models.User, row.user_id)
    if not ratelimit.hit(f"2fa:{user.id}", 6, 300):
        return render(request, db, "packs/v3/login_wait.html", sidebar=False, device=row.device, backup=True, error="Слишком много попыток")
    from .account import use_backup_code
    if not user.two_factor_enabled or not use_backup_code(db, user, code):
        return render(request, db, "packs/v3/login_wait.html", sidebar=False, device=row.device, backup=True, error="Неверный резервный код")
    _close(db, row, "approved")
    row.status = "used"
    db.commit()
    from routers.auth_routes import _finish_login
    resp = _finish_login(request, db, user, row.next_url, approved=True)
    resp.delete_cookie(COOKIE)
    return resp


# ---------------------------------------------------------------- телефон, который подтверждает
def _pending_for(db, user):
    rows = (db.query(m.LoginApproval).filter_by(user_id=user.id, status="pending")
            .order_by(m.LoginApproval.id.desc()).limit(5).all())
    out = []
    for r in rows:
        if _expired(r):
            _close(db, r, "expired")
        else:
            out.append(r)
    db.commit()
    return out


def _view(r):
    return {"id": r.id, "device": r.device, "ip": r.ip, "at": r.created_at.strftime("%H:%M")}


@router.get("/login-approve")
def approve_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return redirect("/login")
    return render(request, db, "packs/v3/login_approve.html", rows=[_view(r) for r in _pending_for(db, user)])


@router.get("/login-approve/pending")
def approve_pending(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    return JSONResponse({"rows": [_view(r) for r in _pending_for(db, user)]})


@router.post("/login-approve/{rid}")
def approve_decide(rid: int, request: Request, decision: str = Form(...), db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    row = db.get(m.LoginApproval, rid)
    if not row or row.user_id != user.id:
        return json_error("Запрос не найден", 404)
    if row.status != "pending" or _expired(row):
        if _expired(row):
            _close(db, row, "expired")
            db.commit()
        return json_error("Запрос уже неактуален — попробуйте войти ещё раз")
    yes = decision == "yes"
    _close(db, row, "approved" if yes else "denied")
    if not yes:
        db.add(models.Notification(user_id=user.id, type="security",
                                   text=f"Вы отклонили вход с устройства «{row.device}». Если это были не вы, кто-то знает ваш пароль — смените его."))
    db.commit()
    return JSONResponse({"ok": True, "state": row.status})


@router.post("/v3/login-approval")
def toggle(request: Request, on: str = Form(""), db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    set_enabled(db, user, on in ("1", "true", "on"))
    db.commit()
    return JSONResponse({"ok": True, "on": enabled(user)})
