"""Вложения в чатах хранятся на сервере 7 дней: потом файл стирается, а в переписке остаётся пометка.
Постоянно на сервере хранятся только посты, аватарки, истории и другие публичные вещи."""
from datetime import datetime, timedelta

from sqlalchemy import or_

import models
from services.uploads import delete_file

KEEP_DAYS = 7
BATCH = 300


def _kind(row, field):
    if field == "voice":
        return "voice"
    if field == "file_url":
        return "file"
    if row.is_video_circle:
        return "circle"
    return "video" if (row.image or "").lower().endswith((".mp4", ".mov", ".webm")) else "photo"


def _used_elsewhere(db, url, cutoff):
    """Файл ещё нужен: его переслали в свежее сообщение или он стоит в посте/истории."""
    for model in (models.Message, models.GroupMessage):
        if db.query(model.id).filter(model.created_at >= cutoff, or_(model.image == url, model.voice == url, model.file_url == url)).first():
            return True
    if db.query(models.Post.id).filter(models.Post.image == url).first() or db.query(models.PostMedia.id).filter(models.PostMedia.media_url == url).first():
        return True
    return False


def expire_chat_media(db, now=None):
    cutoff = (now or datetime.utcnow()) - timedelta(days=KEEP_DAYS)
    done = 0
    for model in (models.Message, models.GroupMessage):
        rows = (db.query(model).filter(model.created_at < cutoff, or_(model.media_expired == None, model.media_expired == ""),  # noqa: E711
                                       or_(model.image != "", model.voice != "", model.file_url != ""))
                .order_by(model.id).limit(BATCH).all())
        for row in rows:
            kind = ""
            for field in ("image", "voice", "file_url"):
                url = getattr(row, field) or ""
                if not url:
                    continue
                kind = kind or _kind(row, field)
                if url.startswith("/uploads/") and not _used_elsewhere(db, url, cutoff):
                    delete_file(url)
                setattr(row, field, "")
            row.media_expired = kind or "file"
            done += 1
    if done:
        db.commit()
    return done
