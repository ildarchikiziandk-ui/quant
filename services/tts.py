"""Встроенная озвучка постов (7.11.2026): голос рисует сам сервер программой Piper — без чужих сервисов, работает
в любом браузере и в старом приложении (там своей озвучки нет). Голоса ставит `bash /opt/nuvora/deploy/set-tts.sh`
в data/tts/voices (*.onnx + *.onnx.json + MODEL_CARD), какой звучит — выбирает владелец: админка → «Озвучка».
Готовые записи кэшируются в data/tts/cache (mp3, если есть ffmpeg, иначе wav), один и тот же пост второй раз не рисуется.
Свой голос: data/tts/voices/nuvora-custom.onnx (обучается по записям из «Студии голоса», см. packs/v3/tts.py)."""
import hashlib
import os
import re
import shutil
import subprocess
import threading
import wave

import config

ROOT = os.path.join(config.BASE_DIR, "data", "tts")
VOICES = os.path.join(ROOT, "voices")
CACHE = os.path.join(ROOT, "cache")
NAMES = {"irina": "Ирина", "denis": "Денис", "dmitri": "Дмитрий", "ruslan": "Руслан", "nuvora-custom": "Голос Nuvora (свой)"}
_lock = threading.Lock()
_loaded = {}
MAX_CHARS = 1500


def voices():
    """[(id, имя, лицензия)] установленных голосов."""
    out = []
    try:
        files = sorted(f for f in os.listdir(VOICES) if f.endswith(".onnx") and os.path.exists(os.path.join(VOICES, f + ".json")))
    except OSError:
        return []
    for f in files:
        vid = f[:-5]
        key = next((k for k in NAMES if k in vid), vid)
        out.append((vid, NAMES.get(key, vid), license_of(vid)))
    return out


def license_of(vid):
    """Строка про лицензию из MODEL_CARD голоса (её скачивает set-tts.sh)."""
    try:
        card = open(os.path.join(VOICES, vid + ".MODEL_CARD"), encoding="utf-8", errors="replace").read()
    except OSError:
        return "свой голос" if "custom" in vid else "неизвестно"
    m = re.search(r"(?im)^\s*\*?\s*licen[cs]e[^:\n]*:\s*(.+)$", card)
    return (m.group(1).strip() if m else "смотрите MODEL_CARD")[:80]


def noncommercial(vid):
    return bool(re.search(r"(?i)\bNC\b|non-?commercial|некоммерч", license_of(vid)))


def current():
    """Выбранный владельцем голос; если не выбран — первый подходящий для сайта (без «только некоммерческое»)."""
    from packs.v3 import site
    have = [v[0] for v in voices()]
    chosen = site.get("tts_voice") or ""
    if chosen in have:
        return chosen
    for v in have:
        if "custom" in v:
            return v
    return next((v for v in have if not noncommercial(v)), "")


def enabled():
    try:
        from packs.v3 import site
        return bool(site.get("tts_on")) and bool(current())
    except Exception:  # noqa: BLE001
        return False


def clean(text):
    """Текст поста → то, что читаем вслух: без ссылок, разметки, решёток и эмодзи."""
    t = str(text or "")
    t = re.sub(r"https?://\S+", " ссылка ", t)
    t = re.sub(r"\[\[v3:[^\]]+\]\]", " ", t)
    t = re.sub(r"[*_~`|>#]+", " ", t)
    t = re.sub(r"@([\w.]+)", r"\1", t)
    t = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️‍]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:MAX_CHARS]


def _voice(vid):
    if vid not in _loaded:
        from piper import PiperVoice  # ставится set-tts.sh (piper-tts)
        _loaded.clear()  # в памяти держим один голос
        _loaded[vid] = PiperVoice.load(os.path.join(VOICES, vid + ".onnx"))
    return _loaded[vid]


def speak(text, vid=None):
    """Готовый звуковой файл (путь, тип) или (None, причина)."""
    vid = vid or current()
    text = clean(text)
    if not vid:
        return None, "Озвучка ещё не установлена"
    if not text:
        return None, "Нечего читать"
    os.makedirs(CACHE, exist_ok=True)
    key = hashlib.sha1(f"{vid}|{text}".encode()).hexdigest()[:24]
    mp3, wav = os.path.join(CACHE, key + ".mp3"), os.path.join(CACHE, key + ".wav")
    for p, mt in ((mp3, "audio/mpeg"), (wav, "audio/wav")):
        if os.path.exists(p):
            return p, mt
    with _lock:  # голос рисуется по одному: у сервера 2 ядра, остальным людям тоже нужно
        if not os.path.exists(mp3) and not os.path.exists(wav):
            tmp = wav + ".part"
            with wave.open(tmp, "wb") as w:
                _voice(vid).synthesize_wav(text, w)
            os.replace(tmp, wav)
            if shutil.which("ffmpeg"):
                r = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", wav, "-ac", "1", "-b:a", "64k", mp3 + ".part.mp3"], capture_output=True)
                if r.returncode == 0:
                    os.replace(mp3 + ".part.mp3", mp3)
                    os.remove(wav)
        _prune()
    return (mp3, "audio/mpeg") if os.path.exists(mp3) else (wav, "audio/wav")


def _prune(limit_mb=400):
    """Кэш не больше ~400 МБ: самые старые записи удаляются."""
    try:
        files = [os.path.join(CACHE, f) for f in os.listdir(CACHE)]
        files = [(os.path.getmtime(f), os.path.getsize(f), f) for f in files if os.path.isfile(f)]
        total = sum(s for _, s, _ in files)
        for _, s, f in sorted(files):
            if total <= limit_mb * 1024 * 1024:
                break
            os.remove(f)
            total -= s
    except OSError:
        pass
