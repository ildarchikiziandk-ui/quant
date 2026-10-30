"""Справочник населённых пунктов для поля «Город» (файл places.sqlite собирает tools/build_places.py).
Пока файла нет, город можно вписать вручную, как раньше."""
import os
import re
import sqlite3

import config

PLACES_DB = os.environ.get("PLACES_DB") or os.path.join(config.BASE_DIR, "places.sqlite")


def norm(text):
    return re.sub(r"\s+", " ", (text or "").lower().replace("ё", "е")).strip()


def available():
    return os.path.exists(PLACES_DB)


def _conn():
    return sqlite3.connect(f"file:{PLACES_DB}?mode=ro", uri=True)


def search(q, limit=10):
    """Подсказки по началу названия: сначала крупные места."""
    key = norm(q)
    if len(key) < 2 or not available():
        return []
    with _conn() as db:
        rows = db.execute("SELECT DISTINCT p.label FROM names n JOIN places p ON p.id = n.id WHERE n.key >= ? AND n.key < ? "
                          "ORDER BY n.pop DESC LIMIT ?", (key, key + "￿", limit * 3)).fetchall()
    out = []
    for (label,) in rows:
        if label not in out:
            out.append(label)
    return out[:limit]


def exists(label):
    if not available():
        return True
    with _conn() as db:
        return db.execute("SELECT 1 FROM places WHERE label = ? LIMIT 1", (label,)).fetchone() is not None
