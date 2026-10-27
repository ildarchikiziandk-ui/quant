"""Языки интерфейса: русский (основной), английский и древнеславянский.

Русские строки в коде не размечаются. Перевод делается автоматически по словарю:
- шаблоны переводятся один раз при загрузке (свой экземпляр Jinja на каждый язык): только текст, написанный
  в самом шаблоне, — посты, сообщения и имена людей приходят через {{ … }} и не трогаются;
- строки из Python, выводимые в шаблон через {{ … }}, переводятся, если целиком совпадают с фразой словаря
  (подписи настроек, названия разделов) или с шаблоном f-строки («Можно создать до {} альбомов»);
- JS-файлы отдаются переведёнными по адресу /i18n/<язык>/static/…; ответы JSON — поля error и message.

Словарь английского — i18n/en.json (ключ — русская фраза). Древнеславянский строится из русского правилами
дореформенной орфографии и словарём старинных слов (i18n/cu.json), поэтому переводится всё и сразу.
Ключи собирает tools/i18n_extract.py — тем же разбором, что и при переводе, поэтому они всегда совпадают.
"""
import json
import os
import re
from contextvars import ContextVar
from functools import lru_cache

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "i18n")
LANGS = {"ru": "Русский", "en": "English", "cu": "Древнеславянскій"}
HTML_LANG = {"ru": "ru", "en": "en", "cu": "cu"}
COOKIE = "lang"
LANG: ContextVar[str] = ContextVar("lang", default="ru")

CYR = re.compile(r"[А-Яа-яЁё]")
# остаются на русском: юридические документы (действуют на русском языке) и админка (только для владельца)
SKIP_TEMPLATES = ("terms.html", "privacy.html", "consent.html", "refund.html", "admin", "packs/v3/admin", "packs/v3/nuva_admin")


def skip_template(name):
    return name.startswith(SKIP_TEMPLATES)
PH = re.compile(r"\x01e?\d+\x02")  # e — вставка ${…} в шаблонной строке JS  # место вставки {{ … }} внутри текста шаблона


def current():
    return LANG.get()


def pick(cookie_value):
    return cookie_value if cookie_value in LANGS else "ru"


# ---------------------------------------------------------------- словари
@lru_cache(maxsize=None)
def catalog(lang):
    path = os.path.join(BASE, f"{lang}.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


@lru_cache(maxsize=None)
def ui_keys():
    """Все фразы интерфейса (i18n/keys.json, собирает tools/i18n_extract.py) — чтобы отличать их от текстов людей."""
    try:
        with open(os.path.join(BASE, "keys.json"), encoding="utf-8") as f:
            return frozenset(json.load(f)) | frozenset(catalog("en"))
    except (OSError, ValueError):
        return frozenset(catalog("en"))


@lru_cache(maxsize=None)
def _patterns():
    """Фразы с {} — шаблоны f-строк из Python («{} подписчиков»): regex по русскому ключу."""
    out = []
    for k in sorted(ui_keys(), key=len, reverse=True):  # длинные шаблоны точнее — проверяем первыми
        if "{}" in k and len(CYR.findall(k.replace("{}", ""))) >= 4:
            parts = k.split("{}")
            rx = re.compile("^" + "(.+?)".join(re.escape(p) for p in parts) + "$", re.S)
            out.append((max(parts, key=len), rx, k))  # самый длинный кусок — быстрая проверка до regex
    return out


def lookup(core, lang):
    """Перевод одной фразы без пробелов по краям; None — перевода нет."""
    if lang == "cu":
        return slavonic(core)
    return catalog(lang).get(core)


def phrase(s, lang=None):
    """Перевести строку целиком (с сохранением пробелов по краям). Для строк из Python."""
    lang = lang or current()
    if lang == "ru" or not s or not CYR.search(s):
        return s
    core = s.strip()
    t = None
    if lang == "cu":
        if core in ui_keys():  # только фразы интерфейса, а не тексты людей
            t = slavonic(core)
    else:
        t = catalog(lang).get(core)
    if t is None and len(core) < 300:
        t = _dynamic(core, lang)
    if t is None and core.endswith(")") and " (" in core:  # «Москва (UTC+3)»: переводим название перед скобкой
        head, _, tail = core.rpartition(" (")
        h = _exact(head, lang)
        t = None if h == head else f"{h} ({tail}"
    if t is None:
        return s
    return s[:len(s) - len(s.lstrip())] + t + s[len(s.rstrip()):]


def _exact(s, lang):
    """Вставка в шаблон фразы: переводим, только если это тоже фраза интерфейса (название достижения, подарка)."""
    core = s.strip()
    if not CYR.search(core):
        return s
    if lang == "cu":
        return slavonic(core) if core in ui_keys() else s
    return catalog(lang).get(core, s)


def _dynamic(core, lang):
    for needle, rx, key in _patterns():
        if needle not in core:
            continue
        m = rx.match(core)
        if not m:
            continue
        tpl = slavonic(key) if lang == "cu" else catalog(lang).get(key)
        if not tpl:
            return None
        for a in m.groups():
            tpl = tpl.replace("{}", _exact(a, lang), 1)
        return tpl
    return None


# ---------------------------------------------------------------- разбор текста, HTML и JS
def _ws_wrap(s, fn):
    core = s.strip()
    if not core or not CYR.search(core):
        return s
    t = fn(core)
    if t is None:
        return s
    return s[:len(s) - len(s.lstrip())] + t + s[len(s.rstrip()):]


def text(s, fn, ph_ok=None):
    """Обычный текст: куски между вставками {{ … }} переводятся по отдельности."""
    if ph_ok is not None:
        ph_ok.update(PH.findall(s))  # вставки в обычном тексте страницы можно переводить (подписи из Python)
    if not CYR.search(s):
        return s
    pieces = PH.split(s)
    marks = PH.findall(s)
    out = []
    for i, p in enumerate(pieces):
        out.append(_ws_wrap(p, fn))
        if i < len(marks):
            out.append(marks[i])
    return "".join(out)


_TAG = r"""<[a-zA-Z/!](?:[^>"']|"[^"]*"|'[^']*')*>"""  # кавычки внутри атрибутов (onclick="…=>…") не обрывают тег
_TOKENS = re.compile(r"(<script\b[^>]*>)(.*?)(</script\s*>)|(<textarea\b[^>]*>)(.*?</textarea\s*>)|<style\b.*?</style\s*>|<!--.*?-->|" + _TAG, re.S | re.I)
_ATTR = re.compile(r"""([\w:.\-@]+)(\s*=\s*)("([^"]*)"|'([^']*)')""")


_NO_TR_ATTR = ("href", "src", "action", "name", "id", "class", "style", "for", "pattern", "type", "method", "accept", "autocomplete",
               "inputmode", "rel", "target", "lang", "hreflang", "srcset", "sizes", "width", "height", "min", "max", "step", "maxlength")
_TR_DATA = ("data-confirm", "data-title", "data-tip", "data-label", "data-placeholder", "data-hint", "data-text", "data-empty")


def _tag(tag, fn, ph_ok=None):
    if not CYR.search(tag) and not (ph_ok is not None and "\x01" in tag):
        return tag
    is_btn = re.match(r"<input\b", tag, re.I) and re.search(r"""type\s*=\s*["']?(submit|button)""", tag, re.I)

    def attr(m):
        name, eq, whole, dq, sq = m.groups()
        val = dq if dq is not None else sq
        low = name.lower()
        if val is None or low in _NO_TR_ATTR or (low == "value" and not is_btn) or low.startswith("data-") and low not in _TR_DATA:
            return m.group(0)  # адреса, классы, значения полей формы — не надписи
        if low.startswith("on"):
            if not CYR.search(val):
                return m.group(0)
            new = js(val, fn, quote='"' if dq is not None else "'")
        else:
            new = text(val, fn, ph_ok)
            if dq is not None:
                new = new.replace('"', "&quot;")
            else:
                new = new.replace("'", "&#39;")
        q = '"' if dq is not None else "'"
        return f"{name}{eq}{q}{new}{q}"

    return _ATTR.sub(attr, tag)


def html(src, fn, ph_ok=None):
    out, pos = [], 0
    for m in _TOKENS.finditer(src):
        out.append(text(src[pos:m.start()], fn, ph_ok))
        if m.group(1) is not None:
            head = m.group(1)
            body = m.group(2)
            if re.search(r"""type\s*=\s*["']?(application/(ld\+)?json|speculationrules|text/template)""", head, re.I):
                out.append(m.group(0))
            else:
                out.append(_tag(head, fn) + js(body, fn) + m.group(3))
        elif m.group(4) is not None:
            out.append(_tag(m.group(4), fn, ph_ok) + m.group(5))  # у поля ввода переводим подсказку, а не содержимое
        elif m.group(0)[:6].lower() in ("<style", "<!--"):
            out.append(m.group(0))  # стили, комментарии и содержимое полей ввода не трогаем
        else:
            out.append(_tag(m.group(0), fn, ph_ok))
        pos = m.end()
    out.append(text(src[pos:], fn, ph_ok))
    return "".join(out)


_REGEX_BEFORE = set("(,=:[!&|?{};+-*%<>~^") | {""}


def _string_content(s, fn, q):
    """Содержимое строкового литерала JS (без кавычек). Экранируем только сам перевод — исходный текст уже корректен."""
    if not CYR.search(s):
        return s

    def safe(core):
        t = fn(core)
        if t is None:
            return None
        t = t.replace("\\", "\\\\").replace("\n", "\\n")
        return t.replace("`", "\\`").replace("${", "\\${") if q == "`" else t.replace(q, "\\" + q)
    return html(s, safe) if re.search(r"<[a-zA-Z/]", s) else text(s, safe)


def js(src, fn, quote=None):
    """JS-код: переводим только строковые литералы с кириллицей. quote — JS внутри HTML-атрибута с этой кавычкой."""
    if not CYR.search(src):
        return src
    return _js(src, 0, fn, quote, False)[0]


def _js(src, i, fn, quote, nested):
    """Разбор с позиции i. nested — внутри ${…}: останавливаемся на парной закрывающей скобке."""
    out, n, depth, last_sig = [], len(src), 0, ""
    while i < n:
        c = src[i]
        if c in "\"'":
            j = i + 1
            while j < n and src[j] != c and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            body = src[i + 1:j]
            # строку сравнивают ('Да' === x, case 'Да':) — это ключ, а не надпись
            compared = re.search(r"([=!]==?|\bcase)\s*$", "".join(out[-6:])) or re.match(r"\s*[=!]==?", src[j + 1:j + 6])
            loc = getattr(fn, "locale", None)
            if loc and body in loc:  # toLocaleDateString('ru-RU') → даты на языке интерфейса
                new = loc[body]
            else:
                new = body if compared else _string_content(body, fn, c)
            if quote and quote != c:  # JS внутри атрибута: кавычку атрибута внутри строки нельзя пускать
                new = new.replace(quote, "&quot;" if quote == '"' else "&#39;")
            out.append(c + new + (src[j] if j < n else ""))
            i, last_sig = j + 1, c
        elif c == "`":
            # вся строка целиком, ${…} — как вставки: так HTML внутри неё разбирается правильно
            j, chunk, res, exprs = i + 1, i + 1, [], []
            while j < n and src[j] != "`":
                if src[j] == "\\":
                    j += 2
                    continue
                if src.startswith("${", j):
                    res.append(src[chunk:j])
                    inner, j = _js(src, j + 2, fn, quote, True)
                    res.append(f"\x01e{len(exprs)}\x02")
                    exprs.append(inner)
                    chunk = j
                    continue
                j += 1
            res.append(src[chunk:j])
            body = _string_content("".join(res), fn, "`")
            body = re.sub(r"\x01e(\d+)\x02", lambda m: "${" + exprs[int(m.group(1))] + "}", body)
            out.append("`" + body + "`")
            i, last_sig = j + 1, "`"
        elif src.startswith("//", i) and quote is None:
            j = src.find("\n", i)
            j = n if j < 0 else j
            out.append(src[i:j])
            i = j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(src[i:j])
            i = j
        elif c == "/" and (last_sig in _REGEX_BEFORE or re.search(r"(return|typeof|case|in|of)\s*$", src[max(0, i - 10):i])):
            j, cls = i + 1, False  # регулярное выражение — копируем как есть
            while j < n and src[j] != "\n":
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "[":
                    cls = True
                elif src[j] == "]":
                    cls = False
                elif src[j] == "/" and not cls:
                    break
                j += 1
            out.append(src[i:j + 1])
            i, last_sig = j + 1, "x"
        else:
            if nested and c == "{":
                depth += 1
            elif nested and c == "}":
                if depth == 0:
                    return "".join(out), i + 1  # конец ${…}
                depth -= 1
            out.append(c)
            if not c.isspace():
                last_sig = c if not (c.isalnum() or c in "_$)]") else "x"
            i += 1
    return "".join(out), i


# ---------------------------------------------------------------- шаблоны Jinja
_JINJA = re.compile(r"({{.*?}}|{%.*?%}|{#.*?#})", re.S)
_JSTR = re.compile(r"""(?P<pre>(==|!=|\bin|\bnot in|startswith\(|endswith\(|\[)\s*)?(?P<q>["'])(?P<s>(?:\\.|(?!(?P=q)).)*)(?P=q)(?P<post>\s*(==|!=|\bin\b|\]))?""", re.S)


def _jinja_strings(tok, fn):
    if tok.startswith("{#") or not CYR.search(tok):
        return tok

    def rep(m):
        s = m.group("s")
        if not CYR.search(s) or m.group("pre") or m.group("post"):
            return m.group(0)  # строку сравнивают или ищут по ней ключ — не трогаем
        q = m.group("q")
        new = html(s, fn) if re.search(r"<[a-zA-Z/]", s) else _ws_wrap(s, fn)
        new = new.replace("\\", "\\\\").replace(q, "\\" + q)
        return q + new + q
    return _JSTR.sub(rep, tok)


_OUT = re.compile(r"^{{(-?)(.*?)(-?)}}$", re.S)


def template(src, fn, notr=None):
    """Перевести исходник шаблона. notr — имя фильтра, которым помечаются вставки {{ … }} в полях форм, ссылках
    и скриптах: их значения нельзя переводить (иначе город «Москва» из профиля уйдёт в форму как «Moscow»)."""
    keep, ok = [], set()

    def stash(m):
        keep.append(_jinja_strings(m.group(0), fn))
        return f"\x01{len(keep) - 1}\x02"
    body = _JINJA.sub(stash, src)
    body = html(body, fn, ok)

    def restore(m):
        tok = keep[int(m.group(1))]
        if notr and m.group(0) not in ok:
            o = _OUT.match(tok)
            if o:
                tok = "{{" + o.group(1) + " (" + o.group(2).strip() + ")|" + notr + " " + o.group(3) + "}}"
        return tok
    return re.sub(r"\x01(\d+)\x02", restore, body)


# ---------------------------------------------------------------- древнеславянский
_SLAV_WORDS = None


def _slav_words():
    global _SLAV_WORDS
    if _SLAV_WORDS is None:
        _SLAV_WORDS = {k.lower(): v for k, v in catalog("cu").items()}
    return _SLAV_WORDS


CONS = "бвгджзклмнпрстфхцчшщ"
VOW = "аеёиоуыэюяй"
# корни с буквой «ять» (ѣ) — самые частые в интерфейсе
YAT = ["нет", "где", "здесь", "мест", "свет", "цвет", "лет", "бел", "дел", "дет", "век", "человек", "вер", "мер", "смех", "след",
       "обед", "сед", "снег", "лес", "хлеб", "бед", "пес", "тень", "тело", "цел", "грех", "вет", "сдел", "успе", "поме", "отве", "сове",
       "приве", "изве", "пове", "отме", "заме", "наде", "посе", "оде", "уве", "раздел", "звезд", "вез", "плен", "стен", "колен", "бег"]
_YAT_SKIP = ("телефон", "телеграм", "телевиз", "версия", "версии", "вершин", "дета", "лест", "мерч", "сервер", "песн")
_YAT_RX = re.compile(r"\b(без|не|по|при|про|за|на|от|о|об|у|до|раз|с|из|вы|под|пере)?(" + "|".join(sorted({y for y in YAT if len(y) >= 3}, key=len, reverse=True)) + r")", re.I)
_NO_TI = {"путь", "мать", "печать", "тетрадь", "знать", "рать", "кровать", "благодать", "гладь", "есть", "суть", "часть", "власть", "радость", "новость", "версть"}


def _case(src, new):
    if src.isupper() and len(src) > 1:
        return new.upper()
    if src[:1].isupper():
        return new[:1].upper() + new[1:]
    return new


def _slav_word(w):
    low = w.lower().replace("ё", "е")
    words = _slav_words()
    if low in words:
        return _case(w, words[low])
    out = low
    # инфинитив: сохранить → сохранити
    if re.search(r"[аяиеуыо]ть$", out) and out not in _NO_TI and not out.endswith("ость"):
        out = out[:-2] + "ти"
    elif re.search(r"[аяиеуыо]ться$", out):
        out = out[:-4] + "тися"
    # ять в известных корнях (только в начале слова или после приставки)
    m = _YAT_RX.match(out)
    if m and len(out) >= 3 and not out.startswith(_YAT_SKIP):
        root = m.group(2)
        k = root.find("е")
        if k >= 0:
            s = m.start(2) + k
            out = out[:s] + "ѣ" + out[s + 1:]
    # і перед гласной: Россия → Россія
    out = re.sub(r"и(?=[аеёиоуыэюяй])", "і", out)
    # ъ на конце после согласной
    if out[-1:] in CONS:
        out += "ъ"
    return _case(w, out)


@lru_cache(maxsize=20000)
def slavonic(s):
    """Русская фраза интерфейса → «древнеславянский»: старинные слова и дореформенное письмо (ѣ, і, ъ, -ти)."""
    if not s:
        return s
    words = _slav_words()
    low = s.lower().replace("ё", "е")
    if low in words:  # целая фраза из словаря
        return _case(s, words[low])
    return re.sub(r"[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)?", lambda m: "-".join(_slav_word(p) for p in m.group(0).split("-")), s)


# ---------------------------------------------------------------- для приложения
LOCALES = {"en": {"ru-RU": "en-US", "ru": "en"}}


def translator(lang):
    def fn(core):
        return lookup(core, lang)
    fn.locale = LOCALES.get(lang)
    return fn


@lru_cache(maxsize=64)
def js_file(path, lang, mtime):
    with open(path, encoding="utf-8") as f:
        return js(f.read(), translator(lang))


def json_fields(data, lang):
    """Ответы JSON: переводим служебные тексты (ошибки, подсказки), а не данные."""
    if isinstance(data, dict):
        for k in ("error", "message", "toast", "hint", "reason", "warning"):
            v = data.get(k)
            if isinstance(v, str):
                data[k] = phrase(v, lang)
        if isinstance(data.get("warnings"), list):
            data["warnings"] = [phrase(x, lang) if isinstance(x, str) else x for x in data["warnings"]]
    return data
