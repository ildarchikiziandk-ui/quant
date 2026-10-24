"""Оформление чатов и свои имена контактов.

Свои имена: пользователь может записать контакт как угодно («Мама», «Саша работа»). Имя видит только он —
в чатах, профиле, ленте и уведомлениях. Имена загружаются один раз на запрос (см. deps.base_context).
"""
import contextvars

import models

_names = contextvars.ContextVar("contact_names", default={})

# фоны чата: ключ, название, CSS
WALLPAPERS = [
    ("", "Без фона", ""),
    ("whales", "Киты", "url('/static/wallpapers/whales.svg') center/220px repeat, var(--wp-base,#e8eef7)"),
    ("dots", "Точки", "radial-gradient(color-mix(in srgb,var(--text) 14%,transparent) 1.2px,transparent 1.4px) 0 0/22px 22px, var(--bg)"),
    ("ocean", "Океан", "linear-gradient(160deg,#a5f3fc,#3b82f6 60%,#1e3a8a)"),
    ("sunset", "Закат", "linear-gradient(170deg,#fde68a,#fb7185 55%,#7c3aed)"),
    ("mint", "Мята", "linear-gradient(160deg,#d1fae5,#6ee7b7 60%,#0f766e)"),
    ("lavender", "Лаванда", "linear-gradient(160deg,#ede9fe,#c4b5fd 55%,#7c3aed)"),
    ("peach", "Персик", "linear-gradient(160deg,#ffedd5,#fdba74 60%,#ea580c)"),
    ("night", "Ночь", "radial-gradient(1px 1px at 20% 30%,#fff 50%,transparent 51%) 0 0/120px 120px, radial-gradient(1px 1px at 70% 80%,#fff 50%,transparent 51%) 0 0/90px 90px, linear-gradient(180deg,#0f172a,#1e1b4b)"),
    ("aurora", "Сияние", "linear-gradient(120deg,#22d3ee,#a855f7 55%,#ec4899)"),
    ("graphite", "Графит", "linear-gradient(160deg,#3f3f46,#18181b)"),
]
WP = {k: css for k, _, css in WALLPAPERS}
DARK_WP = {"ocean", "sunset", "night", "aurora", "graphite", "mint", "lavender", "peach"}  # на них светлый текст подписей

# цвет моих сообщений
BUBBLES = [("", "Как в теме", ""), ("blue", "Синий", "#2563eb"), ("violet", "Фиолетовый", "#7c3aed"), ("pink", "Розовый", "#db2777"),
           ("green", "Зелёный", "#16a34a"), ("teal", "Бирюзовый", "#0d9488"), ("orange", "Оранжевый", "#ea580c"),
           ("red", "Красный", "#dc2626"), ("graphite", "Графит", "#3f3f46")]
BUBBLE = {k: c for k, _, c in BUBBLES}
FONTS = [("", "Обычный"), ("s", "Мелкий"), ("l", "Крупный"), ("xl", "Очень крупный")]
FONT_KEYS = {k for k, _ in FONTS}


# ---------------------------------------------------------------- свои имена
def load_names(db, user):
    names = {}
    if user:
        names = {c.target_id: c.name for c in db.query(models.ContactName).filter_by(owner_id=user.id) if c.name}
    _names.set(names)
    return names


def name_of(u):
    """Имя для показа текущему пользователю: своё имя контакта или имя из профиля."""
    if not u:
        return ""
    return _names.get().get(getattr(u, "id", None)) or u.name or u.username


def custom_name(u):
    return _names.get().get(getattr(u, "id", None)) if u else None


def set_name(db, owner, target, name):
    row = db.query(models.ContactName).filter_by(owner_id=owner.id, target_id=target.id).first()
    name = (name or "").strip()[:60]
    if not name:
        if row:
            db.delete(row)
    elif row:
        row.name = name
    else:
        db.add(models.ContactName(owner_id=owner.id, target_id=target.id, name=name))
    db.commit()


# ---------------------------------------------------------------- настройки чата
def setting(db, user, peer_id=None, group_id=None, create=False):
    q = db.query(models.ChatSetting).filter_by(user_id=user.id, peer_id=peer_id, group_id=group_id)
    row = q.first()
    if not row and create:
        row = models.ChatSetting(user_id=user.id, peer_id=peer_id, group_id=group_id)
        db.add(row)
    return row


def look(db, user, peer_id=None, group_id=None):
    """Оформление чата: своё для этого чата или общее (peer_id=0)."""
    own = setting(db, user, peer_id, group_id) if (peer_id or group_id) else None
    base = setting(db, user, 0, None)
    wp = (own.wallpaper if own and own.wallpaper else (base.wallpaper if base else "")) or ""
    bubble = (own.bubble if own and own.bubble else (base.bubble if base else "")) or ""
    font = (own.font if own and own.font else (base.font if base else "")) or ""
    css = WP.get(wp)
    if css is None and wp.startswith("/uploads/"):
        css = f"url('{wp}') center/cover no-repeat fixed, var(--bg)"
    return {"wallpaper": wp, "wp_css": css or "", "bubble": bubble, "bubble_color": BUBBLE.get(bubble, ""), "font": font,
            "dark": wp in DARK_WP or wp.startswith("/uploads/"), "own": bool(own and (own.wallpaper or own.bubble or own.font))}
