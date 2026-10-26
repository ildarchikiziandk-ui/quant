"""Работа с текстом: безопасная разметка (#теги, @упоминания, ссылки), «время назад», фильтр стоп-слов."""
import re
from datetime import datetime

from markupsafe import Markup, escape

HASHTAG_RE = re.compile(r"(?<![\w&])#(\w{1,64})", re.UNICODE)
MENTION_RE = re.compile(r"(?<![\w@])@([A-Za-z0-9_]{3,30})")
URL_RE = re.compile(r"(https?://[^\s<]+[^\s<.,:;\"')\]!?])")


# --- Эмодзи → SVG (Twemoji, CC-BY 4.0) ------------------------------------------------------------------------
# Эмодзи в тексте пользователей рисуются одинаковыми SVG-картинками на всех устройствах.
_EMOJI_DIR = __import__("os").path.join(__import__("os").path.dirname(__file__), "..", "static", "emoji")
try:
    _EMOJI_FILES = {f[:-4] for f in __import__("os").listdir(_EMOJI_DIR) if f.endswith(".svg")}
except OSError:
    _EMOJI_FILES = set()
_EMOJI_DEFAULT = ("\u2764\u231a\u231b\u23e9-\u23ec\u23f0\u23f3\u25fd\u25fe\u2614\u2615\u2648-\u2653\u267f\u2693\u26a1"
                  "\u26aa\u26ab\u26bd\u26be\u26c4\u26c5\u26ce\u26d4\u26ea\u26f2\u26f3\u26f5\u26fa\u26fd\u2705\u270a"
                  "\u270b\u2728\u274c\u274e\u2753-\u2755\u2757\u2795-\u2797\u27b0\u27bf\u2b1b\u2b1c\u2b50\u2b55")
_EMOJI_TEXT = ("\u00a9\u00ae\u203c\u2049\u2122\u2139\u2194-\u2199\u21a9\u21aa\u2328\u23cf\u23ed-\u23ef\u23f1\u23f2"
               "\u23f8-\u23fa\u24c2\u25aa\u25ab\u25b6\u25c0\u25fb\u25fc\u2600-\u27bf\u2934\u2935\u2b05-\u2b07\u3030\u303d\u3297\u3299")
_MOD = "(?:\ufe0f|[\U0001F3FB-\U0001F3FF])?"
_ONE = f"(?:[\U0001F000-\U0001FAFF{_EMOJI_DEFAULT}]{_MOD}|[{_EMOJI_TEXT}]\ufe0f)"
EMOJI_RE = re.compile(f"[\U0001F1E6-\U0001F1FF]{{2}}|[#*0-9]\ufe0f?\u20e3|{_ONE}(?:\u200d(?:[\U0001F000-\U0001FAFF\u2600-\u27bf]{_MOD}))*")


def emoji_file(seq):
    code = "-".join(f"{ord(c):x}" for c in seq)
    if code in _EMOJI_FILES:
        return code
    short = "-".join(f"{ord(c):x}" for c in seq if c != "\ufe0f")
    return short if short in _EMOJI_FILES else None


def _emoji_tag(seq):
    f = emoji_file(seq)
    return f'<img class="emj" src="/static/emoji/{f}.svg" alt="{seq}" draggable="false">' if f else seq


def emojify(html):
    """Заменяет эмодзи на SVG в уже экранированном HTML (эмодзи не встречаются внутри тегов и атрибутов)."""
    return EMOJI_RE.sub(lambda m: _emoji_tag(m.group(0)), html) if html else html


def strip_emoji(text):
    """Системные тексты (старые уведомления) без эмодзи — в интерфейсе вместо них иконки."""
    if not text:
        return text
    return re.sub(r"\s{2,}", " ", EMOJI_RE.sub("", str(text))).strip()


def emoji_img(seq, cls=""):
    """{{ emo("🔥") }} — одна SVG-эмодзи для цветных мест интерфейса (настроения, праздники)."""
    f = emoji_file(seq)
    if not f:
        return Markup(escape(seq))
    return Markup(f'<img class="emj{(" " + cls) if cls else ""}" src="/static/emoji/{f}.svg" alt="{escape(seq)}" draggable="false">')


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
    raw = str(text).replace("\x00", "")  # нулевой байт служит меткой для `кода` в _format
    for m in URL_RE.finditer(raw):
        out.append(emojify(_tags_and_mentions(raw[pos:m.start()])))
        url = str(escape(m.group(1)))
        label = url if len(url) <= 60 else url[:57] + "…"
        # эмодзи превращаем в картинки только в подписи ссылки, а не внутри href
        out.append(f'<a href="{url}" target="_blank" rel="noopener nofollow ugc" class="rt-link">{emojify(label)}</a>')
        pos = m.end()
    out.append(emojify(_tags_and_mentions(raw[pos:])))
    lines = []
    for line in "".join(out).split("\n"):  # строка, начинающаяся с «> », — цитата
        lines.append(f'<span class="rt-quote">{line[5:]}</span>' if line.startswith("&gt; ") else line)
    return Markup("<br>".join(lines))


_CODE_RE = re.compile(r"`([^`\n]{1,300})`")
_FMT = [
    (re.compile(r"\|\|(.{1,500}?)\|\|"), r'<span class="spoiler" title="Спойлер — нажмите, чтобы открыть">\1</span>'),
    (re.compile(r"\*\*(\S(?:.{0,500}?\S)?)\*\*"), r"<b>\1</b>"),
    (re.compile(r"(?<!\w)__(\S(?:.{0,500}?\S)?)__(?!\w)"), r"<i>\1</i>"),  # не трогаем логины вида a__b__c
    (re.compile(r"~~(\S(?:.{0,500}?\S)?)~~"), r"<s>\1</s>"),
]


def _format(s):
    """Простая разметка: **жирный**, __курсив__, ~~зачёркнутый~~, `код`, ||спойлер||. Текст уже экранирован."""
    codes = []

    def keep(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"
    s = _CODE_RE.sub(keep, s)
    for rx, rep in _FMT:
        s = rx.sub(rep, s)
    return re.sub(r"\x00(\d+)\x00", lambda m: f'<code class="rt-code">{codes[int(m.group(1))]}</code>' if int(m.group(1)) < len(codes) else "", s)


def _tags_and_mentions(chunk):
    s = str(escape(chunk))
    s = _format(s)
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
    from services import i18n
    if i18n.current() == "en":  # в английском две формы; слова уже переведены шаблоном
        return f"{n} {one if abs(n) == 1 else many}"
    return f"{n} {_plural(n, one, few, many)}"


EN_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _timeago_en(dt):
    if not dt:
        return "long ago"
    sec = int((datetime.utcnow() - dt).total_seconds())
    if sec < 0:
        return "scheduled"
    if sec < 45:
        return "just now"
    for size, word in ((3600, None), (86400, "hour"), (86400 * 7, "day")):
        if sec < size:
            n = max(1, sec // 60) if word is None else sec // (3600 if word == "hour" else 86400)
            w = word or "minute"
            return "yesterday" if w == "day" and n == 1 else f"{n} {w}{'' if n == 1 else 's'} ago"
    if dt.year == datetime.utcnow().year:
        return f"{EN_MONTHS[dt.month - 1]} {dt.day}"
    return f"{EN_MONTHS[dt.month - 1]} {dt.day}, {dt.year}"


def timeago(dt):
    from services import i18n
    lang = i18n.current()
    if lang == "en":
        return _timeago_en(dt)
    if lang == "cu":
        return i18n.slavonic(_timeago_ru(dt))
    return _timeago_ru(dt)


def _timeago_ru(dt):
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


BANNED_MSG = "Не опубликовано: в тексте есть нецензурные или запрещённые слова. Уберите их и попробуйте снова."


def banned(text, stop_words=()):
    """Есть ли в тексте мат или стоп-слова (в любом написании). Публичное с такими словами не публикуется."""
    if not text:
        return False
    from services import profanity
    stop_words = [w for w in (stop_words or ()) if w]
    if profanity.has_bad(text, [w for w in stop_words if " " not in w]):
        return True
    low = text.lower()
    return any(w.lower() in low for w in stop_words if " " in w)


def censor(text, stop_words):
    """Заменяет мат и стоп-слова звёздочками — в любом написании (латиница, цифры, похожие буквы)."""
    if not text:
        return text
    from services import profanity
    text = profanity.mask(text, [w for w in (stop_words or ()) if w and " " not in w])
    if not stop_words:
        return text
    for w in stop_words:
        if not w:
            continue
        text = re.sub(re.escape(w), lambda m: m.group(0)[0] + "*" * (len(m.group(0)) - 1), text, flags=re.IGNORECASE)
    return text


# подписи служебных сообщений [[v3:вид:id]] — для ответов, превью чатов, закрепа, поиска и уведомлений
SPECIAL_LABELS = {"poll": "Опрос", "ttt": "Крестики-нолики", "market": "Объявление", "call": "Звонок", "st": "Стикер",
                  "gift": "Подарок", "rps": "Камень, ножницы, бумага", "dice": "Кости", "c4": "Четыре в ряд", "hang": "Виселица"}


def chat_summary(content, empty="Вложение"):
    """Короткий текст сообщения для цитаты/превью: служебная метка превращается в понятное слово."""
    if not content:
        return empty
    if content.startswith("[[v3:") and content.endswith("]]"):
        kind = content[5:-2].split(":", 1)[0]
        return SPECIAL_LABELS.get(kind, "Сообщение")
    return content
