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


# ---------------------------------------------------------------------------------------------------------
def active(user):
    from services import social
    return social.is_plus(user)


# лимиты: (обычный аккаунт, Plus)
LIMITS = {"post_length": (5000, 15000), "post_media": (10, 20), "bio": (300, 600), "links": (5, 10),
          "voice": (300, 900), "circle": (60, 120)}


def limit(user, key):
    free, plus_value = LIMITS[key]
    return plus_value if active(user) else free


POINTS_MULT = 1.5   # искры за активность
GIFT_DISCOUNT = .3  # скидка на подарки
SHIELD_DAYS = 7     # защита стрика: один пропуск раз в неделю


def points(user, value):
    return int(round(value * POINTS_MULT)) if value > 0 and active(user) else value


def gift_price(user, price):
    return int(round(price * (1 - GIFT_DISCOUNT))) if active(user) else price


# дополнительные цвета акцента и фоны постов — только для Plus
ACCENTS = ["#ec4899", "#f97316", "#06b6d4", "#8b5cf6", "#84cc16", "#e11d48", "#0ea5e9", "#a16207"]
BGS = [("aurora", "Сияние"), ("cosmos", "Космос"), ("goldbg", "Золото"), ("ocean", "Океан")]
BG_KEYS = {k for k, _ in BGS}
EXCLUSIVE_GIFTS = {"whale", "aurora"}
EXPIRES = [("1", "Через 1 час"), ("6", "Через 6 часов")]

FEATURES = [
    ("Оформление", [
        ("sparkle", "Значок PLUS", "18 цветов и градиентов на выбор или свой цвет"),
        ("palette", "Цветное имя", "Имя в постах и комментариях переливается цветом вашего значка"),
        ("circle", "Сияющая аватарка", "Анимированное кольцо вокруг фото профиля"),
        ("image", "Цветная обложка", "Если обложки нет — профиль окрашен в ваш цвет"),
        ("bag", "Все рамки бесплатно", "Любые рамки аватарки из магазина — без искр"),
        ("contrast", "Эксклюзивные цвета", "8 дополнительных акцентных цветов интерфейса"),
        ("layers", "Фоны для постов", "4 эксклюзивных фона: сияние, космос, золото, океан"),
        ("gift", "Особые подарки", "«Кит Nuvora» и «Северное сияние» дарят только с Plus"),
    ]),
    ("Возможности", [
        ("hourglass", "Исчезающие посты на час", "Таймеры удаления поста на 1 и 6 часов"),
        ("note", "Длинные посты", "До 15 000 символов вместо 5 000"),
        ("image", "20 фото и видео", "В одном посте — вдвое больше вложений"),
        ("mic", "Длинные голосовые", "Голосовые до 15 минут, кружки до 2 минут"),
        ("user", "Расширенный профиль", "Описание до 600 символов и до 10 ссылок"),
    ]),
    ("Игры и искры", [
        ("bolt", "×1,5 искр", "За посты, лайки, задания и активность"),
        ("wheel", "Два вращения колеса", "Второй шанс в колесе фортуны каждый день"),
        ("snowflake", "Защита стрика", "Один пропущенный день в неделю не обнуляет серию"),
        ("gift", "Скидка 30% на подарки", "Дарите больше за те же искры"),
        ("lifebuoy", "Приоритетная поддержка", "Ваши обращения рассматриваются первыми"),
    ]),
]
