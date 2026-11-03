"""Копия сайта на компьютер владельца (/admin/backup): база с постами, сообщениями и пользователями — одним zip,
фото и файлы — отдельным архивом. Скачивать может только основатель. Нужна на случай аварии у хостинга:
по этим двум файлам Нувору можно поднять на любом другом сервере (инструкция лежит внутри архива)."""
import io
import os
import sqlite3
import tarfile
import tempfile
import zipfile
from datetime import datetime

from fastapi import Depends, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

import config
from database import get_db
from deps import current_user, log_mod, redirect, render
from services import social

from . import site
from .common import router

SCHOOL_DB = os.path.join(config.BASE_DIR, "school", "data", "school.db")
README = """Резервная копия Nuvora от {when}

Что внутри:
  quant.db        — база сайта: пользователи, посты, комментарии, сообщения, подарки, настройки
  env.txt         — настройки сервера (файл .env). В нём SECRET_KEY — без него не расшифруются сообщения.
                    НИКОМУ НЕ ОТПРАВЛЯЙТЕ этот архив и не выкладывайте его в интернет.
  school.db       — база электронной школы (если она есть)
Фото и файлы пользователей скачиваются отдельной кнопкой (архив uploads).

Как восстановить на новом сервере:
  1. Поставить Нувору как обычно: bash deploy/install.sh ваш-домен
  2. Загрузить на сервер этот архив и архив с фото (например, в папку /root)
  3. Выполнить: bash /opt/nuvora/deploy/restore.sh /root/этот-архив.zip /root/архив-с-фото.tar.gz
"""


def _founder(request, db):
    user = current_user(request, db)
    if not user or not user.is_owner:
        return None
    main = social.main_owner(db)
    return user if main and main.id == user.id else None


def _db_path():
    url = config.DATABASE_URL
    return url.split("sqlite:///", 1)[1] if url.startswith("sqlite:///") else ""


def _size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _mb(n):
    return f"{n / 1024 / 1024:.1f} МБ" if n < 1024 ** 3 else f"{n / 1024 ** 3:.2f} ГБ"


@router.get("/admin/backup")
def backup_page(request: Request, db: Session = Depends(get_db)):
    me = _founder(request, db)
    if not me:
        return redirect("/admin")
    dbp = _db_path()
    info = {"db": _mb(os.path.getsize(dbp)) if dbp and os.path.exists(dbp) else "—",
            "uploads": _mb(_size(config.UPLOAD_DIR)) if os.path.isdir(config.UPLOAD_DIR) else "—",
            "last_db": site.get("backup_last_db") or "", "last_files": site.get("backup_last_files") or ""}
    return render(request, db, "packs/v3/admin_backup.html", sidebar=False, info=info)


@router.get("/admin/backup/db.zip")
def backup_db(request: Request, db: Session = Depends(get_db)):
    me = _founder(request, db)
    if not me:
        return redirect("/admin")
    dbp = _db_path()
    if not dbp or not os.path.exists(dbp):
        return redirect("/admin/backup")
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    fd, out = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    snap = out + ".db"
    src, dst = sqlite3.connect(dbp), sqlite3.connect(snap)
    try:
        src.backup(dst)  # целая копия даже во время работы сайта
    finally:
        dst.close()
        src.close()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(snap, "quant.db")
        env = os.path.join(config.BASE_DIR, ".env")
        if os.path.exists(env):
            z.write(env, "env.txt")
        if os.path.exists(SCHOOL_DB):
            ssnap = out + ".school"
            s1, s2 = sqlite3.connect(SCHOOL_DB), sqlite3.connect(ssnap)
            try:
                s1.backup(s2)
            finally:
                s2.close()
                s1.close()
            z.write(ssnap, "school.db")
            os.remove(ssnap)
        z.writestr("ПРОЧТИ.txt", README.format(when=stamp))
    os.remove(snap)
    site.put(db, "backup_last_db", datetime.now().strftime("%d.%m.%Y %H:%M"))
    log_mod(db, me, "backup_download", "db")
    db.commit()
    return FileResponse(out, filename=f"nuvora-baza-{stamp}.zip", media_type="application/zip",
                        background=BackgroundTask(lambda: os.path.exists(out) and os.remove(out)))


class _Pipe(io.RawIOBase):
    """Куда tarfile пишет архив: копим байты и отдаём их браузеру кусками — на диске сервера ничего не создаётся."""
    def __init__(self):
        self.buf = bytearray()

    def writable(self):
        return True

    def write(self, b):
        self.buf += b
        return len(b)

    def take(self):
        out = bytes(self.buf)
        self.buf.clear()
        return out


def _stream_uploads():
    pipe = _Pipe()
    with tarfile.open(fileobj=pipe, mode="w|gz") as tar:
        for root, _dirs, files in os.walk(config.UPLOAD_DIR):
            for name in files:
                path = os.path.join(root, name)
                try:
                    tar.add(path, arcname=os.path.relpath(path, config.UPLOAD_DIR))
                except OSError:
                    continue
                if len(pipe.buf) > 1024 * 1024:
                    yield pipe.take()
    yield pipe.take()


@router.get("/admin/backup/uploads.tar.gz")
def backup_uploads(request: Request, db: Session = Depends(get_db)):
    me = _founder(request, db)
    if not me or not os.path.isdir(config.UPLOAD_DIR):
        return redirect("/admin")
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    site.put(db, "backup_last_files", datetime.now().strftime("%d.%m.%Y %H:%M"))
    log_mod(db, me, "backup_download", "uploads")
    db.commit()
    return StreamingResponse(_stream_uploads(), media_type="application/gzip",
                             headers={"Content-Disposition": f'attachment; filename="nuvora-foto-{stamp}.tar.gz"'})


@router.post("/v3/rename-notice/hide")
def rename_notice_hide(request: Request, db: Session = Depends(get_db)):
    """Плашка «вам выдан временный логин» (после объединения баз) — больше не показывать."""
    me = current_user(request, db)
    if me and me.rename_notice:
        me.rename_notice = False  # previous_username оставляем: по нему можно входить, пока логин не сменён
        db.commit()
    return redirect(request.headers.get("referer") or "/")
