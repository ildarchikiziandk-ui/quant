"""«Магазин логинов»: красивые логины за искры (списки — в services/handles.py)."""
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
    return {r[0] for r in rows} | {a.handle for a in db.query(m.UserAlias).filter(m.UserAlias.handle.in_(names))}


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
    if handles.owner_of(db, name):
        return json_error("Этот логин уже купили")
    as_alias = s(data.get("mode")) == "alias"
    if as_alias and db.query(m.UserAlias).filter_by(user_id=user.id).count() >= handles.MAX_ALIASES:
        return json_error(f"У вас уже {handles.MAX_ALIASES} дополнительных логина — удалите один в настройках")
    if not auth.verify_password(s(data.get("password")), user.password):
        return json_error("Неверный пароль")
    if extras.balance(user) < price:
        return json_error(f"Не хватает искр: нужно {price}, у вас {extras.balance(user)}")
    old = user.username
    user.spent_points = (user.spent_points or 0) + price
    if as_alias:
        db.add(m.UserAlias(user_id=user.id, handle=name))
        text = f"@{name} теперь ваш дополнительный логин — по нему вас найдут и он ведёт в ваш профиль."
    else:
        user.username = name
        text = f"Теперь ваш логин — @{name}. Старый @{old} освободился."
    db.add(m.HandlePurchase(user_id=user.id, username=name, old_username=old, price=price))
    db.add(models.Notification(user_id=user.id, type="system", text=text))
    db.commit()
    return JSONResponse({"ok": True, "username": user.username, "alias": as_alias, "balance": extras.balance(user)})


# ---------------------------------------------------------------- до трёх логинов у одного человека
def aliases_of(user):
    """Дополнительные логины человека (для профиля и настроек)."""
    if not user:
        return []
    from database import SessionLocal
    db = SessionLocal()
    try:
        return [a.handle for a in db.query(m.UserAlias).filter_by(user_id=user.id).order_by(m.UserAlias.id)]
    finally:
        db.close()


def _alias_error(db, user, name):
    from routers.auth_routes import validate_username
    if not name:
        return "Введите логин"
    err = validate_username(name, user)
    if err:
        return err
    if handles.owner_of(db, name):
        return "Этот логин уже занят"
    if db.query(m.UserAlias).filter_by(user_id=user.id).count() >= handles.MAX_ALIASES:
        return f"Можно не больше {handles.MAX_ALIASES + 1} логинов: основной и {handles.MAX_ALIASES} дополнительных"
    return None


@router.post("/settings/aliases/add")
async def alias_add(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    data = await read_payload(request)
    name = s(data.get("handle")).strip().lstrip("@")
    if not auth.verify_password(s(data.get("password")), user.password):
        return json_error("Неверный пароль")
    err = _alias_error(db, user, name)
    if err:
        return json_error(err)
    db.add(m.UserAlias(user_id=user.id, handle=name.lower()))
    db.commit()
    return JSONResponse({"ok": True, "handle": name.lower()})


@router.post("/settings/aliases/{handle}/{action}")
def alias_action(handle: str, action: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    a = db.query(m.UserAlias).filter_by(user_id=user.id, handle=handle.lower()).first()
    if not a:
        return json_error("Логин не найден", 404)
    if action == "delete":
        db.delete(a)
    elif action == "primary":  # дополнительный становится основным, а основной — дополнительным
        old = user.username
        user.username, a.handle = a.handle, old.lower()
    else:
        return json_error("Неизвестное действие")
    db.commit()
    return JSONResponse({"ok": True, "username": user.username})


OWNER_ALIASES = ("ildar", "mint")  # логины владельца сайта (основной — OWNER_USERNAME)
_seeded = []


def seed_owner_aliases(db):
    """Фоновая задача, один раз: закрепляет за владельцем его дополнительные логины, если они свободны."""
    if _seeded:
        return
    _seeded.append(1)
    import config
    owner = db.query(models.User).filter(func.lower(models.User.username) == (config.OWNER_USERNAME or "").lower()).first() \
        or social.main_owner(db)
    if not owner:
        return
    for name in OWNER_ALIASES:
        if db.query(m.UserAlias).filter_by(user_id=owner.id).count() >= handles.MAX_ALIASES:
            break
        if not handles.owner_of(db, name):
            db.add(m.UserAlias(user_id=owner.id, handle=name))
    db.commit()
