"""Собственная модель модерации Nuvora.

Лёгкий классификатор токсичности русского текста: хэшированные символьные n-граммы и слова
+ логистическая регрессия. Модель обучается скриптом tools/train_moderation.py и хранится
в ml/toxicity_ru.bin (несколько сотен КБ). Для работы не нужны numpy, torch или видеокарта:
проверка одного поста занимает доли миллисекунды на чистом Python.

Помимо модели здесь же простые эвристики спама (ссылки, телефоны, «заработок», капс)."""
import math
import os
import re
import struct
import zlib

import config

MODEL_PATH = os.path.join(config.BASE_DIR, "ml", "toxicity_ru.bin")
MAGIC = b"NVTX1"

# --- Нормализация: снимаем маскировку вида «xуй», «х.у.й», «бл*ть», «дуууурак», «3апрет» -----------------
_LOOKALIKE = str.maketrans({
    "a": "а", "b": "в", "c": "с", "e": "е", "h": "н", "k": "к", "m": "м", "o": "о", "p": "р", "t": "т",
    "x": "х", "y": "у", "u": "и", "r": "г", "n": "п", "0": "о", "3": "з", "4": "ч", "6": "б", "@": "а",
    "$": "с", "ё": "е", "€": "е",
})
_INNER_SEP = re.compile(r"(?<=[^\W\d_])[.\-_'`\"|]+(?=[^\W\d_])")
_SPACED = re.compile(r"\b(?:[^\W\d_][\s.\-_*]+){2,}[^\W\d_]\b")
_REPEAT = re.compile(r"(.)\1+")
_WORD = re.compile(r"[^\W_]+(?:\*+[^\W_]*)*|\*+[^\W_]+", re.UNICODE)


def normalize(text: str) -> str:
    t = (text or "").lower()
    t = re.sub(r"https?://\S+|www\.\S+", " ссылка ", t)
    t = _SPACED.sub(lambda m: re.sub(r"[\s.\-_*]+", "", m.group(0)), t)
    t = _INNER_SEP.sub("", t)
    t = t.translate(_LOOKALIKE)
    return _REPEAT.sub(r"\1", t)


def features(text: str):
    """Набор признаков текста (строки). Одинаково используется при обучении и при проверке."""
    words = _WORD.findall(normalize(text))[:400]
    feats = set()
    for i, w in enumerate(words):
        feats.add("w:" + w)
        if i:
            feats.add("b:" + words[i - 1] + " " + w)
        p = "<" + w + ">"
        for n in (3, 4, 5):
            for j in range(len(p) - n + 1):
                feats.add("c:" + p[j:j + n])
    return feats


def fhash(f: str) -> int:
    return zlib.crc32(f.encode("utf-8"))


# --- Загрузка весов ---------------------------------------------------------------------------------------
_model = None


def save_model(path, bias, weights: dict):
    """weights: {hash: float}. Веса квантуются в int8 — файл получается крошечным."""
    items = sorted(weights.items())
    scale = max((abs(w) for _, w in items), default=1.0) / 127 or 1.0
    with open(path, "wb") as f:
        f.write(MAGIC + struct.pack("<ffI", bias, scale, len(items)))
        f.write(struct.pack(f"<{len(items)}I", *[h for h, _ in items]))
        f.write(struct.pack(f"<{len(items)}b", *[max(-127, min(127, round(w / scale))) for _, w in items]))


def load_model(path=MODEL_PATH):
    with open(path, "rb") as f:
        data = f.read()
    if not data.startswith(MAGIC):
        raise ValueError("неизвестный формат модели")
    off = len(MAGIC)
    bias, scale, n = struct.unpack_from("<ffI", data, off)
    off += 12
    hashes = struct.unpack_from(f"<{n}I", data, off)
    qs = struct.unpack_from(f"<{n}b", data, off + 4 * n)
    return bias, {h: q * scale for h, q in zip(hashes, qs)}


def _get_model():
    global _model
    if _model is None:
        try:
            _model = load_model()
        except (OSError, ValueError) as e:
            print(f"[moderation] модель не загружена: {e}")
            _model = (0.0, {})
    return _model


def toxicity(text: str) -> float:
    """Вероятность (0..1), что текст содержит оскорбления, мат или агрессию."""
    bias, w = _get_model()
    if not w or not text or not text.strip():
        return 0.0
    hs = [fhash(f) for f in features(text)]
    if not hs:
        return 0.0
    z = bias + sum(w.get(h, 0.0) for h in hs) / math.sqrt(len(hs))
    return 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))


# --- Спам ---------------------------------------------------------------------------------------------------
_SPAM_WORDS = re.compile(r"заработ|доход от|пассивн\w* доход|казино|ставк\w* на спорт|букмекер|крипт\w*|инвестиц|"
                         r"пиши в (?:лс|личку|директ)|переходи по ссылке|только сегодня|скидк\w* \d+|бесплатн\w* подписчик|"
                         r"накрутк|раскрутк|промокод на|выигрыш|розыгрыш iphone|t\.me/|wa\.me/", re.I)
_PHONE = re.compile(r"(?:\+7|8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}")
_LINK = re.compile(r"https?://|www\.|\b\w+\.(?:ru|com|net|org|io|me|xyz|top|site|online|shop)\b", re.I)


def spam(text: str) -> float:
    if not text:
        return 0.0
    s = 0.0
    s += 0.35 * min(2, len(_SPAM_WORDS.findall(text)))
    s += 0.25 * min(2, len(_LINK.findall(text)))
    s += 0.3 if _PHONE.search(text) else 0
    letters = [c for c in text if c.isalpha()]
    if len(letters) > 20 and sum(c.isupper() for c in letters) / len(letters) > 0.7:
        s += 0.2
    if re.search(r"(.)\1{9,}", text):
        s += 0.15
    return min(1.0, s)


LABELS = {"toxic": "оскорбления / мат", "spam": "похоже на спам"}


def check(text: str) -> dict:
    """Итоговая проверка: {'score': 0..1, 'label': 'toxic'|'spam'|'', 'toxic': .., 'spam': ..}."""
    tox, sp = toxicity(text), spam(text)
    label, score = ("toxic", tox) if tox >= sp else ("spam", sp)
    return {"score": round(score, 3), "label": label if score > 0 else "", "toxic": round(tox, 3), "spam": round(sp, 3)}


def review(db, kind, obj, author, text):
    """Проверяет новый пост/комментарий. Подозрительное отправляет модераторам, явное — скрывает до проверки.
    Ничего не удаляет сам: финальное решение всегда за человеком."""
    import models
    from services import social
    if not config.MODERATION_ENABLED or not text or social.can_mod(author):
        return None
    r = check(text)
    if r["score"] < config.MOD_FLAG_THRESHOLD:
        return None
    hold = kind == "post" and r["score"] >= config.MOD_HOLD_THRESHOLD
    if hold:
        obj.is_published = False
    flag = models.ModerationFlag(kind=kind, object_id=obj.id, post_id=obj.id if kind == "post" else obj.post_id, user_id=author.id,
                                 label=r["label"], score=r["score"], snippet=text[:500], held=hold)
    db.add(flag)
    if hold:
        social.notify(db, author.id, "moderation", None, None,
                      text="Ваш пост отправлен на проверку модераторам и появится в ленте после одобрения.")
    return flag
