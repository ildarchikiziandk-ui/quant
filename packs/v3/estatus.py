"""Статус у имени для Nuvora+ (6.11.2026, просьба владельца): вместо кружка Plus рядом с именем стоит выбранный
нарисованный стикер. 215 вариантов без подписей — мордочки 12 персонажей Nuvora с разными настроениями и предметы
в том же стиле. Картинки и список рисует `python3 tools/status_art.py` (static/estatus/<id>.webp и index.json).
Выбор — страница /plus/status (Nuvora+ → «Статус у имени»)."""
import json
import os

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from database import get_db
from deps import current_user, json_error, redirect, render
from services import social

from .common import router, s

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _build():
    try:
        with open(os.path.join(ROOT, "static", "estatus", "index.json"), encoding="utf-8") as f:
            idx = json.load(f)
    except OSError:
        idx = []
    groups = [{"title": g["title"], "items": [{"id": "s:" + k, "img": f"/static/estatus/{k}.webp", "title": n} for k, n in g["items"]]} for g in idx]
    return groups, {it["id"]: it["img"] for g in groups for it in g["items"]}


GROUPS, BY_ID = _build()


def img_of(user):
    """Картинка статуса у имени, если у человека Nuvora+ и статус выбран; иначе пусто."""
    code = getattr(user, "emoji_status", "") or ""
    return BY_ID.get(code, "") if code and social.is_plus(user) else ""


@router.get("/plus/status")
def status_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return redirect("/login?next=/plus/status")
    cur = user.emoji_status or ""  # старые значения (эмодзи текстом, прежние коды) просто не показываем
    return render(request, db, "packs/v3/estatus.html", sidebar=False, groups=GROUPS, total=len(BY_ID),
                  current=cur if cur in BY_ID else "", current_img=BY_ID.get(cur, ""), plus=social.is_plus(user))


@router.get("/plus/status.json")
def status_list(request: Request, db: Session = Depends(get_db)):
    """Для маленького окна выбора: нажать на свой значок у имени → выбрать стикер."""
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    cur = user.emoji_status or ""
    return {"ok": True, "plus": social.is_plus(user), "current": cur if cur in BY_ID else "",
            "groups": [{"title": g["title"], "items": [[it["id"], it["img"], it["title"]] for it in g["items"]]} for g in GROUPS]}


@router.post("/plus/status")
async def status_save(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    if not social.is_plus(user):
        return json_error("Статус у имени — для Nuvora+", 403)
    from routers.posts import read_payload
    code = s((await read_payload(request)).get("id"))[:40]
    if code and code not in BY_ID:
        return json_error("Такого статуса нет")
    user.emoji_status = code
    db.commit()
    return {"ok": True, "img": BY_ID.get(code, "")}
