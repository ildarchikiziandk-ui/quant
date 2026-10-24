"""Обновление Android-приложения изнутри: сайт узнаёт последнюю сборку в GitHub Releases (раз в 30 минут),
хранит копию APK у себя и раздаёт её сам — пользователю не нужно заходить на GitHub."""
import json
import os
import re
import threading
import time
import urllib.request

from fastapi import Depends, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

import config
from database import get_db

from .common import router

_cache = {"t": 0.0, "data": None}
_lock = threading.Lock()
_fetching = set()


def latest():
    """{"version_code", "version", "apk"} последней сборки или None (GitHub недоступен — берём прошлое значение)."""
    if _cache["data"] and time.time() - _cache["t"] < 1800:
        return _cache["data"]
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{config.ANDROID_REPO}/releases/latest",
                                     headers={"Accept": "application/vnd.github+json", "User-Agent": "nuvora-server"})
        with urllib.request.urlopen(req, timeout=6) as r:
            j = json.load(r)
        m = re.search(r"(\d+)$", j.get("tag_name") or "")
        apk = next((a for a in j.get("assets") or [] if str(a.get("name", "")).endswith(".apk")), None)
        if m and apk:
            _cache["data"] = {"version_code": int(m.group(1)), "version": f"1.0.{m.group(1)}",
                              "apk": apk["browser_download_url"], "size": apk.get("size") or 0}
    except Exception as e:  # noqa: BLE001 — нет сети до GitHub: отдаём то, что уже знаем
        print(f"[app-update] {e}")
    _cache["t"] = time.time()
    return _cache["data"]


def _path(code):
    return os.path.join(config.APP_CACHE_DIR, f"Nuvora-{code}.apk")


def _mirror(info):
    """Скачать APK к себе (в фоне, один раз), старые копии удалить."""
    code = info["version_code"]
    with _lock:
        if code in _fetching:
            return
        _fetching.add(code)
    try:
        os.makedirs(config.APP_CACHE_DIR, exist_ok=True)
        tmp = _path(code) + ".part"
        req = urllib.request.Request(info["apk"], headers={"User-Agent": "nuvora-server"})
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
        if info.get("size") and os.path.getsize(tmp) != info["size"]:
            raise IOError("размер не совпал")
        os.replace(tmp, _path(code))
        for name in os.listdir(config.APP_CACHE_DIR):
            if name.startswith("Nuvora-") and name != os.path.basename(_path(code)):
                try:
                    os.remove(os.path.join(config.APP_CACHE_DIR, name))
                except OSError:
                    pass
    except Exception as e:  # noqa: BLE001
        print(f"[app-update] mirror failed: {e}")
    finally:
        _fetching.discard(code)


@router.get("/api/app/latest")
def app_latest():
    info = latest()
    if not info:
        return JSONResponse({"ok": False}, status_code=503)
    return JSONResponse({"ok": True, "version_code": info["version_code"], "version": info["version"],
                         "url": f"{config.SITE_URL}/download/android.apk?v={info['version_code']}", "size": info["size"]})


@router.get("/download/android.apk")
def app_download():
    info = latest()
    if not info:
        return RedirectResponse(f"https://github.com/{config.ANDROID_REPO}/releases/latest/download/Nuvora.apk", status_code=302)
    p = _path(info["version_code"])
    if os.path.isfile(p):
        return FileResponse(p, media_type="application/vnd.android.package-archive", filename="Nuvora.apk")
    threading.Thread(target=_mirror, args=(info,), daemon=True).start()
    return RedirectResponse(info["apk"], status_code=302)  # пока копия качается — прямо с GitHub


@router.get("/app")
def app_page(request: Request, db: Session = Depends(get_db)):
    from deps import render
    return render(request, db, "packs/v3/app_install.html")
