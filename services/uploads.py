"""Сохранение загруженных файлов: проверка типа и размера, сжатие и поворот фото."""
import io
import os
import uuid

from PIL import Image, ImageOps

import config

os.makedirs(config.UPLOAD_DIR, exist_ok=True)

IMAGE_TYPES = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
VIDEO_TYPES = {"video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm"}
AUDIO_TYPES = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a", "audio/mpeg": ".mp3", "audio/wav": ".wav"}
FILE_TYPES = {
    "application/pdf": ".pdf", "application/msword": ".doc", "text/plain": ".txt", "application/zip": ".zip",
    "application/x-zip-compressed": ".zip",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
}


def is_upload(obj) -> bool:
    return obj is not None and hasattr(obj, "filename") and bool(obj.filename)


def _read_limited(upload, limit):
    data = upload.file.read(limit + 1)
    return data, len(data) > limit


def save_file(upload, allowed=("image", "video", "audio", "file")):
    """Возвращает (url, media_type) или (None, текст ошибки)."""
    if not is_upload(upload):
        return None, "Файл не выбран"
    ct = (upload.content_type or "").lower().split(";")[0].strip()
    if ct in IMAGE_TYPES:
        mtype, ext, limit = "image", IMAGE_TYPES[ct], config.MAX_IMAGE_SIZE
    elif ct in VIDEO_TYPES:
        mtype, ext, limit = "video", VIDEO_TYPES[ct], config.MAX_VIDEO_SIZE
    elif ct in AUDIO_TYPES:
        mtype, ext, limit = "audio", AUDIO_TYPES[ct], config.MAX_AUDIO_SIZE
    elif ct in FILE_TYPES:
        mtype, ext, limit = "file", FILE_TYPES[ct], config.MAX_FILE_SIZE
    else:
        return None, "Неподдерживаемый формат файла"
    if mtype not in allowed:
        return None, "Этот тип файла здесь нельзя загрузить"
    contents, too_big = _read_limited(upload, limit)
    if too_big:
        return None, f"Файл слишком большой (макс. {limit // (1024 * 1024)} МБ)"
    if not contents:
        return None, "Пустой файл"
    fname = f"{uuid.uuid4().hex}{ext}"
    fpath = os.path.join(config.UPLOAD_DIR, fname)
    if mtype == "image" and ext != ".gif":
        try:
            img = Image.open(io.BytesIO(contents))
            img = ImageOps.exif_transpose(img)
            if img.width > config.MAX_IMAGE_DIMENSION or img.height > config.MAX_IMAGE_DIMENSION:
                img.thumbnail((config.MAX_IMAGE_DIMENSION, config.MAX_IMAGE_DIMENSION), Image.LANCZOS)
            params = {"optimize": True}
            if ext == ".jpg":
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                params["quality"] = 85
            elif ext == ".webp":
                params["quality"] = 85
            img.save(fpath, **params)
        except Exception as ex:
            print(f"Image error: {ex}")
            return None, "Не удалось обработать фото"
    else:
        if mtype == "image":
            try:
                Image.open(io.BytesIO(contents)).verify()
            except Exception:
                return None, "Повреждённое изображение"
        with open(fpath, "wb") as f:
            f.write(contents)
    return f"/uploads/{fname}", mtype


def delete_file(url):
    if not url or not url.startswith("/uploads/"):
        return
    name = os.path.basename(url)
    try:
        fpath = os.path.join(config.UPLOAD_DIR, name)
        if os.path.exists(fpath):
            os.remove(fpath)
    except OSError:
        pass
