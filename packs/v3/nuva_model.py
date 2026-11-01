"""Своя нейросеть Нувы: открытая модель (Qwen2.5-Instruct, Apache 2.0) на нашем же сервере через llama.cpp.

Ставится скриптом deploy/set-local-ai.sh (служба nuvora-ai, только 127.0.0.1), адрес — LOCAL_AI_URL в .env.
Вопросы никуда не уходят с сервера: никаких внешних нейросетей и ключей. Если модель не запущена или не ответила —
Нува отвечает по справке, как раньше.
"""
import json
import re
import urllib.request

import config

SYSTEM = """Ты — Нува, дружелюбная помощница социальной сети Nuvora (nvra.ru). Отвечай по-русски, тепло и по делу,
коротко: 1–5 предложений или короткий список, если не просят длиннее. Можешь болтать, шутить, советовать,
придумывать подписи к фото, поздравления, идеи постов, помогать с текстами и учёбой.
Про функции Nuvora опирайся только на справку ниже; если в справке ответа нет — честно скажи, что не уверена,
и предложи написать в поддержку (раздел «Поддержка»). Не выдумывай кнопки и разделы.
Внутренняя валюта Nuvora называется «Искры». Подписка — Nuvora+.
Не проси и не повторяй пароли, коды и личные данные. Не помогай с опасным, незаконным и травлей.
Пользователя зовут: {name}."""


def enabled():
    return bool(config.LOCAL_AI_URL)


def _post_local(messages, max_tokens, temperature):
    """Своя модель (llama.cpp server, OpenAI-совместимый API) на этом же сервере: без ключей и без интернета.
    На обычном процессоре она думает небыстро, поэтому ответы короче и ждём дольше."""
    body = json.dumps({"model": config.LOCAL_AI_MODEL, "messages": messages, "temperature": temperature,
                       "max_tokens": min(max_tokens, 400)}).encode()
    req = urllib.request.Request(config.LOCAL_AI_URL + "/chat/completions", method="POST", data=body,
                                 headers={"Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        j = json.load(r)
    return (j["choices"][0]["message"]["content"] or "").strip()


def _post(messages, max_tokens=700, temperature=0.7):
    """Запрос к нейросети. Вынесено отдельно, чтобы в тестах подменить."""
    return _post_local(messages, max_tokens, temperature)


# язык интерфейса: на английском Нува отвечает по-английски, на древнеславянском — стилизацией под старинную речь
LANG_NOTE = {
    "en": "\nВАЖНО: интерфейс у пользователя на английском — отвечай по-английски (English), названия разделов тоже по-английски.",
    "cu": "\nВАЖНО: пользователь выбрал «древнеславянский» язык интерфейса — отвечай шутливо-торжественной старинной речью "
          "(аз, еси, сие, зело, дабы, лепо), но так, чтобы смысл был понятен современному читателю.",
}


def chat(question, history, user, kb_hits):
    """Ответ нейросети или None (тогда Нува отвечает по справке)."""
    if not enabled():
        return None
    ref = "\n\n".join(f"### {e['title']}\n{e['text']}" for _, e in kb_hits[:4]) or "(подходящих статей не нашлось)"
    from services import i18n
    lang_note = LANG_NOTE.get(i18n.current(), "")
    msgs = [{"role": "system", "content": SYSTEM.format(name=(user.name or user.username) if user else "гость") + lang_note
             + "\n\nСправка Nuvora:\n" + ref}]
    for h in (history or [])[-8:]:
        role = "assistant" if h.get("role") == "bot" else "user"
        text = str(h.get("content") or "")[:1500]
        if text:
            msgs.append({"role": role, "content": text})
    msgs.append({"role": "user", "content": question[:2000]})
    try:
        out = _post(msgs)
        if FOREIGN.search(out):  # маленькая модель иногда вставляет китайские иероглифы — спрашиваем ещё раз, спокойнее
            out = _post(msgs, temperature=0.2)
    except Exception as e:  # noqa: BLE001 — модель не запущена или занята: молча возвращаемся к справке
        print(f"[nuva-ai] {type(e).__name__}: {e}")
        return None
    return clean(out)[:4000] or None


# иероглифы и прочие «чужие» письменности, которых в ответах Нувы быть не должно
FOREIGN = re.compile(r"[\u0590-\u08ff\u0e00-\u0e7f\u1100-\u11ff\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff\uff00-\uff60]")


def clean(text):
    """Убирает предложения с иероглифами; если ничего не осталось — пусто (тогда Нува ответит по справке)."""
    if not FOREIGN.search(text or ""):
        return (text or "").strip()
    parts = re.split(r"(?<=[.!?…])\s+|\n+", text)
    return " ".join(p for p in parts if p and not FOREIGN.search(p)).strip()


def rewrite(text, mode):
    """«Исправить текст» нейросетью: исправляет ошибки, не меняя смысл и стиль."""
    if not enabled() or mode != "fix":
        return None
    try:
        out = _post([{"role": "system", "content": "Исправь орфографию, пунктуацию и опечатки в тексте пользователя. Не меняй смысл, "
                                                   "стиль, эмодзи, хэштеги и @упоминания. Верни только исправленный текст без пояснений."},
                     {"role": "user", "content": text[:4000]}], max_tokens=1500, temperature=0.1)
    except Exception as e:  # noqa: BLE001
        print(f"[nuva-ai] rewrite {e}")
        return None
    out = clean(out)
    return out or None
