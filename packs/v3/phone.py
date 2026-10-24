"""Проверка номера телефона через свой бот в мессенджере MAX — не у всех, а выборочно (примерно каждая
20-я регистрация) и при подозрении: несколько новых аккаунтов с одного адреса, одноразовая почта,
массовые сообщения незнакомым, просьба админа.

Как это выглядит: на сайте кнопка «Подтвердить в MAX» открывает бота по одноразовой ссылке
(max.ru/<бот>/start/<код>), бот просит нажать «Поделиться номером» — MAX сам присылает контакт
пользователя с номером (чужой контакт не принимаем). Сайт ждёт подтверждения и пускает дальше.
Кнопка «Нет MAX» пропускает проверку. Пока проверка не пройдена, сайт открывает страницу проверки,
а сообщения не отправляются. Бот получает события долгим запросом /updates (вебхук не нужен).
"""
import hashlib
import hmac
import json
import random
import re
import secrets
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import config
import models
from database import SessionLocal, get_db
from deps import current_user, redirect, render

from . import models as m
from . import site
from .common import router

COOKIE = "pv"
REPEAT_DAYS = 30  # после проверки или пропуска не спрашиваем снова месяц (кроме просьбы админа)
LINK_MINUTES = 30  # одноразовая ссылка на бота действует полчаса
PER_ACCOUNT = 3  # один аккаунт MAX подтверждает не больше трёх аккаунтов Nuvora
DISPOSABLE = {"mailinator.com", "yopmail.com", "guerrillamail.com", "10minutemail.com", "temp-mail.org", "tempmail.com", "trashmail.com",
              "sharklasers.com", "getnada.com", "dispostable.com", "maildrop.cc", "fakeinbox.com", "mohmal.com", "emailondeck.com",
              "tempmail.plus", "mail.tm", "mintemail.com", "throwawaymail.com", "minuteinbox.com", "dropmail.me", "1secmail.com"}


def available():
    return bool(site.get("phone_check") and config.MAX_BOT_TOKEN and config.MAX_BOT_USERNAME)


def _hash(token):
    return hmac.new(config.SECRET_KEY.encode(), token.encode(), hashlib.sha256).hexdigest()


def pending(db, user):
    return bool(user) and db.query(m.PhoneCheck.id).filter_by(user_id=user.id, status="pending").first() is not None


def require(db, user, reason, force=False):
    """Попросить подтвердить номер. force — по просьбе админа, даже если недавно проверяли."""
    if not user or user.is_owner or (not force and not available()):
        return False
    row = db.query(m.PhoneCheck).filter_by(user_id=user.id).first()
    if row and not force:
        if row.status == "pending" or (row.done_at and row.done_at > datetime.utcnow() - timedelta(days=REPEAT_DAYS)):
            return row.status == "pending"
    if not row:
        row = m.PhoneCheck(user_id=user.id)
        db.add(row)
    row.status, row.reason, row.code_hash, row.done_at = "pending", reason[:80], "", None
    db.commit()
    return True


def on_register(db, user, request):
    """После регистрации: случайно примерно каждый N-й или при подозрении."""
    if not available():
        return False
    reasons = []
    if (user.email or "").split("@")[-1].lower() in DISPOSABLE:
        reasons.append("одноразовая почта")
    ip = request.client.host if request.client else ""
    if ip:
        day = datetime.utcnow() - timedelta(days=1)
        same = (db.query(models.UserSession.user_id).join(models.User, models.User.id == models.UserSession.user_id)
                .filter(models.UserSession.ip == ip, models.User.created_at > day, models.User.id != user.id).distinct().count())
        if same >= 2:  # у мобильных операторов один адрес на тысячи людей — подозрительно только с 3-го нового аккаунта
            reasons.append("несколько новых аккаунтов с одного адреса")
    if not reasons and random.random() < 1 / max(1, int(site.get("phone_every") or 20)):
        reasons.append("выборочная проверка")
    return require(db, user, ", ".join(reasons)) if reasons else False


def on_message(db, user):
    """Новый аккаунт за час пишет многим людям — похоже на рассылку."""
    if not available() or not user.created_at or user.created_at < datetime.utcnow() - timedelta(days=7):
        return False
    hour = datetime.utcnow() - timedelta(hours=1)
    n = db.query(models.Message.receiver_id).filter(models.Message.sender_id == user.id, models.Message.created_at > hour,
                                                    models.Message.group_id == None).distinct().count()  # noqa: E711
    return n >= 10 and require(db, user, "много новых чатов за час")


def status_of(db, user):
    return db.query(m.PhoneCheck).filter_by(user_id=user.id).first() if user else None


def _clear(resp):
    resp.delete_cookie(COOKIE)
    return resp


# ---------------------------------------------------------------- сайт
@router.get("/verify-phone")
def page(request: Request, next: str = "/", db: Session = Depends(get_db)):
    user = current_user(request, db)
    nxt = next if next.startswith("/") and not next.startswith("//") else "/"
    if not user:
        return redirect("/login")
    row = db.query(m.PhoneCheck).filter_by(user_id=user.id, status="pending").first()
    if not row:
        return _clear(redirect(nxt))
    return render(request, db, "packs/v3/phone_verify.html", sidebar=False, next=nxt, bot=config.MAX_BOT_USERNAME)


@router.post("/verify-phone/link")
def link(request: Request, db: Session = Depends(get_db)):
    """Одноразовая ссылка на бота: max.ru/<бот>/start/<код>."""
    user = current_user(request, db)
    row = db.query(m.PhoneCheck).filter_by(user_id=user.id, status="pending").first() if user else None
    if not row:
        return _clear(JSONResponse({"ok": True, "done": True}))
    if not config.MAX_BOT_USERNAME:  # бот не настроен — не задерживаем человека
        row.status, row.done_at = "skipped", datetime.utcnow()
        db.commit()
        return _clear(JSONResponse({"ok": True, "done": True}))
    token = secrets.token_urlsafe(18)
    row.code_hash, row.code_sent_at = _hash(token), datetime.utcnow()
    db.commit()
    return JSONResponse({"ok": True, "url": f"https://max.ru/{config.MAX_BOT_USERNAME}/start/{token}"})


@router.get("/verify-phone/status")
def status(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    row = db.query(m.PhoneCheck).filter_by(user_id=user.id).first() if user else None
    done = not row or row.status != "pending"
    resp = JSONResponse({"ok": True, "done": done, "verified": bool(row and row.status == "verified")})
    return _clear(resp) if done else resp


@router.post("/verify-phone/skip")
def skip(request: Request, db: Session = Depends(get_db)):
    """«Нет MAX»: пропускаем проверку."""
    user = current_user(request, db)
    row = db.query(m.PhoneCheck).filter_by(user_id=user.id, status="pending").first() if user else None
    if row:
        row.status, row.done_at, row.code_hash = "skipped", datetime.utcnow(), ""
        db.commit()
    return _clear(JSONResponse({"ok": True, "done": True}))


# ---------------------------------------------------------------- бот MAX
def _api(method, path, query=None, body=None, timeout=15):
    url = config.MAX_API_URL + path + ("?" + urllib.parse.urlencode(query) if query else "")
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": config.MAX_BOT_TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _say(user_id, text, contact_button=False):
    body = {"text": text}
    if contact_button:
        body["attachments"] = [{"type": "inline_keyboard", "payload": {"buttons": [[{"type": "request_contact", "text": "📱 Поделиться номером"}]]}}]
    try:
        _api("POST", "/messages", {"user_id": user_id}, body)
    except Exception as e:  # noqa: BLE001
        print(f"[max-bot] send: {e}")


def _phone_from_vcf(vcf):
    m = re.search(r"TEL[^:\n]*:([+\d][\d\s()+-]{5,})", vcf or "")
    d = re.sub(r"\D", "", m.group(1)) if m else ""
    return "+" + d if len(d) >= 10 else ""


def handle_update(db, upd, say=_say):
    """Одно событие от MAX. Возвращает, что произошло (для тестов)."""
    kind = upd.get("update_type")
    if kind == "bot_started":
        user_id = str((upd.get("user") or {}).get("user_id") or "")
        token = (upd.get("payload") or "").strip()
        if not user_id:
            return "skip"
        row = db.query(m.PhoneCheck).filter_by(code_hash=_hash(token), status="pending").first() if token else None
        if not row or not row.code_sent_at or row.code_sent_at < datetime.utcnow() - timedelta(minutes=LINK_MINUTES):
            say(user_id, "Это бот проверки аккаунтов Nuvora. Чтобы подтвердить номер, откройте ссылку со страницы проверки на сайте nvra.ru.")
            return "no-token"
        row.tg_user = user_id
        db.commit()
        u = db.get(models.User, row.user_id)
        say(user_id, f"Подтвердим аккаунт @{u.username if u else '?'} в Nuvora. Нажмите кнопку ниже — MAX передаст номер, "
                     "привязанный к вашему аккаунту. Номер никому не показывается.", contact_button=True)
        return "asked"
    if kind != "message_created":
        return "skip"
    msg = upd.get("message") or {}
    sender = str((msg.get("sender") or {}).get("user_id") or "")
    if not sender or (msg.get("sender") or {}).get("is_bot"):
        return "skip"
    contact = next((a.get("payload") or {} for a in ((msg.get("body") or {}).get("attachments") or []) if a.get("type") == "contact"), None)
    if contact is None:
        say(sender, "Чтобы подтвердить номер, нажмите кнопку «📱 Поделиться номером». Если кнопки нет — откройте ссылку со страницы проверки на сайте.",
            contact_button=bool(db.query(m.PhoneCheck.id).filter_by(tg_user=sender, status="pending").first()))
        return "hint"
    owner = str((contact.get("max_info") or {}).get("user_id") or "")
    if owner != sender:
        say(sender, "Нужен ваш собственный номер — нажмите кнопку «📱 Поделиться номером».", contact_button=True)
        return "foreign"
    row = db.query(m.PhoneCheck).filter_by(tg_user=sender, status="pending").order_by(m.PhoneCheck.code_sent_at.desc()).first()
    if not row:
        say(sender, "Не нашли проверку для этого аккаунта. Откройте ссылку со страницы проверки на сайте ещё раз.")
        return "no-check"
    if db.query(m.PhoneCheck).filter(m.PhoneCheck.tg_user == sender, m.PhoneCheck.status == "verified").count() >= PER_ACCOUNT:
        say(sender, "Этим аккаунтом MAX уже подтверждено несколько аккаунтов Nuvora. На сайте нажмите «Нет MAX».")
        return "limit"
    row.phone, row.method, row.status, row.done_at, row.code_hash = _phone_from_vcf(contact.get("vcf_info")), "max", "verified", datetime.utcnow(), ""
    db.commit()
    say(sender, "Готово! Номер подтверждён — возвращайтесь в Nuvora, страница откроется сама.")
    return "verified"


_bot = {"started": False}


def start_bot():
    """Долгий опрос MAX в фоновом потоке (один на процесс)."""
    if _bot["started"] or not config.MAX_BOT_TOKEN:
        return
    _bot["started"] = True

    def loop():
        marker, delay = None, 2
        while True:
            try:
                q = {"timeout": 25, "limit": 50, "types": "bot_started,message_created"}
                if marker is not None:
                    q["marker"] = marker
                res = _api("GET", "/updates", q, timeout=40)
                marker = res.get("marker", marker)
                for upd in res.get("updates") or []:
                    db = SessionLocal()
                    try:
                        handle_update(db, upd)
                    except Exception as e:  # noqa: BLE001
                        db.rollback()
                        print(f"[max-bot] {e}")
                    finally:
                        db.close()
                delay = 2
            except Exception as e:  # noqa: BLE001 — нет связи с MAX: пробуем реже
                print(f"[max-bot] poll: {e}")
                time.sleep(delay)
                delay = min(delay * 2, 120)

    threading.Thread(target=loop, name="nuvora-max-bot", daemon=True).start()
