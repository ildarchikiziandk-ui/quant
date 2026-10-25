"""Покупка Искр и Nuvora+ через ЮKassa. Пока выключено: работает, только когда в .env заданы ключи магазина
(YOOKASSA_SHOP_ID, YOOKASSA_SECRET) и владелец включил оплату в админке («Сайт»).

- Nuvora+ на 30 дней — за любое пожертвование от 35 до 250 ₽.
- Искры — 1 Искра ≈ 0,25 ₽ (4 Искры за рубль). Купленные Искры не поднимают уровень: уровень — за активность.
Оплату подтверждаем только по ответу самой ЮKassa (запрос статуса платежа), уведомлению на слово не верим.
"""
import base64
import json
import uuid
import urllib.request
from datetime import datetime

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import config
import models
from database import get_db
from deps import current_user, json_error, login_redirect, redirect, render

from . import models as m
from . import site
from .common import router, s

API = "https://api.yookassa.ru/v3"
SPARK_PACKS = [100, 400, 1000, 2000]  # готовые наборы Искр; можно и своё число


def keys_set():
    return bool(config.YOOKASSA_SHOP_ID and config.YOOKASSA_SECRET)


def enabled():
    return keys_set() and bool(site.get("payments_on"))


def sparks_price(n):
    return max(1, round(n * config.SPARK_RUB))


def _call(method, path, body=None, key=None):
    """Запрос к API ЮKassa. Вынесено отдельно, чтобы в тестах подменить."""
    auth = base64.b64encode(f"{config.YOOKASSA_SHOP_ID}:{config.YOOKASSA_SECRET}".encode()).decode()
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json",
                                          **({"Idempotence-Key": key} if key else {})})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def apply(db, p):
    """Начислить купленное (один раз)."""
    if p.applied or p.status != "succeeded":
        return
    user = db.get(models.User, p.user_id)
    if not user:
        return
    if p.kind == "plus":
        from services import gamification
        gamification.grant_plus(user, 30)
        text = f"Спасибо за поддержку! Nuvora+ активен до {user.plus_until.strftime('%d.%m.%Y')}"
    else:
        user.spent_points = (user.spent_points or 0) - p.sparks  # баланс растёт, уровень — нет
        text = f"Начислено {p.sparks} Искр — спасибо за покупку!"
    p.applied = True
    p.paid_at = datetime.utcnow()
    db.add(models.Notification(user_id=user.id, type="system", text=text))


def refresh(db, p):
    """Узнать у ЮKassa актуальный статус платежа и начислить, если оплачен."""
    if not p.provider_id or p.status != "pending":
        return p
    try:
        j = _call("GET", f"/payments/{p.provider_id}")
    except Exception as e:  # noqa: BLE001
        print(f"[pay] status {p.id}: {e}")
        return p
    if j.get("status") == "succeeded" and j.get("paid"):
        amount = float((j.get("amount") or {}).get("value") or 0)
        if amount + 0.001 >= p.amount:  # сумма должна совпасть с заказом
            p.status = "succeeded"
            apply(db, p)
    elif j.get("status") == "canceled":
        p.status = "canceled"
    db.commit()
    return p


@router.get("/buy")
def buy_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    from services import extras
    return render(request, db, "packs/v3/buy.html", on=enabled(), packs=[(n, sparks_price(n)) for n in SPARK_PACKS],
                  pmin=config.PLUS_DONATION_MIN, pmax=config.PLUS_DONATION_MAX, rub=config.SPARK_RUB, balance=extras.balance(user),
                  history=db.query(m.Payment).filter_by(user_id=user.id).order_by(m.Payment.id.desc()).limit(10).all())


@router.post("/buy")
async def buy(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    if not enabled():
        return json_error("Оплата пока не работает — скоро включим")
    f = await request.form()
    kind = s(f.get("kind"))
    try:
        if kind == "plus":
            amount = int(s(f.get("amount")) or 0)
            if not config.PLUS_DONATION_MIN <= amount <= config.PLUS_DONATION_MAX:
                return json_error(f"Сумма пожертвования — от {config.PLUS_DONATION_MIN} до {config.PLUS_DONATION_MAX} ₽")
            sparks, desc = 0, f"Nuvora+ на 30 дней (@{user.username})"
        elif kind == "sparks":
            sparks = int(s(f.get("sparks")) or 0)
            if not 20 <= sparks <= 40000:
                return json_error("Можно купить от 20 до 40 000 Искр за раз")
            amount, desc = sparks_price(sparks), f"{sparks} Искр (@{user.username})"
        else:
            return json_error("Что покупаем?")
    except ValueError:
        return json_error("Неверная сумма")
    p = m.Payment(user_id=user.id, kind=kind, amount=amount, sparks=sparks)
    db.add(p)
    db.flush()
    try:
        j = _call("POST", "/payments", {
            "amount": {"value": f"{amount}.00", "currency": "RUB"}, "capture": True, "description": desc[:128],
            "confirmation": {"type": "redirect", "return_url": f"{config.SITE_URL}/buy/return/{p.id}"},
            "metadata": {"payment": p.id, "user": user.id},
        }, key=str(uuid.uuid4()))
    except Exception as e:  # noqa: BLE001
        print(f"[pay] create: {e}")
        db.rollback()
        return json_error("Платёжный сервис не ответил — попробуйте позже")
    p.provider_id = str(j.get("id") or "")[:64]
    db.commit()
    url = (j.get("confirmation") or {}).get("confirmation_url")
    return JSONResponse({"ok": True, "url": url})


@router.get("/buy/return/{pid}")
def buy_return(pid: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    p = db.get(m.Payment, pid)
    if not user or not p or p.user_id != user.id:
        return redirect("/buy")
    refresh(db, p)
    return render(request, db, "packs/v3/buy_done.html", p=p)


@router.post("/buy/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    """Уведомление от ЮKassa: берём из него только id платежа и сами спрашиваем статус."""
    try:
        data = await request.json()
        pid = str(((data or {}).get("object") or {}).get("id") or "")
    except ValueError:
        pid = ""
    p = db.query(m.Payment).filter_by(provider_id=pid).first() if pid else None
    if p:
        refresh(db, p)
    return JSONResponse({"ok": True})


def pending_job(db):
    """Фоновая проверка «зависших» платежей (человек оплатил, но не вернулся на сайт)."""
    if not keys_set():
        return
    for p in db.query(m.Payment).filter_by(status="pending").order_by(m.Payment.id.desc()).limit(20):
        if p.provider_id and (datetime.utcnow() - p.created_at).total_seconds() < 86400:
            refresh(db, p)
