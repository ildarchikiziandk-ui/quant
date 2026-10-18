"""Безопасность и удобство 3.0: резервные коды 2FA, уведомление о входе с нового устройства, центр помощи."""
import hashlib
import secrets

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import config
import models
from database import get_db
from deps import current_user, json_error, render

from . import models as m
from .common import router
from .help import ARTICLES


def _h(user_id, code):
    return hashlib.sha256(f"{config.SECRET_KEY}:{user_id}:{code}".encode()).hexdigest()


def _norm(code):
    return "".join(ch for ch in str(code or "") if ch.isdigit())


# ---------------------------------------------------------------- резервные коды
@router.post("/v3/backup-codes")
def backup_codes(request: Request, db: Session = Depends(get_db)):
    """Новые 10 резервных кодов (старые перестают работать). Показываются один раз."""
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    if not user.two_factor_enabled:
        return json_error("Сначала включите двухфакторную защиту")
    db.query(m.BackupCode).filter_by(user_id=user.id).delete()
    codes = []
    for _ in range(10):
        c = "".join(secrets.choice("0123456789") for _ in range(8))
        codes.append(f"{c[:4]}-{c[4:]}")
        db.add(m.BackupCode(user_id=user.id, code_hash=_h(user.id, c)))
    db.commit()
    return JSONResponse({"ok": True, "codes": codes})


def backup_left(user):
    from database import SessionLocal
    if not user:
        return 0
    db = SessionLocal()
    try:
        return db.query(m.BackupCode).filter_by(user_id=user.id, used=False).count()
    finally:
        db.close()


def use_backup_code(db, user, code):
    """Вход по резервному коду: код одноразовый."""
    c = _norm(code)
    if len(c) != 8:
        return False
    row = db.query(m.BackupCode).filter_by(user_id=user.id, code_hash=_h(user.id, c), used=False).first()
    if not row:
        return False
    row.used = True
    db.add(models.Notification(user_id=user.id, type="security", text="Выполнен вход по резервному коду. Если это были не вы — смените пароль."))
    db.commit()
    return True


# ---------------------------------------------------------------- вход с нового устройства
def new_device_alerts(db):
    """Фоновая задача: новый сеанс с устройства, с которого человек раньше не входил, — уведомление."""
    last = db.query(m.SeenDevice).filter_by(user_id=0).first()  # служебная строка: последний обработанный сеанс
    if not last:
        top = db.query(models.UserSession.id).order_by(models.UserSession.id.desc()).first()
        db.add(m.SeenDevice(user_id=0, device="__cursor__", last_session_id=top[0] if top else 0))
        # уже существующие устройства считаем знакомыми
        for uid, dev in db.query(models.UserSession.user_id, models.UserSession.device).distinct():
            db.add(m.SeenDevice(user_id=uid, device=(dev or "")[:120]))
        db.commit()
        return
    for sess in (db.query(models.UserSession).filter(models.UserSession.id > last.last_session_id)
                 .order_by(models.UserSession.id).limit(200).all()):
        last.last_session_id = sess.id
        dev = (sess.device or "неизвестное устройство")[:120]
        known = db.query(m.SeenDevice).filter_by(user_id=sess.user_id, device=dev).first()
        if known:
            continue
        had_any = db.query(m.SeenDevice.id).filter(m.SeenDevice.user_id == sess.user_id).first()
        db.add(m.SeenDevice(user_id=sess.user_id, device=dev))
        if had_any:  # самый первый вход после регистрации — не тревожим
            db.add(models.Notification(user_id=sess.user_id, type="security",
                                       text=f"Вход в аккаунт с нового устройства: {dev}. Если это были не вы — завершите сеанс в настройках безопасности и смените пароль."))
    db.commit()


# ---------------------------------------------------------------- центр помощи
@router.get("/help")
def help_center(request: Request, q: str = "", db: Session = Depends(get_db)):
    return render(request, db, "packs/v3/help.html", articles=ARTICLES, q=q)
