import json
import re
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import auth
import config
import models
from database import get_db
from deps import current_user, redirect, render, safe_next
from services import legal, mailer, ratelimit, timezones

router = APIRouter()

RESERVED = {"admin", "api", "static", "uploads", "login", "logout", "register", "settings", "support", "nuvora", "root", "system"}


def validate_username(u):
    if len(u) < 3:
        return "Логин: минимум 3 символа"
    if len(u) > 30:
        return "Логин: максимум 30 символов"
    if not re.match(r"^[a-zA-Z0-9_]+$", u):
        return "Логин: только латиница, цифры и _"
    if u.lower() in RESERVED:
        return "Этот логин зарезервирован"
    return None


def validate_password(p):
    if len(p) < 8:
        return "Пароль: минимум 8 символов"
    if len(p) > 64:
        return "Пароль: максимум 64 символа"
    if p.isdigit() or p.isalpha():
        return "Пароль должен содержать и буквы, и цифры"
    return None


def validate_email(e):
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e or "") is not None


def _client_ip(request: Request):
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


def _finish_login(request, db, user, next_url="/"):
    token = auth.start_session(db, user, request)
    resp = redirect(safe_next(next_url))
    auth.set_auth_cookie(resp, token)
    resp.delete_cookie("pending_2fa")
    return resp


@router.get("/login")
def login_page(request: Request, next: str = "/", db: Session = Depends(get_db)):
    if current_user(request, db):
        return redirect(safe_next(next))
    return render(request, db, "login.html", sidebar=False, next=next)


def _find_user(db, ident):
    ident = ident.strip().lstrip("@").strip()
    return db.query(models.User).filter(or_(func.lower(models.User.username) == ident.lower(),
                                            func.lower(models.User.email) == ident.lower())).first()


@router.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), next: str = Form("/"),
          db: Session = Depends(get_db)):
    ident = username.strip().lstrip("@").strip()
    ip = _client_ip(request)
    if not ratelimit.hit(f"login:{ip}:{ident.lower()}", 10, 300):
        print(f"[login] rate-limited ip={ip} ident={ident!r}")
        return render(request, db, "login.html", sidebar=False, error="Слишком много попыток. Подождите 5 минут.", username=ident, next=next)
    user = _find_user(db, ident)
    if not user:
        print(f"[login] no such user ident={ident!r} ip={ip}")
        return render(request, db, "login.html", sidebar=False, username=ident, next=next,
                      error="Аккаунт с таким логином или email не найден. Вводите именно логин (тот, что после @), а не имя.")
    ok = auth.verify_password(password, user.password)
    if not ok and password != password.strip():
        # телефонные клавиатуры иногда добавляют пробел в конце
        ok = auth.verify_password(password.strip(), user.password)
        password = password.strip() if ok else password
    if not ok:
        print(f"[login] wrong password user={user.username} ip={ip}")
        return render(request, db, "login.html", sidebar=False, username=ident, next=next,
                      error="Неверный пароль. Проверьте раскладку и Caps Lock или нажмите «Забыли пароль?».")
    print(f"[login] ok user={user.username} ip={ip} ua={request.headers.get('user-agent', '')[:80]!r}")
    if auth.needs_rehash(user.password):
        user.password = auth.hash_password(password)
        db.commit()
    if user.two_factor_enabled and user.two_factor_secret:
        pending = auth.create_token({"uid": user.id, "purpose": "2fa", "exp": datetime.utcnow() + timedelta(minutes=5)})
        resp = render(request, db, "login_2fa.html", sidebar=False, next=next)
        resp.set_cookie("pending_2fa", pending, max_age=300, httponly=True, samesite="lax", secure=config.COOKIE_SECURE)
        return resp
    return _finish_login(request, db, user, next)


@router.post("/login/2fa")
def login_2fa(request: Request, code: str = Form(...), next: str = Form("/"), db: Session = Depends(get_db)):
    payload = auth.decode_token(request.cookies.get("pending_2fa", ""))
    if not payload or payload.get("purpose") != "2fa":
        return redirect("/login")
    if not ratelimit.hit(f"2fa:{payload['uid']}", 6, 300):
        return render(request, db, "login_2fa.html", sidebar=False, error="Слишком много попыток", next=next)
    user = db.get(models.User, payload["uid"])
    if not user or not auth.totp_verify(user.two_factor_secret, code):
        return render(request, db, "login_2fa.html", sidebar=False, error="Неверный код", next=next)
    return _finish_login(request, db, user, next)


@router.get("/register")
def register_page(request: Request, db: Session = Depends(get_db)):
    if current_user(request, db):
        return redirect("/")
    return render(request, db, "register.html", sidebar=False, beta=bool(config.BETA_CODE))


@router.post("/register")
def register(request: Request, username: str = Form(...), email: str = Form(...), password: str = Form(...),
             confirm_password: str = Form(...), agree: str = Form(""), consent: str = Form(""), adult: str = Form(""), beta_code: str = Form(""), name: str = Form(""),
             tz: str = Form(""), ref: str = Form(""), db: Session = Depends(get_db)):
    username, email = username.strip().lstrip("@"), email.strip().lower()
    form = {"username": username, "email": email, "full_name": name, "beta": bool(config.BETA_CODE)}

    def fail(msg):
        return render(request, db, "register.html", sidebar=False, error=msg, **form)

    if not ratelimit.hit(f"register:{_client_ip(request)}", 5, 3600):
        return fail("Слишком много регистраций с вашего адреса. Попробуйте позже.")
    if config.BETA_CODE and beta_code.strip().upper() != config.BETA_CODE.upper():
        return fail("Неверный инвайт-код")
    err = validate_username(username) or validate_password(password)
    if err:
        return fail(err)
    if not validate_email(email):
        return fail("Некорректный email")
    if password != confirm_password:
        return fail("Пароли не совпадают")
    if not agree:
        return fail("Нужно принять пользовательское соглашение")
    if not consent:
        return fail("Нужно дать согласие на обработку персональных данных")
    if not adult:
        return fail(f"Регистрация доступна с {config.MIN_AGE} лет")
    if db.query(models.User).filter(func.lower(models.User.username) == username.lower()).first():
        return fail(f"Логин @{username} уже занят")
    if db.query(models.User).filter(func.lower(models.User.email) == email).first():
        return fail("Email уже зарегистрирован")
    user = models.User(username=username, email=email, password=auth.hash_password(password), is_verified=True,
                       name=(name.strip() or username)[:60], email_verified=not config.EMAIL_ENABLED,
                       is_owner=(username == config.OWNER_USERNAME), pd_consent_at=datetime.utcnow(),
                       pd_consent_version=legal.CONSENT_VERSION, age_confirmed=True)
    tz_key = timezones.iana_map().get(tz.strip()[:64])
    if tz_key:  # пояс определён браузером при регистрации
        user.prefs = json.dumps({"timezone": tz_key}, ensure_ascii=False)
    db.add(user)
    db.commit()
    if config.EMAIL_ENABLED:
        _send_code(db, email, "register")
    db.add(models.Notification(user_id=user.id, type="system",
                               text=f"Добро пожаловать в {config.BRAND_NAME}! Заполни профиль и выполни первые задания ✨"))
    ref = (ref or request.cookies.get("ref") or "").strip()[:30]
    if ref and ratelimit.hit(f"invite-reward:{ref.lower()}", 5, 86400):  # не больше 5 наград в сутки — защита от накрутки
        from routers.extras import reward_inviter
        reward_inviter(db, user, ref)
    db.commit()
    resp = _finish_login(request, db, user, "/verify" if config.EMAIL_ENABLED else "/welcome")
    resp.delete_cookie("ref")
    return resp


def _send_code(db, email, purpose):
    code = mailer.generate_code()
    db.query(models.VerificationCode).filter_by(email=email, purpose=purpose).delete()
    db.add(models.VerificationCode(email=email, code=code, purpose=purpose))
    db.commit()
    if purpose == "reset":
        mailer.send_reset_email(email, code)
    else:
        mailer.send_verification_email(email, code)


def _check_code(db, email, purpose, code):
    vc = db.query(models.VerificationCode).filter_by(email=email, purpose=purpose).order_by(models.VerificationCode.created_at.desc()).first()
    if not vc or (datetime.utcnow() - vc.created_at) > timedelta(minutes=10):
        return False
    if not secrets.compare_digest(vc.code, code.strip()):
        return False
    db.delete(vc)
    db.commit()
    return True


@router.get("/verify")
def verify_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return redirect("/login")
    if user.email_verified:
        return redirect("/")
    return render(request, db, "verify.html", sidebar=False)


@router.post("/verify")
def verify_submit(request: Request, code: str = Form(...), db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return redirect("/login")
    if not ratelimit.hit(f"verify:{user.id}", 10, 600):
        return render(request, db, "verify.html", sidebar=False, error="Слишком много попыток")
    if _check_code(db, user.email, "register", code):
        user.email_verified = True
        db.commit()
        return redirect("/welcome")
    return render(request, db, "verify.html", sidebar=False, error="Неверный или просроченный код")


@router.post("/verify/resend")
def verify_resend(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if user and not user.email_verified and ratelimit.hit(f"resend:{user.id}", 3, 600):
        _send_code(db, user.email, "register")
    return redirect("/verify")


@router.get("/forgot")
def forgot_page(request: Request, db: Session = Depends(get_db)):
    return render(request, db, "forgot.html", sidebar=False, step="email", email_enabled=config.EMAIL_ENABLED)


@router.post("/forgot")
def forgot_submit(request: Request, email: str = Form(...), db: Session = Depends(get_db)):
    email = email.strip().lower()
    if ratelimit.hit(f"forgot:{_client_ip(request)}", 5, 3600):
        user = db.query(models.User).filter(func.lower(models.User.email) == email).first()
        if user:
            _send_code(db, email, "reset")
    return render(request, db, "forgot.html", sidebar=False, step="code", email=email, email_enabled=config.EMAIL_ENABLED)


@router.post("/forgot/reset")
def forgot_reset(request: Request, email: str = Form(...), code: str = Form(...), password: str = Form(...),
                 db: Session = Depends(get_db)):
    email = email.strip().lower()
    ctx = {"step": "code", "email": email, "email_enabled": config.EMAIL_ENABLED}
    if not ratelimit.hit(f"reset:{email}", 8, 600):
        return render(request, db, "forgot.html", sidebar=False, error="Слишком много попыток", **ctx)
    err = validate_password(password)
    if err:
        return render(request, db, "forgot.html", sidebar=False, error=err, **ctx)
    user = db.query(models.User).filter(func.lower(models.User.email) == email).first()
    if not user or not _check_code(db, email, "reset", code):
        return render(request, db, "forgot.html", sidebar=False, error="Неверный или просроченный код", **ctx)
    user.password = auth.hash_password(password)
    db.query(models.UserSession).filter_by(user_id=user.id).update({"is_active": False})
    db.commit()
    return render(request, db, "login.html", sidebar=False, success="Пароль изменён, войдите с новым паролем", username=user.username)


@router.get("/logout")
def logout_get(request: Request, db: Session = Depends(get_db)):
    return logout(request, db)


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    auth.end_session(request, db)
    resp = redirect("/")
    resp.delete_cookie(auth.COOKIE_NAME)
    return resp


# --- Яндекс OAuth -----------------------------------------------------------
@router.get("/auth/yandex")
def yandex_login():
    if not config.YANDEX_CLIENT_ID:
        return redirect("/login")
    from urllib.parse import urlencode
    state = secrets.token_urlsafe(16)
    url = "https://oauth.yandex.ru/authorize?" + urlencode({"response_type": "code", "client_id": config.YANDEX_CLIENT_ID,
                                                            "redirect_uri": config.YANDEX_REDIRECT_URI, "state": state})
    resp = redirect(url, 302)
    resp.set_cookie("oauth_state", state, max_age=600, httponly=True, samesite="lax", secure=config.COOKIE_SECURE)
    return resp


@router.get("/auth/yandex/callback")
async def yandex_callback(request: Request, code: str = "", state: str = "", db: Session = Depends(get_db)):
    if not code or not state or state != request.cookies.get("oauth_state"):
        return redirect("/login")
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            tr = await client.post("https://oauth.yandex.ru/token", data={
                "grant_type": "authorization_code", "code": code, "client_id": config.YANDEX_CLIENT_ID,
                "client_secret": config.YANDEX_CLIENT_SECRET, "redirect_uri": config.YANDEX_REDIRECT_URI})
            at = tr.json().get("access_token")
            if not at:
                return redirect("/login")
            yu = (await client.get("https://login.yandex.ru/info", headers={"Authorization": f"OAuth {at}"})).json()
    except Exception as e:
        print(f"Yandex OAuth error: {e}")
        return redirect("/login")
    yid = str(yu.get("id", ""))
    if not yid:
        return redirect("/login")
    email = (yu.get("default_email") or f"yandex_{yid}@yandex.ru").lower()
    user = db.query(models.User).filter(func.lower(models.User.email) == email).first()
    if not user:
        ubase = re.sub(r"[^A-Za-z0-9_]", "_", yu.get("login") or f"y_{yid}")[:26] or f"y_{yid}"
        if len(ubase) < 3:
            ubase = f"user_{ubase}"
        un, i = ubase, 1
        while db.query(models.User).filter(func.lower(models.User.username) == un.lower()).first():
            un, i = f"{ubase}_{i}", i + 1
        user = models.User(name=(yu.get("real_name") or yu.get("display_name") or un)[:60], username=un, email=email,
                           password=auth.hash_password(secrets.token_urlsafe(32)), is_verified=True, email_verified=True)
        db.add(user)
        db.commit()
    if user.two_factor_enabled and user.two_factor_secret:
        pending = auth.create_token({"uid": user.id, "purpose": "2fa", "exp": datetime.utcnow() + timedelta(minutes=5)})
        resp = render(request, db, "login_2fa.html", sidebar=False, next="/")
        resp.set_cookie("pending_2fa", pending, max_age=300, httponly=True, samesite="lax", secure=config.COOKIE_SECURE)
        return resp
    return _finish_login(request, db, user, "/")
