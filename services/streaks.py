"""Огоньки в личных чатах (как в TikTok).

Огонёк растёт, если оба собеседника пишут друг другу каждый день. День считается по часовому поясу
пользователя. Если сегодня кто-то ещё не написал, огонёк «тлеет» — его можно спасти до полуночи.
"""
from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_

import models
from services import timezones

MIN_DAYS = 3  # огонёк появляется после трёх дней подряд, как в TikTok
LOOKBACK = 400


def _local_date(db, offset_minutes):
    """SQL-выражение «дата сообщения в поясе пользователя» для SQLite и PostgreSQL."""
    col = models.Message.created_at
    if db.bind.dialect.name == "sqlite":
        return func.date(col, f"{offset_minutes:+d} minutes")
    return func.date(col + timedelta(minutes=offset_minutes))


def chat_streaks(db, user, peer_ids):
    """{peer_id: (дней подряд, тлеет ли)} — только для огоньков от MIN_DAYS дней."""
    peer_ids = [p for p in set(peer_ids) if p]
    if not user or not peer_ids:
        return {}
    tz = timezones.tzinfo(timezones.user_key(user))
    now_local = datetime.now(tz)
    offset = int((now_local.utcoffset() or timedelta(0)).total_seconds() // 60)
    since = datetime.utcnow() - timedelta(days=LOOKBACK)
    day = _local_date(db, offset)
    rows = (db.query(models.Message.sender_id, models.Message.receiver_id, day)
            .filter(models.Message.group_id == None, models.Message.created_at >= since,
                    or_(and_(models.Message.sender_id == user.id, models.Message.receiver_id.in_(peer_ids)),
                        and_(models.Message.receiver_id == user.id, models.Message.sender_id.in_(peer_ids))))
            .distinct().all())
    sent, got = {}, {}
    for s, r, d in rows:
        d = d if isinstance(d, str) else d.isoformat()
        if s == user.id:
            sent.setdefault(r, set()).add(d)
        else:
            got.setdefault(s, set()).add(d)
    today = now_local.date()
    out = {}
    for pid in peer_ids:
        both = sent.get(pid, set()) & got.get(pid, set())
        if not both:
            continue
        start, risk = today, False
        if today.isoformat() not in both:
            start, risk = today - timedelta(days=1), True
        n = 0
        while (start - timedelta(days=n)).isoformat() in both:
            n += 1
        if n >= MIN_DAYS:
            out[pid] = (n, risk)
    return out


def level(days):
    return "legend" if days >= 100 else "hot" if days >= 30 else "warm" if days >= 7 else ""
