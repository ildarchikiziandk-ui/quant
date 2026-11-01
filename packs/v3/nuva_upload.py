"""Приём дообученной модели Нувы из Google Colab (tools/nuva_finetune.ipynb).

Модель весит ~0,5 ГБ, поэтому приходит частями по 40 МБ. Пускаем только с кодом NUVA_UPLOAD_CODE из .env
(его выдаёт deploy/nuva-upload-code.sh). Готовый файл — data/ai/nuva-custom.gguf; включает его
deploy/set-local-ai.sh (служба nuvora-ai берёт свою модель вместо стандартной).
"""
import hmac
import os

from fastapi import Request
from fastapi.responses import JSONResponse

import config

from .common import router

PART_MAX = 50 * 1024 * 1024
TOTAL_MAX = 2 * 1024 * 1024 * 1024


def _ok(request):
    code = config.NUVA_UPLOAD_CODE
    given = request.headers.get("x-upload-code", "")
    return bool(code) and len(code) >= 16 and hmac.compare_digest(code, given)


@router.post("/api/nuva-model/upload")
async def nuva_model_upload(request: Request, part: int = 0, total: int = 1):
    if not _ok(request):
        return JSONResponse({"ok": False, "error": "Неверный код загрузки"}, status_code=403)
    if not (0 <= part < total <= 64):
        return JSONResponse({"ok": False, "error": "Неверный номер части"}, status_code=400)
    data = await request.body()
    if not data or len(data) > PART_MAX:
        return JSONResponse({"ok": False, "error": "Часть пустая или больше 50 МБ"}, status_code=400)
    os.makedirs(config.NUVA_MODEL_DIR, exist_ok=True)
    tmp = os.path.join(config.NUVA_MODEL_DIR, "nuva-custom.gguf.part")
    if part == 0 and os.path.exists(tmp):
        os.remove(tmp)
    if part > 0 and not os.path.exists(tmp):
        return JSONResponse({"ok": False, "error": "Начните загрузку с первой части"}, status_code=400)
    if os.path.exists(tmp) and os.path.getsize(tmp) + len(data) > TOTAL_MAX:
        return JSONResponse({"ok": False, "error": "Файл слишком большой"}, status_code=400)
    with open(tmp, "ab") as f:
        f.write(data)
    if part == total - 1:
        with open(tmp, "rb") as f:
            if f.read(4) != b"GGUF":
                os.remove(tmp)
                return JSONResponse({"ok": False, "error": "Это не файл модели GGUF"}, status_code=400)
        os.replace(tmp, os.path.join(config.NUVA_MODEL_DIR, "nuva-custom.gguf"))
        return JSONResponse({"ok": True, "done": True, "size": os.path.getsize(os.path.join(config.NUVA_MODEL_DIR, "nuva-custom.gguf"))})
    return JSONResponse({"ok": True, "done": False})
