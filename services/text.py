"""Работа с текстом: безопасная разметка (#теги, @упоминания, ссылки), «время назад», фильтр стоп-слов."""
import re
from datetime import datetime

from markupsafe import Markup, escape

HASHTAG_RE = re.compile(r"(?<![\w&])#(\w{1,64})", re.UNICODE)
MENTION_RE = re.compile(r"(?<![\w@])@([A-Za-z0-9_]{3,30})")
URL_RE = re.compile(r"(https?://[^\s<]+[^\s<.,:;\"')\]!?])")


def extract_hashtags(text):
    return {t.lower() for t in HASHTAG_RE.findall(text or "")}


def extract_mentions(text):
    return {m for m in MENTION_RE.findall(text or "")}


def richtext(text):
    """Экранирует текст и превращает ссылки, теги и упоминания в ссылки."""
    if not text:
        return Markup("")
    out = []
    pos = 0
    raw = str(text)
    for m in URL_RE.finditer(raw):
        out.append(_tags_and_mentions(raw[pos:m.start()]))
        url = str(escape(m.group(1)))
        label = url if len(url) <= 60 else url[:57] + "…"
        out.append(f'<a href="{url}" target="_blank" rel="noopener nofollow ugc" class="rt-link">{label}</a>')
        pos = m.end()
    out.append(_tags_and_mentions(raw[pos:]))
    return Markup("".join(out).replace("\n", "<br>"))


def _tags_and_mentions(chunk):
    s = str(escape(chunk))
    s = HASHTAG_RE.sub(lambda m: f'<a href="/hashtag/{m.group(1).lower()}" class="rt-tag">#{m.group(1)}</a>', s)
    s = MENTION_RE.sub(lambda m: f'<a href="/profile/{m.group(1)}" class="rt-mention">@{m.group(1)}</a>', s)
    return s


def _plural(n, one, few, many):
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def plural(n, one, few, many):
    return f"{n} {_plural(n, one, few, many)}"


def timeago(dt):
    if not dt:
        return "давно"
    sec = int((datetime.utcnow() - dt).total_seconds())
    if sec < 0:
        return "по расписанию"
    if sec < 45:
        return "только что"
    if sec < 3600:
        m = max(1, sec // 60)
        return f"{m} {_plural(m, 'минуту', 'минуты', 'минут')} назад"
    if sec < 86400:
        h = sec // 3600
        return f"{h} {_plural(h, 'час', 'часа', 'часов')} назад"
    if sec < 86400 * 7:
        d = sec // 86400
        return "вчера" if d == 1 else f"{d} {_plural(d, 'день', 'дня', 'дней')} назад"
    months = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
    if dt.year == datetime.utcnow().year:
        return f"{dt.day} {months[dt.month - 1]}"
    return f"{dt.day} {months[dt.month - 1]} {dt.year}"


def compact_number(n):
    n = n or 0
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".") + "M"
    if n >= 1000:
        return f"{n / 1000:.1f}".rstrip("0").rstrip(".") + "K"
    return str(n)


def filesize(n):
    n = n or 0
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "Б" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} ТБ"


def censor(text, stop_words):
    """Заменяет стоп-слова звёздочками."""
    if not text or not stop_words:
        return text
    for w in stop_words:
        if not w:
            continue
        text = re.sub(re.escape(w), lambda m: m.group(0)[0] + "*" * (len(m.group(0)) - 1), text, flags=re.IGNORECASE)
    return text
