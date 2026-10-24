"""Русский язык для Нувы: стеммер Портера (Snowball), исправление раскладки, повторов букв и опечаток."""
import re

# ---------------------------------------------------------------- стеммер (алгоритм Snowball для русского)
_PERFECTIVE = re.compile(r"((ив|ивши|ившись|ыв|ывши|ывшись)|((?<=[ая])(в|вши|вшись)))$")
_REFLEXIVE = re.compile(r"(с[яь])$")
_ADJECTIVE = re.compile(r"(ее|ие|ые|ое|ими|ыми|ей|ий|ый|ой|ем|им|ым|ом|его|ого|ему|ому|их|ых|ую|юю|ая|яя|ою|ею)$")
_PARTICIPLE = re.compile(r"((ивш|ывш|ующ)|((?<=[ая])(ем|нн|вш|ющ|щ)))$")
_VERB = re.compile(r"((ила|ыла|ена|ейте|уйте|ите|или|ыли|ей|уй|ил|ыл|им|ым|ен|ило|ыло|ено|ят|ует|уют|ит|ыт|ены|ить|ыть|ишь|ую|ю)"
                   r"|((?<=[ая])(ла|на|ете|йте|ли|й|л|ем|н|ло|но|ет|ют|ны|ть|ешь|нно)))$")
_NOUN = re.compile(r"(а|ев|ов|ие|ье|е|иями|ями|ами|еи|ии|и|ией|ей|ой|ий|й|иям|ям|ием|ем|ам|ом|о|у|ах|иях|ях|ы|ь|ию|ью|ю|ия|ья|я)$")
_RV = re.compile(r"^(.*?[аеиоуыэюя])(.*)$")
_DERIV = re.compile(r".*[^аеиоуыэюя]+[аеиоуыэюя].*ость?$")
_cache = {}


def stem(word):
    """«паролем», «пароля», «пароль» → «парол»; «уведомления» → «уведомлен»."""
    w = word.lower().replace("ё", "е")
    if w in _cache:
        return _cache[w]
    m = _RV.match(w)
    if not m or not re.search("[а-я]", w):
        _cache[w] = w
        return w
    pre, rv = m.groups()
    t = _PERFECTIVE.sub("", rv, 1)
    if t == rv:
        rv = _REFLEXIVE.sub("", rv, 1)
        t = _ADJECTIVE.sub("", rv, 1)
        if t != rv:
            rv = _PARTICIPLE.sub("", t, 1)
        else:
            t = _VERB.sub("", rv, 1)
            rv = _NOUN.sub("", rv, 1) if t == rv else t
    else:
        rv = t
    rv = re.sub("и$", "", rv, 1)
    if _DERIV.match(rv):
        rv = re.sub("ость?$", "", rv, 1)
    t = re.sub("ь$", "", rv, 1)
    if t == rv:
        rv = re.sub("(ейше|ейш)$", "", rv, 1)
        rv = re.sub("нн$", "н", rv, 1)
    else:
        rv = t
    res = pre + rv
    if len(_cache) < 20000:
        _cache[w] = res
    return res


# ---------------------------------------------------------------- подготовка текста
_LAYOUT = dict(zip("qwertyuiop[]asdfghjkl;'zxcvbnm,.`/?&", "йцукенгшщзхъфывапролджэячсмитьбюё.,?"))


def _conv_word(w):
    out = []
    for ch in w:
        r = _LAYOUT.get(ch.lower())
        out.append((r.upper() if ch != ch.lower() else r) if r else ch)
    return "".join(out)


def from_layout(text):
    """«rfr cvtybnm gfhjkm» → «как сменить пароль» (набрано в английской раскладке: «,» и «.» — это «б» и «ю»,
    а русские запятая и точка выходят как «?» и «/»)."""
    return _conv_word(text)


def looks_like_wrong_layout(text, known):
    """Латиница без кириллицы, а после перевода раскладки слова узнаются — значит, забыли переключить язык."""
    if re.search("[а-яё]", text, re.I) or not re.search("[a-z]", text, re.I):
        return False
    conv = words(from_layout(text))
    if not conv:
        return False
    ok = sum(1 for w in conv if len(w) > 1 and (w in known or stem(w) in known))
    return ok >= max(1, (len(conv) + 1) // 2)


def squeeze(text):
    """«приииивет!!!» → «привет!»: убираем растянутые буквы (3 и более подряд)."""
    return re.sub(r"(.)\1{2,}", r"\1", text)


def words(text):
    return re.findall(r"[a-zа-я0-9]+", text.lower().replace("ё", "е"))


# ---------------------------------------------------------------- опечатки
def distance(a, b, limit=2):
    """Расстояние Дамерау–Левенштейна (перестановка соседних букв — одна ошибка) с ранним выходом."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2, prev = None, list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        best = cur[0]
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if prev2 is not None and i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
            best = min(best, cur[j])
        if best > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[-1]


def closest(stem_, vocab):
    """Ближайшая основа из словаря справки: одна ошибка для коротких слов, две — для длинных."""
    if len(stem_) < 4 or stem_ in vocab:
        return stem_
    limit = 1 if len(stem_) < 7 else 2
    best, best_d = None, limit + 1
    for v in vocab:
        if abs(len(v) - len(stem_)) > limit or v[0] != stem_[0] and len(stem_) < 7:
            continue
        d = distance(stem_, v, limit)
        if d < best_d or (d == best_d and best and vocab[v] > vocab[best]):
            best, best_d = v, d
    return best if best is not None and best_d <= limit else stem_
