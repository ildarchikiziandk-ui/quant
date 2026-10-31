"""Вспомогательная логика новых функций: подарки, «Возможно, вы знакомы», время чтения, воспоминания, интересы."""
import re
from datetime import datetime

from sqlalchemy import func

import models

# --- Подарки за искры --------------------------------------------------------------------------------------
# (код, эмодзи для текста, название, цена в искрах). Картинки — static/gifts/<код>.svg (рисует tools/gift_art.py).
REGULAR = [
    ("heart", "❤️", "Сердечко", 10), ("rose", "🌹", "Роза", 20), ("cake", "🎂", "Тортик", 40), ("bear", "🧸", "Мишка", 50),
    ("whale", "🐋", "Кит Nuvora", 150), ("crown", "👑", "Корона", 200), ("diamond", "💎", "Бриллиант", 300), ("rocket", "🚀", "Ракета", 500),
]
# «Коллекция» — дорогие подарки, доступны всегда
PREMIUM = [
    ("castle", "🏰", "Замок", 1000), ("unicorn", "🦄", "Единорог", 1500), ("golden_whale", "🐳", "Золотой кит", 3500), ("phoenix", "🔥", "Феникс", 5000),
]
# Сняты с продажи 31.10.2026 (владелец: «подарков слишком много»). Уже подаренные остаются у получателей.
RETIRED = [
    ("coffee", "☕", "Кофе", 24), ("balloon", "🎈", "Шарик", 30), ("star", "⭐", "Звезда", 60), ("fire", "🔥", "Огонь", 70),
    ("trophy", "🏆", "Кубок", 120), ("aurora", "✨", "Северное сияние", 240), ("yacht", "⛵", "Яхта", 2000), ("planet", "🪐", "Планета", 2500),
]
# Лимитированные — по одному на месяц. Скрыты, пока владелец не «дропнет» их в админке (/admin/gifts).
LIMITED = [
    ("snowglobe", "🔮", "Снежный шар", 400, "ноябрь 2026"), ("xmas_tree", "🎄", "Новогодняя ёлка", 600, "декабрь 2026"),
    ("snowman", "⛄", "Снеговик", 450, "январь 2027"), ("valentine", "💌", "Валентинка", 500, "февраль 2027"),
    ("mimosa", "🌼", "Мимоза", 400, "март 2027"), ("cosmonaut", "👨‍🚀", "Космонавт", 600, "апрель 2027"),
    ("lilac", "💜", "Сирень", 400, "май 2027"), ("icecream", "🍦", "Мороженое", 400, "июнь 2027"),
    ("watermelon", "🍉", "Арбуз", 450, "июль 2027"), ("shooting_star", "🌠", "Звездопад", 550, "август 2027"),
    ("maple", "🍁", "Кленовый лист", 400, "сентябрь 2027"), ("pumpkin", "🎃", "Тыква", 500, "октябрь 2027"),
]
FOUNDER = ("founder", "🏅", "Подарок от создателя", 0)  # дарить может только основатель сайта
LIMITED_SUPPLY = 100  # тираж по умолчанию при дропе

GIFTS = REGULAR + PREMIUM + [g[:4] for g in LIMITED] + [FOUNDER] + RETIRED
GIFT_BY_CODE = {g[0]: g for g in GIFTS}
KIND = {**{g[0]: "regular" for g in REGULAR}, **{g[0]: "premium" for g in PREMIUM}, **{g[0]: "limited" for g in LIMITED}, FOUNDER[0]: "founder", **{g[0]: "retired" for g in RETIRED}}
LIMITED_MONTH = {g[0]: g[4] for g in LIMITED}


def drops():
    """Состояние лимитированных: {код: {"on": bool, "supply": int}} — меняется в админке."""
    from packs.v3 import site
    return site.get("gift_drops") or {}


def sold(db, code):
    return db.query(func.count(models.UserGift.id)).filter(models.UserGift.gift_code == code).scalar() or 0


def is_founder(user):
    return bool(user and user.is_owner and not user.co_owner)


def gift_state(db, code, user=None):
    """Можно ли сейчас дарить: (можно, причина/подпись, сколько осталось или None)."""
    kind = KIND.get(code)
    if kind == "retired":
        return False, "Больше не продаётся", None
    if kind == "founder":
        return is_founder(user), ("Дарить может только создатель Nuvora" if not is_founder(user) else ""), None
    if kind == "limited":
        st = drops().get(code) or {}
        if not st.get("on"):
            return False, "Ещё не вышел" if not st.get("ever") else "Продажи закрыты", 0
        supply = int(st.get("supply") or 0)
        if supply:
            left = max(0, supply - sold(db, code))
            return left > 0, ("Распродан" if not left else ""), left
        return True, "", None
    return True, "", None


def serial(db, ug):
    """Номер экземпляра лимитированного подарка: «№12»."""
    return db.query(func.count(models.UserGift.id)).filter(models.UserGift.gift_code == ug.gift_code, models.UserGift.id <= ug.id).scalar() or 1


OWNER_BALANCE = 10 ** 9  # у владельца искры бесконечные: показываются как «∞», траты их не уменьшают


def balance(user):
    """Искры, которые можно потратить. Уровень считается по всем заработанным искрам и от трат не падает."""
    if user and user.is_owner:
        return OWNER_BALANCE
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


# --- Посты: настроение, фон, срок жизни ----------------------------------------------------------------------
MOODS = [("happy", "😊", "радостно"), ("love", "🥰", "влюблённо"), ("cool", "😎", "круто"), ("party", "🥳", "празднично"),
         ("chill", "😌", "спокойно"), ("think", "🤔", "задумчиво"), ("tired", "😴", "устало"), ("sad", "😢", "грустно"),
         ("angry", "😤", "злюсь"), ("sick", "🤒", "болею"), ("proud", "💪", "горжусь собой"), ("hungry", "🍕", "голодно")]
MOOD_BY = {m[0]: m for m in MOODS}
BGS = [("graphite", "Графит"), ("sand", "Песок"), ("mint", "Мята"), ("sky", "Небо"), ("sunset", "Закат"), ("night", "Ночь")]
BG_KEYS = {b[0] for b in BGS}
EXPIRES = [("", "Не удалять"), ("24", "Через 24 часа"), ("72", "Через 3 дня"), ("168", "Через неделю")]

# --- Рамки аватарок за искры ------------------------------------------------------------------------------------
FRAMES = [("silver", "Серебро", 100), ("gold", "Золото", 250), ("neon", "Неон", 300), ("fire", "Огонь", 400), ("galaxy", "Галактика", 600)]
FRAME_BY = {f[0]: f for f in FRAMES}
STREAK_FREEZE_PRICE = 50

# --- Колесо фортуны: раз в сутки ------------------------------------------------------------------------------
WHEEL = [3, 5, 5, 8, 10, 13, 15, 25]


def spin_prize(user_id, day):
    """Детерминированный результат на день — нельзя «перекрутить» обновлением страницы."""
    import zlib
    return WHEEL[zlib.crc32(f"{user_id}:{day}:wheel".encode()) % len(WHEEL)]


# --- Знак зодиака по дню рождения ---------------------------------------------------------------------------------
_ZODIAC = [((1, 20), "♑", "Козерог"), ((2, 19), "♒", "Водолей"), ((3, 21), "♓", "Рыбы"), ((4, 20), "♈", "Овен"), ((5, 21), "♉", "Телец"),
           ((6, 22), "♊", "Близнецы"), ((7, 23), "♋", "Рак"), ((8, 23), "♌", "Лев"), ((9, 23), "♍", "Дева"), ((10, 24), "♎", "Весы"),
           ((11, 23), "♏", "Скорпион"), ((12, 22), "♐", "Стрелец"), ((12, 32), "♑", "Козерог")]


def zodiac(birthday):
    try:
        m, d = int(birthday[5:7]), int(birthday[8:10])
    except (TypeError, ValueError):
        return None
    for (bm, bd), sign, title in _ZODIAC:
        if (m, d) < (bm, bd):
            return sign, title
    return None


# --- Праздники (фиксированные даты) ------------------------------------------------------------------------------
HOLIDAYS = {"01-01": ("🎄", "Новый год"), "01-07": ("⭐", "Рождество"), "01-25": ("🎓", "Татьянин день"), "02-14": ("💌", "День святого Валентина"),
            "02-23": ("🎖", "День защитника Отечества"), "03-08": ("🌷", "Международный женский день"), "04-01": ("🤡", "День смеха"),
            "04-12": ("🚀", "День космонавтики"), "05-01": ("🌿", "Праздник Весны и Труда"), "05-09": ("🎗", "День Победы"), "06-01": ("🧸", "День защиты детей"),
            "06-12": ("🇷🇺", "День России"), "07-08": ("💞", "День семьи, любви и верности"), "09-01": ("📚", "День знаний"), "09-13": ("💻", "День программиста"),
            "10-05": ("🍎", "День учителя"), "11-04": ("🤝", "День народного единства"), "12-31": ("🥂", "Канун Нового года")}


def holiday_today(now=None):
    return HOLIDAYS.get((now or datetime.utcnow()).strftime("%m-%d"))


# --- Ссылки в профиле --------------------------------------------------------------------------------------------
def parse_links(raw):
    import json
    try:
        data = json.loads(raw or "[]")
    except ValueError:
        return []
    out = []
    for item in data[:10]:
        if isinstance(item, dict) and item.get("url"):
            out.append({"title": str(item.get("title") or "")[:40], "url": str(item["url"])[:200]})
    return out


def status_active(user, now=None):
    return bool(user and user.status_text and (not user.status_until or user.status_until > (now or datetime.utcnow())))
