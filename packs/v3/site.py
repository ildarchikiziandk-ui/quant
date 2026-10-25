"""Настройки всего сайта из админ-панели: разделы вкл/выкл, регистрация, технические работы.
Хранятся в базе, читаются с кэшем на 15 секунд — меняются без перезапуска сервера."""
import json
import time

import config
from database import SessionLocal

from . import models as m

DEFAULTS = {"disabled": list(config.DISABLED_FEATURES), "registration": True, "maintenance": False,
            "maintenance_text": "Идут технические работы. Скоро вернёмся!",
            "calls": True, "sticker_packs_off": [], "banned_ips": [], "reserved_handles": [],
            "phone_check": True, "phone_every": 20,
            "read_only": False, "payments_on": False, "read_only_text": "", "muted": {}, "warnings": {}}
# разделы, которые можно включать и выключать
SECTIONS = [("/random", "Случайный пост"), ("/guests", "Гости профиля"), ("/notes", "Заметки"), ("/memories", "В этот день"),
            ("/wheel", "Колесо фортуны"), ("/questions", "Анонимные вопросы"), ("/ask", "Задать вопрос (страница вопросов)"),
            ("/games", "Игры"), ("/capsule", "Капсула времени"), ("/ai", "Помощник Нува"), ("/handles", "Красивые логины"),
            ("/events", "События"), ("/groups", "Группы"), ("/shop", "Магазин"), ("/leaderboard", "Рейтинг"), ("/top", "Топ постов"),
            ("/people/city", "Люди рядом"), ("/stories", "Истории"), ("/plus", "Nuvora+")]
_cache = {"t": 0, "v": dict(DEFAULTS)}


def _load():
    if time.time() - _cache["t"] < 15:
        return _cache["v"]
    v = dict(DEFAULTS)
    db = SessionLocal()
    try:
        for row in db.query(m.SiteSetting).all():
            try:
                v[row.key] = json.loads(row.value)
            except ValueError:
                pass
    except Exception:  # таблицы ещё нет (первый запуск) — значения по умолчанию
        pass
    finally:
        db.close()
    _cache.update(t=time.time(), v=v)
    return v


def get(key):
    return _load().get(key, DEFAULTS.get(key))


def put(db, key, value):
    row = db.get(m.SiteSetting, key) or m.SiteSetting(key=key)
    row.value = json.dumps(value, ensure_ascii=False)
    db.merge(row)
    db.commit()
    _cache["t"] = 0


def disabled():
    return get("disabled") or []


def is_disabled(path):
    return any(path == p or path.startswith(p + "/") for p in disabled())
