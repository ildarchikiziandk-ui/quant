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

# --- Push (VAPID) --------------------------------------------------------
VAPID_PUBLIC_KEY = env("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = env("VAPID_PRIVATE_KEY", "")
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
