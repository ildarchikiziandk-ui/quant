"""Аутентификация: хэширование паролей (bcrypt с прозрачным апгрейдом старых sha256),
JWT-токены с привязкой к сессии, 2FA (TOTP) и шифрование сообщений."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import datetime, timedelta

import bcrypt
from jose import JWTError, jwt
from sqlalchemy.orm import Session

import config
import models

ALGORITHM = "HS256"
COOKIE_NAME = "token"


# --- Пароли ----------------------------------------------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def _is_legacy_hash(hashed: str) -> bool:
    return bool(hashed) and len(hashed) == 64 and all(c in "0123456789abcdef" for c in hashed)


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    if _is_legacy_hash(hashed):
        return hmac.compare_digest(hashlib.sha256(plain.encode()).hexdigest(), hashed)
    try:
        return bcrypt.checkpw(plain.encode()[:72], hashed.encode())
    except ValueError:
        return False


def needs_rehash(hashed: str) -> bool:
    return _is_legacy_hash(hashed)


# --- Токены и сессии -------------------------------------------------------
def create_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode.setdefault("exp", datetime.utcnow() + timedelta(days=config.TOKEN_DAYS))  # у токена 2FA — свои 5 минут
    return jwt.encode(to_encode, config.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str):
    try:
        return jwt.decode(token, config.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def _device_from_ua(ua: str) -> str:
    ua_l = (ua or "").lower()
    os_name = ("iPhone" if "iphone" in ua_l else "iPad" if "ipad" in ua_l else "Android" if "android" in ua_l
               else "Windows" if "windows" in ua_l else "macOS" if "mac os" in ua_l else "Linux" if "linux" in ua_l else "Устройство")
    browser = ("Edge" if "edg/" in ua_l else "Opera" if "opr/" in ua_l else "Яндекс" if "yabrowser" in ua_l
               else "Chrome" if "chrome" in ua_l else "Firefox" if "firefox" in ua_l else "Safari" if "safari" in ua_l else "")
    return f"{os_name} · {browser}".strip(" ·")


def start_session(db: Session, user, request) -> str:
    """Создаёт запись сессии и возвращает JWT для cookie."""
    raw = secrets.token_urlsafe(24)
    ua = request.headers.get("user-agent", "")[:300]
    ip = request.client.host if request.client else ""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        ip = fwd.split(",")[0].strip()
    s = models.UserSession(user_id=user.id, token_hash=hashlib.sha256(raw.encode()).hexdigest(),
                           device=_device_from_ua(ua), ip=ip[:64], user_agent=ua)
    db.add(s)
    db.commit()
    return create_token({"sub": user.username, "uid": user.id, "sid": raw})


def set_auth_cookie(resp, token: str):
    resp.set_cookie(COOKIE_NAME, token, max_age=60 * 60 * 24 * config.TOKEN_DAYS, httponly=True,
                    samesite="lax", secure=config.COOKIE_SECURE)
    return resp


def get_current_user(request, db: Session):
    cached = getattr(request.state, "user_cache", None)
    if cached is not None:
        return cached or None
    user = _resolve_user(request, db)
    request.state.user_cache = user or False
    return user


def _resolve_user(request, db: Session):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    payload = decode_token(token)
    # входом считается только токен с активной сессией; служебные токены (например, ожидание кода 2FA) не подходят
    if not payload or payload.get("purpose") or not payload.get("sid"):
        return None
    user = None
    if payload.get("uid"):
        user = db.get(models.User, payload["uid"])
    elif payload.get("sub"):
        user = db.query(models.User).filter(models.User.username == payload["sub"]).first()
    if not user:
        return None
    sid = payload.get("sid")
    if sid:
        s = db.query(models.UserSession).filter(
            models.UserSession.token_hash == hashlib.sha256(sid.encode()).hexdigest()).first()
        if not s or not s.is_active or s.user_id != user.id:
            return None
        now = datetime.utcnow()
        if not s.last_active or (now - s.last_active).total_seconds() > 300:
            s.last_active = now
            db.commit()
        request.state.session_id = s.id
    return user


def end_session(request, db: Session):
    token = request.cookies.get(COOKIE_NAME)
    payload = decode_token(token) if token else None
    if payload and payload.get("sid"):
        s = db.query(models.UserSession).filter(
            models.UserSession.token_hash == hashlib.sha256(payload["sid"].encode()).hexdigest()).first()
        if s:
            s.is_active = False
            db.commit()


# --- TOTP (двухфакторная аутентификация, RFC 6238) -------------------------
def totp_new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _totp_at(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


def totp_now(secret: str) -> str:
    return _totp_at(secret, int(time.time() // 30))


def totp_verify(secret: str, code: str, window: int = 1) -> bool:
    if not secret or not code:
        return False
    code = code.strip().replace(" ", "")
    counter = int(time.time() // 30)
    return any(hmac.compare_digest(_totp_at(secret, counter + d), code) for d in range(-window, window + 1))


def totp_uri(secret: str, username: str) -> str:
    from urllib.parse import quote
    issuer = quote(config.BRAND_NAME)
    return f"otpauth://totp/{issuer}:{quote(username)}?secret={secret}&issuer={issuer}"


# --- «Шифрование» сообщений (совместимо со старыми данными) ----------------
def encrypt_message(content: str) -> str:
    if not content:
        return ""
    encrypted = "".join(chr(ord(c) ^ 42) for c in content)
    return encrypted.encode("utf-8").hex()


def decrypt_message(encrypted: str) -> str:
    if not encrypted:
        return ""
    try:
        raw = bytes.fromhex(encrypted)
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError:
            decoded = raw.decode("latin-1")
        return "".join(chr(ord(c) ^ 42) for c in decoded)
    except Exception:
        return encrypted
