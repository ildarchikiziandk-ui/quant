"""Шифрование личных и групповых сообщений в базе данных.

Алгоритм — AES-256-GCM (тот же класс шифров, что в банковских приложениях и мессенджерах): каждое
сообщение шифруется со своим случайным 96-битным nonce, а GCM-тег защищает от подмены. В базе хранится
строка вида «enc1:<base64(nonce + шифротекст)>», расшифровка происходит прозрачно при чтении.

Ключ:
- MESSAGE_KEY в .env (base64, 32 байта) — рекомендуется; сгенерировать: python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())";
- если не задан — выводится из SECRET_KEY через HKDF-SHA256. Поэтому SECRET_KEY нельзя менять без MESSAGE_KEY:
  иначе старые сообщения не расшифруются.

Это шифрование «на хранении»: если база или бэкап утекут, переписку не прочитать без ключа с сервера.
"""
import base64
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

import config

PREFIX = "enc1:"
_aead = None


def _key():
    raw = os.getenv("MESSAGE_KEY", "").strip()
    if raw:
        key = base64.b64decode(raw)
        if len(key) != 32:
            raise ValueError("MESSAGE_KEY должен быть 32 байта в base64")
        return key
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"nuvora-messages-v1", info=b"message-encryption").derive(
        config.SECRET_KEY.encode())


def _cipher():
    global _aead
    if _aead is None:
        _aead = AESGCM(_key())
    return _aead


def _is_ciphertext(value):
    try:
        data = base64.b64decode(str(value)[len(PREFIX):], validate=True)
        _cipher().decrypt(data[:12], data[12:], b"nuvora-msg")
        return True
    except Exception:
        return False


def encrypt(text):
    if text is None or text == "":
        return text
    # уже зашифрованное не шифруем повторно; но обычный текст, который просто начинается с «enc1:», шифруем как обычно
    if str(text).startswith(PREFIX) and _is_ciphertext(text):
        return text
    nonce = os.urandom(12)
    ct = _cipher().encrypt(nonce, str(text).encode("utf-8"), b"nuvora-msg")
    return PREFIX + base64.b64encode(nonce + ct).decode("ascii")


def decrypt(value):
    if not value or not str(value).startswith(PREFIX):
        return value  # старые незашифрованные сообщения читаются как есть
    try:
        data = base64.b64decode(str(value)[len(PREFIX):])
        return _cipher().decrypt(data[:12], data[12:], b"nuvora-msg").decode("utf-8")
    except Exception:
        return "Сообщение не удалось расшифровать"


def is_encrypted(value):
    return bool(value) and str(value).startswith(PREFIX)
