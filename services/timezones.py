"""Часовые пояса пользователей.

Каждый город — отдельный пункт, даже если смещение совпадает (например, Новосибирск и Красноярск —
оба UTC+7, но это разные пояса со своей историей и своим названием). Время в базе хранится в UTC,
а показывается в поясе пользователя.
"""
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

DEFAULT = "moscow"

# ключ, город, IANA-зона, запасное смещение (часы) — если в системе нет базы tzdata
ZONES = [
    ("kaliningrad", "Калининград", "Europe/Kaliningrad", 2),
    ("moscow", "Москва", "Europe/Moscow", 3),
    ("spb", "Санкт-Петербург", "Europe/Moscow", 3),
    ("kazan", "Казань", "Europe/Moscow", 3),
    ("nnovgorod", "Нижний Новгород", "Europe/Moscow", 3),
    ("rostov", "Ростов-на-Дону", "Europe/Moscow", 3),
    ("krasnodar", "Краснодар", "Europe/Moscow", 3),
    ("simferopol", "Симферополь", "Europe/Simferopol", 3),
    ("kirov", "Киров", "Europe/Kirov", 3),
    ("volgograd", "Волгоград", "Europe/Volgograd", 3),
    ("samara", "Самара", "Europe/Samara", 4),
    ("ulyanovsk", "Ульяновск", "Europe/Ulyanovsk", 4),
    ("saratov", "Саратов", "Europe/Saratov", 4),
    ("astrakhan", "Астрахань", "Europe/Astrakhan", 4),
    ("izhevsk", "Ижевск", "Europe/Samara", 4),
    ("yekaterinburg", "Екатеринбург", "Asia/Yekaterinburg", 5),
    ("chelyabinsk", "Челябинск", "Asia/Yekaterinburg", 5),
    ("ufa", "Уфа", "Asia/Yekaterinburg", 5),
    ("perm", "Пермь", "Asia/Yekaterinburg", 5),
    ("tyumen", "Тюмень", "Asia/Yekaterinburg", 5),
    ("omsk", "Омск", "Asia/Omsk", 6),
    ("novosibirsk", "Новосибирск", "Asia/Novosibirsk", 7),
    ("krasnoyarsk", "Красноярск", "Asia/Krasnoyarsk", 7),
    ("barnaul", "Барнаул", "Asia/Barnaul", 7),
    ("tomsk", "Томск", "Asia/Tomsk", 7),
    ("novokuznetsk", "Новокузнецк", "Asia/Novokuznetsk", 7),
    ("kemerovo", "Кемерово", "Asia/Novokuznetsk", 7),
    ("irkutsk", "Иркутск", "Asia/Irkutsk", 8),
    ("ulanude", "Улан-Удэ", "Asia/Irkutsk", 8),
    ("chita", "Чита", "Asia/Chita", 9),
    ("yakutsk", "Якутск", "Asia/Yakutsk", 9),
    ("blagoveshchensk", "Благовещенск", "Asia/Yakutsk", 9),
    ("vladivostok", "Владивосток", "Asia/Vladivostok", 10),
    ("khabarovsk", "Хабаровск", "Asia/Vladivostok", 10),
    ("magadan", "Магадан", "Asia/Magadan", 11),
    ("sakhalin", "Южно-Сахалинск", "Asia/Sakhalin", 11),
    ("srednekolymsk", "Среднеколымск", "Asia/Srednekolymsk", 11),
    ("kamchatka", "Петропавловск-Камчатский", "Asia/Kamchatka", 12),
    ("anadyr", "Анадырь", "Asia/Anadyr", 12),
    # соседи и мир
    ("minsk", "Минск", "Europe/Minsk", 3),
    ("kyiv", "Киев", "Europe/Kyiv", 2),
    ("chisinau", "Кишинёв", "Europe/Chisinau", 2),
    ("riga", "Рига", "Europe/Riga", 2),
    ("tbilisi", "Тбилиси", "Asia/Tbilisi", 4),
    ("yerevan", "Ереван", "Asia/Yerevan", 4),
    ("baku", "Баку", "Asia/Baku", 4),
    ("astana", "Астана", "Asia/Almaty", 5),
    ("almaty", "Алматы", "Asia/Almaty", 5),
    ("tashkent", "Ташкент", "Asia/Tashkent", 5),
    ("dushanbe", "Душанбе", "Asia/Dushanbe", 5),
    ("bishkek", "Бишкек", "Asia/Bishkek", 6),
    ("ashgabat", "Ашхабад", "Asia/Ashgabat", 5),
    ("istanbul", "Стамбул", "Europe/Istanbul", 3),
    ("dubai", "Дубай", "Asia/Dubai", 4),
    ("berlin", "Берлин", "Europe/Berlin", 1),
    ("london", "Лондон", "Europe/London", 0),
    ("newyork", "Нью-Йорк", "America/New_York", -5),
    ("bangkok", "Бангкок", "Asia/Bangkok", 7),
    ("beijing", "Пекин", "Asia/Shanghai", 8),
    ("tokyo", "Токио", "Asia/Tokyo", 9),
    ("utc", "UTC (всемирное время)", "UTC", 0),
]
BY_KEY = {z[0]: z for z in ZONES}
_tz_cache = {}


def tzinfo(key):
    key = key if key in BY_KEY else DEFAULT
    if key not in _tz_cache:
        _, _, iana, off = BY_KEY[key]
        tz = None
        if ZoneInfo:
            try:
                tz = ZoneInfo(iana)
            except Exception:
                tz = None
        _tz_cache[key] = tz or timezone(timedelta(hours=off))
    return _tz_cache[key]


def offset_label(key):
    off = datetime.now(tzinfo(key)).utcoffset() or timedelta(0)
    total = int(off.total_seconds() // 60)
    sign = "+" if total >= 0 else "−"
    h, m = divmod(abs(total), 60)
    return f"UTC{sign}{h}" + (f":{m:02d}" if m else "")


def options():
    return [(k, f"{city} ({offset_label(k)})") for k, city, _, _ in ZONES]


def iana_map():
    """{IANA: ключ} — для автоопределения пояса по устройству (первый город с такой зоной)."""
    out = {}
    for k, _, iana, _ in ZONES:
        out.setdefault(iana, k)
    return out


def user_key(user):
    from services import prefs
    return prefs.get(user, "timezone") if user else DEFAULT


def to_local(dt, user):
    if not dt:
        return dt
    return dt.replace(tzinfo=timezone.utc).astimezone(tzinfo(user_key(user))).replace(tzinfo=None)


def from_local(dt, user):
    """Время, введённое пользователем в его поясе → UTC (без tzinfo, как хранится в базе)."""
    if not dt:
        return dt
    return dt.replace(tzinfo=tzinfo(user_key(user))).astimezone(timezone.utc).replace(tzinfo=None)


def city(user):
    return BY_KEY.get(user_key(user), BY_KEY[DEFAULT])[1]
