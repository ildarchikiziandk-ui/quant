"""Приложение школы для Android: сервер узнаёт последнюю сборку (релизы school-v1.0.N на GitHub),
держит копию APK у себя и раздаёт её — ни ученику, ни учителю не нужно заходить на GitHub."""
import json
import os
import re
import threading
import time
import urllib.request

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from . import config
from . import db as m
from .core import render

router = APIRouter()
_cache = {"t": 0.0, "data": None}
_lock = threading.Lock()
_busy = set()
PREFIX = "school-v"


def latest():
    if _cache["data"] and time.time() - _cache["t"] < 1800:
        return _cache["data"]
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{config.ANDROID_REPO}/releases?per_page=30",
                                     headers={"Accept": "application/vnd.github+json", "User-Agent": "school-server"})
        with urllib.request.urlopen(req, timeout=6) as r:
            rels = json.load(r)
        for rel in rels:
            tag = rel.get("tag_name") or ""
            mt = re.fullmatch(PREFIX + r"1\.0\.(\d+)", tag)
            apk = next((a for a in rel.get("assets") or [] if str(a.get("name", "")).endswith(".apk")), None)
            if mt and apk:
                _cache["data"] = {"version_code": int(mt.group(1)), "version": f"1.0.{mt.group(1)}",
                                  "apk": apk["browser_download_url"], "size": apk.get("size") or 0}
                break
    except Exception as e:  # noqa: BLE001 — GitHub недоступен: отдаём то, что уже знаем
        print(f"[school-app] {e}")
    _cache["t"] = time.time()
    return _cache["data"]


def _path(code):
    return os.path.join(config.APK_CACHE_DIR, f"School-{code}.apk")


def _mirror(info):
    code = info["version_code"]
    with _lock:
        if code in _busy:
            return
        _busy.add(code)
    try:
        os.makedirs(config.APK_CACHE_DIR, exist_ok=True)
        tmp = _path(code) + ".part"
        req = urllib.request.Request(info["apk"], headers={"User-Agent": "school-server"})
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            while chunk := r.read(1 << 16):
                f.write(chunk)
        if info.get("size") and os.path.getsize(tmp) != info["size"]:
            raise IOError("размер не совпал")
        os.replace(tmp, _path(code))
        for name in os.listdir(config.APK_CACHE_DIR):
            if name.startswith("School-") and name != os.path.basename(_path(code)):
                os.remove(os.path.join(config.APK_CACHE_DIR, name))
    except Exception as e:  # noqa: BLE001
        print(f"[school-app] mirror failed: {e}")
    finally:
        _busy.discard(code)


@router.get("/api/app/latest")
def app_latest():
    info = latest()
    if not info:
        return JSONResponse({"ok": False}, status_code=503)
    if not os.path.isfile(_path(info["version_code"])):
        threading.Thread(target=_mirror, args=(info,), daemon=True).start()
    return {"ok": True, "version_code": info["version_code"], "version": info["version"], "url": f"{config.SITE_URL}/download/school.apk"}


@router.get("/download/school.apk")
def download():
    info = latest()
    if not info:
        return JSONResponse({"ok": False, "error": "Приложение ещё не собрано"}, status_code=503)
    p = _path(info["version_code"])
    if os.path.isfile(p):
        return FileResponse(p, media_type="application/vnd.android.package-archive", filename="School.apk")
    threading.Thread(target=_mirror, args=(info,), daemon=True).start()
    return RedirectResponse(info["apk"], status_code=302)


@router.get("/app")
def app_page(request: Request, db: Session = Depends(m.get_db)):
    info = latest()
    return render(request, db, "app.html", info=info)
