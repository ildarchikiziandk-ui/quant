"""Nuvora+: оформление значка и возможности подписки."""
import re

# Цвета PLUS-значка и обложки: ключ, название, CSS-фон
PALETTE = [
    ("violet", "Фиалка", "linear-gradient(135deg,#a78bfa,#6d28d9)"),
    ("aurora", "Северное сияние", "linear-gradient(120deg,#22d3ee,#a855f7 55%,#ec4899)"),
    ("ocean", "Океан", "linear-gradient(135deg,#22d3ee,#2563eb)"),
    ("sky", "Небо", "linear-gradient(135deg,#7dd3fc,#3b82f6)"),
    ("mint", "Мята", "linear-gradient(135deg,#6ee7b7,#059669)"),
    ("emerald", "Изумруд", "linear-gradient(135deg,#10b981,#065f46)"),
    ("lime", "Лайм", "linear-gradient(135deg,#bef264,#16a34a)"),
    ("gold", "Золото", "linear-gradient(135deg,#fde047,#f59e0b 50%,#b45309)"),
    ("sunset", "Закат", "linear-gradient(135deg,#fb923c,#db2777)"),
    ("fire", "Пламя", "linear-gradient(135deg,#facc15,#ef4444)"),
    ("peach", "Персик", "linear-gradient(135deg,#fdba74,#fb7185)"),
    ("rose", "Роза", "linear-gradient(135deg,#fb7185,#be123c)"),
    ("candy", "Карамель", "linear-gradient(135deg,#f472b6,#8b5cf6)"),
    ("grape", "Виноград", "linear-gradient(135deg,#c084fc,#7e22ce)"),
    ("night", "Ночь", "linear-gradient(135deg,#475569,#0f172a)"),
    ("graphite", "Графит", "linear-gradient(135deg,#a1a1aa,#27272a)"),
    ("rainbow", "Радуга", "linear-gradient(90deg,#ef4444,#f59e0b,#22c55e,#3b82f6,#a855f7)"),
    ("cosmos", "Космос", "linear-gradient(135deg,#1e1b4b,#7c3aed 60%,#f0abfc)"),
]
PALETTE_BY = {k: css for k, _, css in PALETTE}
DEFAULT = "violet"
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def valid_color(value):
    return value in PALETTE_BY or bool(HEX.match(value or ""))


def bg(user):
    """CSS-фон для значка и обложки пользователя."""
    c = (user.plus_color if user else "") or DEFAULT
    if c in PALETTE_BY:
        return PALETTE_BY[c]
    if HEX.match(c):
        return f"linear-gradient(135deg,{c},color-mix(in srgb,{c} 60%,#000))"
    return PALETTE_BY[DEFAULT]
