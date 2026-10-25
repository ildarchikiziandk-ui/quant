"""Настройки школы. Берутся из переменных окружения (на сервере — /opt/nuvora/school/.env)."""
import os

BASE = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = os.environ.get("SCHOOL_DATABASE_URL") or f"sqlite:///{os.path.join(BASE, 'data', 'school.db')}"
SECRET_KEY = os.environ.get("SCHOOL_SECRET_KEY", "dev-only-school-secret")
COOKIE_SECURE = os.environ.get("SCHOOL_COOKIE_SECURE", "0") == "1"
SITE_URL = os.environ.get("SCHOOL_SITE_URL", "https://school.nvra.ru")
TEACHER_LOGIN = os.environ.get("SCHOOL_TEACHER_LOGIN", "rubl")  # логин кабинета учителя (пароль задаётся при установке)
ANDROID_REPO = os.environ.get("SCHOOL_ANDROID_REPO", "ildarchikiziandk-ui/quant")
APK_CACHE_DIR = os.environ.get("SCHOOL_APK_DIR", os.path.join(BASE, "data", "app"))
SESSION_DAYS = 60
