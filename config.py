"""Настройки приложения. Всё, что зависит от окружения, читается из переменных окружения
(или из файла .env в корне проекта). Секреты в коде больше не хранятся."""
import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv(path):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(os.path.join(BASE_DIR, ".env"))


def env(name, default=""):
    return os.getenv(name, default)


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


# --- Бренд ---------------------------------------------------------------
# Ребрендинг делается здесь: имя проекта подставляется во все шаблоны, письма и пуши.
BRAND_NAME = env("BRAND_NAME", "Nuvora")
APP_VERSION = "3.1"
# Убранные разделы: адреса ведут на главную. Вернуть раздел — убрать его из списка (и ссылку в меню).
DISABLED_FEATURES = [p for p in env("DISABLED_FEATURES", "/random,/guests,/notes,/memories,/wheel,/questions,/ask").split(",") if p.strip()]  # номер версии сайта — показывается в «Что нового»
BRAND_TAGLINE = env("BRAND_TAGLINE", "Соцсеть, где светятся идеи")
BRAND_PLUS = env("BRAND_PLUS", f"{BRAND_NAME}+")
BRAND_EMAIL = env("BRAND_EMAIL", "support@example.com")
BRAND_COLOR = env("BRAND_COLOR", "#18181b")
SITE_URL = env("SITE_URL", "http://localhost:8000").rstrip("/")
ANDROID_APK_URL = env("ANDROID_APK_URL", "https://github.com/ildarchikiziandk-ui/quant/releases/latest/download/Nuvora.apk")

# --- База и файлы --------------------------------------------------------
DATABASE_URL = env("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'quant.db')}")
UPLOAD_DIR = env("UPLOAD_DIR", os.path.join(BASE_DIR, "uploads"))

# --- Безопасность --------------------------------------------------------
_LEGACY_SECRET = "quant_secret_key_2024"
SECRET_KEY = env("SECRET_KEY") or _LEGACY_SECRET
if SECRET_KEY == _LEGACY_SECRET:
    print("[config] ВНИМАНИЕ: SECRET_KEY не задан, используется старый ключ. Задайте SECRET_KEY в .env!")
TOKEN_DAYS = int(env("TOKEN_DAYS", "30"))
COOKIE_SECURE = env_bool("COOKIE_SECURE", SITE_URL.startswith("https://"))
OWNER_USERNAME = env("OWNER_USERNAME", "rubl")
BETA_CODE = env("BETA_CODE", "")  # если задан — регистрация только по инвайт-коду

# --- Почта ---------------------------------------------------------------
SMTP_HOST = env("SMTP_HOST", "smtp.mail.ru")
SMTP_PORT = int(env("SMTP_PORT", "587"))
SMTP_USER = env("SMTP_USER", "")
SMTP_PASSWORD = env("SMTP_PASSWORD", "")
EMAIL_ENABLED = bool(SMTP_USER and SMTP_PASSWORD)

# --- Собственная модель модерации (services/moderation.py) --------------
MODERATION_ENABLED = env_bool("MODERATION_ENABLED", True)
MOD_FLAG_THRESHOLD = float(env("MOD_FLAG_THRESHOLD", "0.7"))   # с этой оценки пост попадает модераторам
MOD_HOLD_THRESHOLD = float(env("MOD_HOLD_THRESHOLD", "0.93"))  # с этой — пост скрывается до проверки

# --- Секретные чаты (ГОСТ, сквозное шифрование) --------------------------
# Выключены по умолчанию: распространение шифровальных средств может требовать лицензии ФСБ (ПП РФ № 313).
# Включить (после консультации юриста): SECRET_CHATS_ENABLED=1 в .env
SECRET_CHATS_ENABLED = env_bool("SECRET_CHATS_ENABLED", False)

# --- Звонки (WebRTC). Видео идёт напрямую; если не получилось — через свой ретранслятор coturn (deploy/set-calls.sh)
CALLS_ENABLED = env_bool("CALLS_ENABLED", True)
STUN_URLS = [u.strip() for u in env("STUN_URLS", "stun:stun.l.google.com:19302,stun:stun.cloudflare.com:3478").split(",") if u.strip()]
TURN_HOST = env("TURN_HOST", "")  # по умолчанию — домен сайта
TURN_SECRET = env("TURN_SECRET", "")  # общий секрет с coturn (use-auth-secret); пусто — только STUN
# Сколько дней сервер хранит шифротекст после срабатывания таймера/удаления (0 — удалять сразу).
# Если сервис внесён в реестр ОРИ (149-ФЗ ст. 10.1), закон требует хранить сообщения 6 месяцев — поставьте 180.
SECRET_RETAIN_DAYS = int(env("SECRET_RETAIN_DAYS", "0"))

# --- Оператор персональных данных (152-ФЗ) — показывается в политике конфиденциальности ---
OPERATOR_NAME = env("OPERATOR_NAME", "")      # ФИО (самозанятый/ИП) или название организации
OPERATOR_INN = env("OPERATOR_INN", "")
OPERATOR_ADDRESS = env("OPERATOR_ADDRESS", "")
OPERATOR_EMAIL = env("OPERATOR_EMAIL", "") or BRAND_EMAIL
SERVER_LOCATION = env("SERVER_LOCATION", "")  # например «Россия, Москва» — для 152-ФЗ ст. 18 ч. 5 (локализация)
MIN_AGE = int(env("MIN_AGE", "14"))

# --- Push (VAPID) --------------------------------------------------------
VAPID_PUBLIC_KEY = env("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = env("VAPID_PRIVATE_KEY", "")


def _auto_vapid():
    """Если ключи не заданы — создаём их один раз и храним рядом с приложением (push в браузере заработает сам)."""
    import base64
    import json as _json
    path = os.path.join(BASE_DIR, ".vapid.json")
    try:
        with open(path, encoding="utf-8") as f:
            d = _json.load(f)
        return d["public"], d["private"]
    except (OSError, ValueError, KeyError):
        pass
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        key = ec.generate_private_key(ec.SECP256R1())
        raw_priv = key.private_numbers().private_value.to_bytes(32, "big")
        raw_pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        b64 = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")
        pub, priv = b64(raw_pub), b64(raw_priv)
        with open(path, "w", encoding="utf-8") as f:
            _json.dump({"public": pub, "private": priv}, f)
        os.chmod(path, 0o600)
        return pub, priv
    except Exception as e:  # нет прав на запись — push в браузере останется выключенным
        print(f"[config] VAPID: {e}")
        return "", ""


if not (VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY) and env_bool("VAPID_AUTO", True):
    VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY = _auto_vapid()
VAPID_EMAIL = env("VAPID_EMAIL", f"mailto:{BRAND_EMAIL}")

# --- Яндекс OAuth --------------------------------------------------------
YANDEX_CLIENT_ID = env("YANDEX_CLIENT_ID", "")
YANDEX_CLIENT_SECRET = env("YANDEX_CLIENT_SECRET", "")
YANDEX_REDIRECT_URI = env("YANDEX_REDIRECT_URI", f"{SITE_URL}/auth/yandex/callback")

# --- Лимиты --------------------------------------------------------------
MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_VIDEO_SIZE = 100 * 1024 * 1024
MAX_FILE_SIZE = 50 * 1024 * 1024
MAX_AUDIO_SIZE = 20 * 1024 * 1024
MAX_IMAGE_DIMENSION = 1920
MAX_POST_LENGTH = 5000
MAX_POST_MEDIA = 10
POINTS_PER_LEVEL = 500
POSTS_PER_PAGE = 20

INSTANCE_ID = secrets.token_hex(4)
try:  # версия статики по содержимому: не меняется при перезапуске и совпадает со встроенной в приложение
    from services.assets import static_version as _sv
    STATIC_V = _sv(os.path.join(BASE_DIR, "static"))
except Exception:
    STATIC_V = INSTANCE_ID
