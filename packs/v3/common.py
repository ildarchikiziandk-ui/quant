from datetime import datetime

from fastapi import APIRouter

router = APIRouter()


def s(v):
    """Значение из формы/JSON → строка (числа и списки не роняют обработчик)."""
    return v if isinstance(v, str) else ("" if v is None or isinstance(v, (list, dict)) else str(v))


def today(user=None):
    """Сегодняшняя дата ГГГГ-ММ-ДД в часовом поясе пользователя."""
    from services import timezones
    try:
        return timezones.to_local(datetime.utcnow(), user).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return datetime.utcnow().strftime("%Y-%m-%d")
