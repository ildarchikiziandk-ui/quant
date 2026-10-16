"""Фильтр мата для переписки, постов и комментариев.

Ловит русский мат, написанный кириллицей, латиницей («blyat», «pizdec», «xyi»), с цифрами и похожими
символами («cyka», «п1зд@»), с разделителями («х.у.й») и растянутыми буквами («сууука»).
Найденное слово заменяется звёздочками, первая буква остаётся.
"""
import re

# латиница → кириллица «по звучанию» (сначала длинные сочетания)
_PHON = [("shch", "щ"), ("sch", "щ"), ("yo", "ё"), ("jo", "ё"), ("yu", "ю"), ("ju", "ю"), ("ya", "я"), ("ja", "я"),
         ("zh", "ж"), ("kh", "х"), ("ch", "ч"), ("sh", "ш"), ("ts", "ц"), ("ye", "е")]
_PHON1 = {"a": "а", "b": "б", "v": "в", "w": "в", "g": "г", "d": "д", "e": "е", "z": "з", "i": "и", "j": "й", "k": "к",
          "l": "л", "m": "м", "n": "н", "o": "о", "p": "п", "r": "р", "s": "с", "t": "т", "u": "у", "f": "ф", "h": "х",
          "x": "х", "c": "к", "q": "к", "y": "ы"}
# латиница и цифры → кириллица «по виду» (xyu → хую, cyka → сука)
_LOOK = str.maketrans({"a": "а", "b": "б", "c": "с", "e": "е", "k": "к", "m": "м", "h": "н", "o": "о", "p": "р", "t": "т",
                       "x": "х", "y": "у", "u": "и", "n": "п", "r": "г", "3": "з", "0": "о", "6": "б", "4": "ч", "@": "а",
                       "1": "и", "$": "с", "|": "и", "ё": "е", "i": "и"})
_DIGITS = str.maketrans({"3": "з", "0": "о", "6": "б", "4": "ч", "@": "а", "1": "и", "$": "с", "ё": "е"})
_VOWELS = set("аеёиоуыэюя")

_PREFIX = r"(?:за|у|вы|до|раз|рас|от|по|на|при|про|съ|с|об|под|недо|пере|из|вз)?"
PATTERNS = [
    r"^(?:на|по|ни|от|до|за|о|а)?ху[йяеёию]", r"^ху[йи]", r"пизд", r"^(?:за|от|вы|рас|у|пере)?пизд",
    r"^бля(?!х)", r"бляд", r"^бл[яа]ть", r"^" + _PREFIX + r"е[б](?:а[лнтш]|у[тлч]?|и[сщл]|ан|ал|ыв|ош|ну|ёт|ет|ла|ли|ло)",
    r"^" + _PREFIX + r"еба", r"^" + _PREFIX + r"еб[уи]", r"долбо[её]б", r"^мудак", r"^мудил", r"^мудо",
    r"пид[оа]р", r"пидр", r"^сук[аиуое]", r"^сучк", r"^сучар", r"залуп", r"^гандон", r"^гондон", r"^шлюх", r"^дроч",
    r"^манда", r"^уеб", r"^ебл[оа]", r"^ебуч",
]
_RX = [re.compile(p) for p in PATTERNS]
_TOKEN = re.compile(r"[0-9A-Za-zА-Яа-яЁё@$|]+(?:[.\-_*]+[0-9A-Za-zА-Яа-яЁё@$|]+)*")
_REPEAT = re.compile(r"(.)\1{2,}")


def _phonetic(w):
    out, i = [], 0
    while i < len(w):
        for a, b in _PHON:
            if w.startswith(a, i):
                out.append(b)
                i += len(a)
                break
        else:
            ch = w[i]
            if ch == "y" and out and out[-1] in _VOWELS:
                out.append("й")  # huy → хуй
            else:
                out.append(_PHON1.get(ch, ch))
            i += 1
    return "".join(out)


def variants(token):
    """Возможные «кириллические прочтения» слова."""
    w = re.sub(r"[.\-_*]+", "", token.lower())
    w = _REPEAT.sub(r"\1\1", w)
    out = {w.translate(_DIGITS)}
    if re.search(r"[a-z0-9@$|]", w):
        out.add(w.translate(_LOOK))
        out.add(_phonetic(w.translate(_DIGITS)))
    out = {v.replace("ё", "е") for v in out}
    return out | {re.sub(r"(.)\1+", r"\1", v) for v in out}  # «сууука», «ххуй»


def is_bad(token, extra=()):
    for v in variants(token):
        if any(r.search(v) for r in _RX):
            return True
        if any(x and x in v for x in extra):
            return True
    return False


def normalize_words(words):
    """Стоп-слова администратора в том же виде, что и проверяемые слова (кириллица, без «ё»)."""
    out = []
    for w in words or ():
        w = (w or "").strip().lower()
        if len(w) >= 3:
            out.extend(sorted(variants(w), key=len)[:1])
    return tuple(out)


def mask(text, extra=()):
    """Заменяет мат и стоп-слова звёздочками в любом написании."""
    if not text:
        return text
    extra = normalize_words(extra)

    def rep(m):
        t = m.group(0)
        if len(t) < 3 or not is_bad(t, extra):
            return t
        return t[0] + "*" * (len(t) - 1)
    return _TOKEN.sub(rep, text)


def has_bad(text, extra=()):
    extra = normalize_words(extra)
    return any(is_bad(m.group(0), extra) for m in _TOKEN.finditer(text or "") if len(m.group(0)) >= 3)


def to_cyrillic(text):
    """Перевод латинских слов в кириллицу — для модели модерации, которая обучена на русском тексте."""
    return _TOKEN.sub(lambda m: _phonetic(m.group(0).lower()) if re.search(r"[a-z]", m.group(0).lower()) else m.group(0), text or "")
