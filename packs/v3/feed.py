"""Лента 3.0: «Не показывать 30 дней» — временно скрыть автора."""
from datetime import datetime, timedelta

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import current_user, json_error

from . import models as m
from .common import router


# ---------------------------------------------------------------- не показывать автора 30 дней
@router.post("/v3/hide/{username}")
def hide_author(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    target = db.query(models.User).filter(func.lower(models.User.username) == username.lower()).first()
    if not target or target.id == user.id:
        return json_error("Пользователь не найден", 404)
    if not db.query(models.UserMute).filter_by(user_id=user.id, muted_id=target.id).first():
        db.add(models.UserMute(user_id=user.id, muted_id=target.id))
    db.query(m.TempMute).filter_by(user_id=user.id, muted_id=target.id).delete()
    db.add(m.TempMute(user_id=user.id, muted_id=target.id, until=datetime.utcnow() + timedelta(days=30)))
    db.commit()
    return JSONResponse({"ok": True})


def unmute_expired(db):
    """Фоновая задача: через 30 дней автор снова появляется в ленте."""
    now = datetime.utcnow()
    for t in db.query(m.TempMute).filter(m.TempMute.until <= now).limit(200).all():
        db.query(models.UserMute).filter_by(user_id=t.user_id, muted_id=t.muted_id).delete()
        db.delete(t)
    db.commit()
