"""«Магазин логинов»: красивые логины за баллы (списки — в services/handles.py)."""
from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

import auth
import models
from database import get_db
from deps import current_user, json_error, login_redirect, render
from routers.posts import read_payload
from services import extras, handles, social

from . import models as m
from .common import router, s


def _taken(db):
    names = list(handles.PREMIUM)
    rows = db.query(func.lower(models.User.username)).filter(func.lower(models.User.username).in_(names)).all()
    return {r[0] for r in rows}


@router.get("/handles")
def handles_page(request: Request, q: str = "", db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    taken = _taken(db)
    q = q.strip().lower().lstrip("@")[:30]
    items = [(n, p) for n, p in handles.PREMIUM.items() if n not in taken and (not q or q in n)]
    items.sort(key=lambda x: (-x[1], x[0]))
    tiers = {}
    for n, p in items:
        tiers.setdefault(p, []).append(n)
    mine = db.query(m.HandlePurchase).filter_by(user_id=user.id).order_by(m.HandlePurchase.id.desc()).all()
    return render(request, db, "packs/v3/handles.html", tiers=sorted(tiers.items(), key=lambda x: -x[0]), q=q,
                  balance=extras.balance(user), elite_n=len(handles.ELITE), sold=len(taken), mine=mine)


@router.post("/handles/buy")
async def handles_buy(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    if social.is_active_block(user):
        return json_error("Аккаунт заблокирован", 403)
    data = await read_payload(request)
    name = s(data.get("username")).strip().lstrip("@").lower()
    price = handles.PREMIUM.get(name)
    if not price:
        return json_error("Этот логин не продаётся")
    if db.query(models.User).filter(func.lower(models.User.username) == name).first():
        return json_error("Этот логин уже купили")
    if not auth.verify_password(s(data.get("password")), user.password):
        return json_error("Неверный пароль")
    if extras.balance(user) < price:
        return json_error(f"Не хватает баллов: нужно {price}, у вас {extras.balance(user)}")
    old = user.username
    user.username = name
    user.spent_points = (user.spent_points or 0) + price
    db.add(m.HandlePurchase(user_id=user.id, username=name, old_username=old, price=price))
    db.add(models.Notification(user_id=user.id, type="system", text=f"Теперь ваш логин — @{name}. Старый @{old} освободился."))
    db.commit()
    return JSONResponse({"ok": True, "username": name, "balance": extras.balance(user)})
