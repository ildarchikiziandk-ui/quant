"""Капсула времени: письмо себе в будущее, до срока его не прочитать."""
from datetime import datetime, timedelta

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import current_user, json_error, login_redirect, render
from routers.posts import read_payload
from services import timezones

from . import models as m
from .common import router, s


@router.get("/capsule")
def capsule(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    now = datetime.utcnow()
    rows = db.query(m.Capsule).filter_by(user_id=user.id).order_by(m.Capsule.open_at.asc()).all()
    return render(request, db, "packs/v3/capsule.html", now=now, sealed=[c for c in rows if c.open_at > now],
                  opened=sorted([c for c in rows if c.open_at <= now], key=lambda c: c.open_at, reverse=True))


@router.post("/capsule")
async def capsule_create(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    data = await read_payload(request)
    text = s(data.get("text")).strip()[:5000]
    if len(text) < 3:
        return json_error("Напишите письмо себе")
    period = s(data.get("period"))
    now = datetime.utcnow()
    if period in ("1m", "6m", "1y"):
        at = now + timedelta(days={"1m": 30, "6m": 182, "1y": 365}[period])
    else:
        try:
            at = timezones.from_local(datetime.strptime(s(data.get("date"))[:10], "%Y-%m-%d").replace(hour=9), user)
        except ValueError:
            return json_error("Выберите, когда открыть письмо")
    if at <= now + timedelta(hours=1) or at > now + timedelta(days=365 * 10):
        return json_error("Дата — от завтра и не дальше чем через 10 лет")
    if db.query(m.Capsule).filter(m.Capsule.user_id == user.id, m.Capsule.open_at > now).count() >= 50:
        return json_error("Слишком много запечатанных писем")
    db.add(m.Capsule(user_id=user.id, text=text, open_at=at))
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/capsule/{cid}/delete")
def capsule_delete(cid: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    db.query(m.Capsule).filter_by(id=cid, user_id=user.id).delete()
    db.commit()
    return JSONResponse({"ok": True})


def capsules_due(db):
    """Фоновая задача: письмо из прошлого открылось — уведомление."""
    now = datetime.utcnow()
    for c in db.query(m.Capsule).filter(m.Capsule.open_at <= now, m.Capsule.notified == False).limit(100).all():
        c.notified = True
        days = max(1, (now - c.created_at).days) if c.created_at else 1
        db.add(models.Notification(user_id=c.user_id, type="capsule", text=f"Открылось письмо, которое вы написали себе {days} дн. назад"))
    db.commit()

