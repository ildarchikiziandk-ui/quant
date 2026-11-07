"""Озвучка постов голосом сервера (services/tts.py) и «Студия голоса» владельца (7.11.2026).
/tts/post/<id>           — mp3 поста (вход нужен; 30 новых озвучек за 10 минут на человека)
/admin/tts               — какой голос, прослушать пример, включить/выключить (владелец)
/admin/voice             — студия: владелец читает фразы, записи копятся в data/tts/studio (только основатель)
/admin/voice/dataset.zip — записи + metadata.csv для обучения своего голоса"""
import io
import os
import zipfile

from fastapi import Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy.orm import Session

from database import get_db
from deps import current_user, json_error, redirect, render
from services import ratelimit, social, tts

from . import site
from .common import router, s
from .voice_phrases import PHRASES

STUDIO = os.path.join(tts.ROOT, "studio")
SAMPLE = "Привет! Это Nuvora. Так будут звучать посты, когда вы нажмёте «Прослушать»."
AUDIO_EXT = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a", "audio/mpeg": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav"}


def _audio(path, mt):
    return FileResponse(path, media_type=mt, headers={"Cache-Control": "private, max-age=604800"})


@router.get("/tts/post/{post_id}")
async def tts_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    from routers.posts import _check_access
    post, err = _check_access(db, user, post_id)
    if err:
        return err
    if not tts.enabled():
        return json_error("Озвучка пока не установлена", 404)
    text = post.content or ""
    if not tts.clean(text):
        return json_error("В посте нет текста", 400)
    if not ratelimit.hit(f"tts:{user.id}", 30, 600):
        return json_error("Слишком много озвучек подряд — подождите пару минут", 429)
    try:
        path, mt = await run_in_threadpool(tts.speak, text)
    except Exception as e:  # noqa: BLE001
        print(f"[tts] ошибка: {e}")
        return json_error("Не получилось озвучить", 500)
    if not path:
        return json_error(mt, 400)
    return _audio(path, mt)


def _owner(request, db):
    u = current_user(request, db)
    return u if u and u.is_owner else None


def _founder(request, db):
    u = current_user(request, db)
    mo = social.main_owner(db) if u and u.is_owner else None
    return u if mo and mo.id == u.id else None


@router.get("/admin/tts")
def admin_tts(request: Request, db: Session = Depends(get_db)):
    me = _owner(request, db)
    if not me:
        return redirect("/")
    vs = [{"id": v, "name": n, "license": lic, "nc": tts.noncommercial(v)} for v, n, lic in tts.voices()]
    done = len(_recorded())
    return render(request, db, "packs/v3/admin_tts.html", voices=vs, current=tts.current(), on=bool(site.get("tts_on")),
                  founder=bool(_founder(request, db)), done=done, total=len(PHRASES))


@router.post("/admin/tts")
async def admin_tts_save(request: Request, db: Session = Depends(get_db)):
    me = _owner(request, db)
    if not me:
        return json_error("forbidden", 403)
    f = await request.form()
    vid = s(f.get("voice"))
    if vid and vid in [v[0] for v in tts.voices()]:
        site.put(db, "tts_voice", vid)
    site.put(db, "tts_on", bool(f.get("on")))
    return redirect("/admin/tts")


@router.get("/admin/tts/sample/{vid}")
async def admin_tts_sample(vid: str, request: Request, db: Session = Depends(get_db)):
    if not _owner(request, db) or vid not in [v[0] for v in tts.voices()]:
        return json_error("forbidden", 403)
    path, mt = await run_in_threadpool(tts.speak, SAMPLE, vid)
    return _audio(path, mt) if path else json_error(mt, 400)


# ---------------------------------------------------------------- студия голоса (только основатель)
def _recorded():
    out = {}
    try:
        for f in os.listdir(STUDIO):
            stem, ext = os.path.splitext(f)
            if stem.isdigit() and ext in AUDIO_EXT.values():
                out[int(stem)] = f
    except OSError:
        pass
    return out


@router.get("/admin/voice")
def voice_studio(request: Request, db: Session = Depends(get_db)):
    if not _founder(request, db):
        return redirect("/")
    return render(request, db, "packs/v3/voice_studio.html", phrases=PHRASES, recorded=sorted(_recorded()))


@router.post("/admin/voice/rec/{n}")
async def voice_save(n: int, request: Request, db: Session = Depends(get_db)):
    if not _founder(request, db):
        return json_error("forbidden", 403)
    if not 0 <= n < len(PHRASES):
        return json_error("Нет такой фразы", 404)
    form = await request.form()
    up = form.get("audio")
    ct = (getattr(up, "content_type", "") or "").split(";")[0].strip().lower()
    if not up or ct not in AUDIO_EXT:
        return json_error("Нужна запись голоса", 400)
    data = up.file.read(4 * 1024 * 1024 + 1)
    if len(data) > 4 * 1024 * 1024 or len(data) < 1000:
        return json_error("Запись слишком длинная или пустая", 400)
    os.makedirs(STUDIO, exist_ok=True)
    old = _recorded().get(n)  # перезапись фразы — старый файл (могло быть другое расширение) убираем
    if old:
        try:
            os.remove(os.path.join(STUDIO, old))
        except OSError:
            pass
    with open(os.path.join(STUDIO, f"{n:03d}{AUDIO_EXT[ct]}"), "wb") as fh:
        fh.write(data)
    return JSONResponse({"ok": True, "done": len(_recorded())})


@router.get("/admin/voice/rec/{n}")
def voice_get(n: int, request: Request, db: Session = Depends(get_db)):
    f = _recorded().get(n)
    if not _founder(request, db) or not f:
        return Response(status_code=404)
    ext = os.path.splitext(f)[1]
    mt = next((k for k, v in AUDIO_EXT.items() if v == ext), "audio/webm")
    return FileResponse(os.path.join(STUDIO, f), media_type=mt, headers={"Cache-Control": "no-store"})


@router.get("/admin/voice/dataset.zip")
def voice_dataset(request: Request, db: Session = Depends(get_db)):
    """Записи + metadata.csv (номер|текст) — для обучения своего голоса."""
    if not _founder(request, db):
        return redirect("/")
    rec = _recorded()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("metadata.csv", "\n".join(f"{n:03d}|{PHRASES[n]}" for n in sorted(rec)) + "\n")
        for n, f in sorted(rec.items()):
            z.write(os.path.join(STUDIO, f), f"wavs/{f}")
    return Response(buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="nuvora-voice.zip"'})


# ---------------------------------------------------------------- связь с блокнотом Colab (tools/voice_finetune.ipynb)
# Тот же код загрузки, что у Нувы: NUVA_UPLOAD_CODE из .env (выдаёт deploy/nuva-upload-code.sh).
def _code_ok(request):
    from .nuva_upload import _ok
    return _ok(request)


@router.get("/api/voice/dataset")
def api_voice_dataset(request: Request, db: Session = Depends(get_db)):
    if not _code_ok(request):
        return JSONResponse({"ok": False, "error": "Неверный код загрузки"}, status_code=403)
    rec = _recorded()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("metadata.csv", "\n".join(f"{n:03d}|{PHRASES[n]}" for n in sorted(rec)) + "\n")
        for n, f in sorted(rec.items()):
            z.write(os.path.join(STUDIO, f), f"wavs/{f}")
    return Response(buf.getvalue(), media_type="application/zip")


@router.post("/api/voice-model/upload")
async def api_voice_model(request: Request, kind: str = "onnx", part: int = 0, total: int = 1, db: Session = Depends(get_db)):
    """Готовый свой голос: kind=json — настройки (один запрос), kind=onnx — модель частями по 40 МБ."""
    if not _code_ok(request):
        return JSONResponse({"ok": False, "error": "Неверный код загрузки"}, status_code=403)
    os.makedirs(tts.VOICES, exist_ok=True)
    data = await request.body()
    base = os.path.join(tts.VOICES, "nuvora-custom.onnx")
    if kind == "json":
        import json as _json
        try:
            cfg = _json.loads(data.decode("utf-8"))
            assert isinstance(cfg, dict) and "audio" in cfg
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": "Это не настройки голоса"}, status_code=400)
        with open(base + ".json.part", "wb") as f:
            f.write(data)
        return JSONResponse({"ok": True})
    if not (0 <= part < total <= 16) or not data or len(data) > 50 * 1024 * 1024:
        return JSONResponse({"ok": False, "error": "Неверная часть"}, status_code=400)
    tmp = base + ".part"
    if part == 0 and os.path.exists(tmp):
        os.remove(tmp)
    if part > 0 and not os.path.exists(tmp):
        return JSONResponse({"ok": False, "error": "Начните с первой части"}, status_code=400)
    with open(tmp, "ab") as f:
        f.write(data)
    if part < total - 1:
        return JSONResponse({"ok": True, "done": False})
    with open(tmp, "rb") as f:
        head = f.read(2)
    if head[:1] != b"\x08" or not os.path.exists(base + ".json.part"):  # у файла ONNX первым идёт номер версии (байт 0x08)
        os.remove(tmp)
        return JSONResponse({"ok": False, "error": "Это не модель голоса или не пришли настройки"}, status_code=400)
    os.replace(base + ".json.part", base + ".json")
    os.replace(tmp, base)
    tts._loaded.clear()  # перечитать голос
    site.put(db, "tts_voice", "nuvora-custom")
    return JSONResponse({"ok": True, "done": True, "size": os.path.getsize(base)})
