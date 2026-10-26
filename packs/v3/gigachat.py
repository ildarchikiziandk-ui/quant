"""Нува на нейросети GigaChat (Сбер): живые ответы, тексты, идеи — с опорой на справку Nuvora.

Включается ключом GIGACHAT_AUTH_KEY в .env (скрипт deploy/set-gigachat.sh). Сертификат сервера GigaChat выдан
НУЦ Минцифры — его корневой сертификат скрипт кладёт в GIGACHAT_CA; проверку TLS мы не отключаем.
Если ключа нет, лимит исчерпан или сервис не ответил — Нува отвечает по справке, как раньше.
"""
import json
import ssl
import threading
import time
import urllib.parse
import urllib.request
import uuid

import config

OAUTH = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
API = config.GIGACHAT_API_URL.rstrip("/") + "/chat/completions"  # новый адрес из кабинета: https://api.giga.chat/v1
_tok = {"v": "", "exp": 0.0}
_lock = threading.Lock()

SYSTEM = """Ты — Нува, дружелюбная помощница социальной сети Nuvora (nvra.ru). Отвечай по-русски, тепло и по делу,
коротко: 1–5 предложений или короткий список, если не просят длиннее. Можешь болтать, шутить, советовать,
придумывать подписи к фото, поздравления, идеи постов, помогать с текстами и учёбой.
Про функции Nuvora опирайся только на справку ниже; если в справке ответа нет — честно скажи, что не уверена,
и предложи написать в поддержку (раздел «Поддержка»). Не выдумывай кнопки и разделы.
Внутренняя валюта Nuvora называется «Искры». Подписка — Nuvora+.
Не проси и не повторяй пароли, коды и личные данные. Не помогай с опасным, незаконным и травлей.
Пользователя зовут: {name}."""


def enabled():
    return bool(config.GIGACHAT_AUTH_KEY)


def _ctx():
    if config.GIGACHAT_CA:
        return ssl.create_default_context(cafile=config.GIGACHAT_CA)
    return ssl.create_default_context()


def _token():
    with _lock:
        if _tok["v"] and time.time() < _tok["exp"] - 60:
            return _tok["v"]
        req = urllib.request.Request(OAUTH, method="POST", data=urllib.parse.urlencode({"scope": config.GIGACHAT_SCOPE}).encode(),
                                     headers={"Authorization": f"Basic {config.GIGACHAT_AUTH_KEY}", "RqUID": str(uuid.uuid4()),
                                              "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10, context=_ctx()) as r:
            j = json.load(r)
        _tok["v"] = j["access_token"]
        _tok["exp"] = (j.get("expires_at") or 0) / 1000 or time.time() + 25 * 60
        return _tok["v"]


def _post(messages, max_tokens=700, temperature=0.7):
    """Запрос к GigaChat. Вынесено отдельно, чтобы в тестах подменить."""
    body = json.dumps({"model": config.GIGACHAT_MODEL, "messages": messages, "temperature": temperature,
                       "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(API, method="POST", data=body, headers={
        "Authorization": f"Bearer {_token()}", "Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25, context=_ctx()) as r:
        j = json.load(r)
    return (j["choices"][0]["message"]["content"] or "").strip()


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
    except Exception as e:  # noqa: BLE001 — сеть, лимиты, сертификат: молча возвращаемся к справке
        print(f"[gigachat] {type(e).__name__}: {e}")
        return None
    return out[:4000] or None


def rewrite(text, mode):
    """«Исправить текст» нейросетью: исправляет ошибки, не меняя смысл и стиль."""
    if not enabled() or mode != "fix":
        return None
    try:
        out = _post([{"role": "system", "content": "Исправь орфографию, пунктуацию и опечатки в тексте пользователя. Не меняй смысл, "
                                                   "стиль, эмодзи, хэштеги и @упоминания. Верни только исправленный текст без пояснений."},
                     {"role": "user", "content": text[:4000]}], max_tokens=1500, temperature=0.1)
    except Exception as e:  # noqa: BLE001
        print(f"[gigachat] rewrite {e}")
        return None
    return out or None
