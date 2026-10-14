"""Вспомогательная логика новых функций: подарки, «Возможно, вы знакомы», время чтения, воспоминания, интересы."""
import re
from datetime import datetime

from sqlalchemy import func

import models

# --- Подарки за очки --------------------------------------------------------------------------------------
GIFTS = [
    ("heart", "❤️", "Сердечко", 10), ("rose", "🌹", "Роза", 20), ("coffee", "☕", "Кофе", 25), ("cake", "🎂", "Тортик", 40),
    ("bear", "🧸", "Мишка", 50), ("star", "⭐", "Звезда", 60), ("fire", "🔥", "Огонь", 75), ("balloon", "🎈", "Шарик", 30),
    ("trophy", "🏆", "Кубок", 120), ("crown", "👑", "Корона", 200), ("diamond", "💎", "Бриллиант", 300), ("rocket", "🚀", "Ракета", 500),
]
GIFT_BY_CODE = {g[0]: g for g in GIFTS}


def balance(user):
    """Очки, которые можно потратить. Уровень считается по всем заработанным очкам и от трат не падает."""
    return max(0, (user.total_points or 0) - (user.spent_points or 0))


# --- Возможно, вы знакомы -----------------------------------------------------------------------------------
def people_you_may_know(db, user, limit=6):
    """Друзья друзей: на кого подписаны ваши подписки, отсортировано по числу общих знакомых.
    Если таких мало — добираем людьми с общими интересами."""
    from services import prefs, social
    if not user:
        return []
    mine = social.following_ids(db, user)
    excl = mine | social.blocked_ids(db, user) | {user.id}
    out = []
    if mine:
        rows = (db.query(models.Follow.following_id, func.count(models.Follow.id).label("n"))
                .filter(models.Follow.follower_id.in_(mine), ~models.Follow.following_id.in_(excl))
                .group_by(models.Follow.following_id).order_by(func.count(models.Follow.id).desc()).limit(limit * 3).all())
        users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_([r[0] for r in rows] or [-1]), models.User.is_blocked == False)}
        for uid, n in rows:
            u = users.get(uid)
            if u and not prefs.get(u, "hide_from_search"):
                out.append((u, f"{n} общ. {'знакомый' if n == 1 else 'знакомых'}"))
    mytags = set(interests(user))
    if len(out) < limit and mytags:
        taken = {u.id for u, _ in out} | excl
        for u in db.query(models.User).filter(models.User.interests != "", models.User.interests != None, ~models.User.id.in_(taken),
                                              models.User.is_blocked == False).limit(200):
            common = mytags & set(interests(u))
            if common and not prefs.get(u, "hide_from_search"):
                out.append((u, "тоже любит " + ", ".join("#" + t for t in sorted(common)[:2])))
            if len(out) >= limit:
                break
    return out[:limit]


# --- Интересы ------------------------------------------------------------------------------------------------
def parse_interests(text):
    tags = []
    for t in re.split(r"[,#\s]+", (text or "").lower()):
        t = re.sub(r"[^\wа-яё\-]", "", t)[:30]
        if len(t) >= 2 and t not in tags:
            tags.append(t)
    return tags[:10]


def interests(user):
    return parse_interests(user.interests) if user and user.interests else []


# --- Время чтения ----------------------------------------------------------------------------------------------
def reading_minutes(text):
    words = len((text or "").split())
    return max(1, round(words / 180))


# --- В этот день ---------------------------------------------------------------------------------------------
def memories(db, user, today=None):
    """Посты пользователя, опубликованные в этот же день в прошлые годы."""
    if not user:
        return []
    today = today or datetime.utcnow()
    md = today.strftime("%m-%d")
    q = (db.query(models.Post).filter(models.Post.user_id == user.id, models.Post.is_draft == False,
                                      func.strftime("%m-%d", models.Post.created_at) == md,
                                      func.strftime("%Y", models.Post.created_at) != today.strftime("%Y")))
    try:
        return q.order_by(models.Post.created_at.desc()).limit(20).all()
    except Exception:  # PostgreSQL: нет strftime — считаем в Python
        db.rollback()
        posts = db.query(models.Post).filter(models.Post.user_id == user.id, models.Post.is_draft == False).limit(2000).all()
        return [p for p in posts if p.created_at.strftime("%m-%d") == md and p.created_at.year != today.year][:20]
