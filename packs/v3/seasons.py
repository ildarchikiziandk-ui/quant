"""Праздники и сезоны Nuvora (решение владельца 5.11.2026):
- снег на сайте — с 15 ноября по конец февраля (можно выключить в настройках: «Внешний вид → Снег на сайте»);
- День матери — последнее воскресенье ноября: заставка и открытки для мамы (/den-materi), с субботы по понедельник;
- Новый год — с 15 декабря по 14 января: новогодний стиль, кит в колпаке, заставка с отсчётом и общая ёлка (/yolka),
  на которую каждый вешает свой шарик, нарисованный самим.
Владелец включает/выключает каждый праздник в админке → «Праздники» (/admin/seasons): «по календарю», «включить», «выключить».
Картинки: node tools/seasons/render.js (логотипы и фоны открыток → static/brand/season/)."""
import base64
import datetime as dt
import io
import os
import re
import textwrap
import time

from fastapi import Depends, Request
from fastapi.responses import Response
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session

import config
import models
from database import get_db
from deps import current_user, json_error, log_mod, redirect, render
from services.prefs import _p

from . import site
from .common import router, s
from .models import YolkaBall

KEYS = ("snow", "mom", "ny")
TITLES = {"snow": "Снег на сайте", "mom": "День матери", "ny": "Новый год и ёлка"}
CARDS = {"tulips": "Тюльпаны", "daisies": "Ромашки", "hearts": "Сердечки"}
FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "og_fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BALL_DIR = os.path.join(config.UPLOAD_DIR, "yolka")
PREFS = [_p("season_snow", "appearance", "Снег на сайте", "Зимой на экране падают снежинки", True, "bool", None, "client", "Праздники")]


def today():
    return (dt.datetime.utcnow() + dt.timedelta(hours=3)).date()  # по Москве


def mothers_day(year):
    """Последнее воскресенье ноября."""
    d = dt.date(year, 11, 30)
    return d - dt.timedelta(days=(d.weekday() + 1) % 7)


def by_calendar(key, d):
    if key == "snow":
        return (d.month == 11 and d.day >= 15) or d.month in (12, 1, 2)
    if key == "mom":
        return abs((d - mothers_day(d.year)).days) <= 1
    if key == "ny":
        return (d.month == 12 and d.day >= 15) or (d.month == 1 and d.day <= 14)
    return False


def mode(key):
    return (site.get("seasons") or {}).get(key, "auto")


def is_on(key, d=None):
    m = mode(key)
    return m == "on" or (m == "auto" and by_calendar(key, d or today()))


def ny_year(d=None):
    d = d or today()
    return d.year + 1 if d.month >= 7 else d.year


def state():
    """Что сейчас включено — для шаблонов (base.html)."""
    return {"snow": is_on("snow"), "mom": is_on("mom"), "ny": is_on("ny"), "ny_year": ny_year()}


GLOBALS = {"season_state": state}


def _can(user, key):
    return is_on(key) or bool(user and user.is_owner)  # владелец видит заранее, чтобы проверить


# ---------------------------------------------------------------- День матери: открытки
def _font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def _wrap(d, text, font, width):
    out = []
    for para in text.split("\n"):
        line = ""
        for w in para.split():
            t = (line + " " + w).strip()
            if d.textlength(t, font=font) <= width:
                line = t
            else:
                if line:
                    out.append(line)
                line = w
        out.append(line)
    return out


def mom_card(card, to, text, sign):
    card = card if card in CARDS else "tulips"
    im = Image.open(os.path.join(ROOT, "static", "brand", "season", f"mom-{card}.png")).convert("RGB")
    d = ImageDraw.Draw(im)
    ink, accent = (43, 37, 32), (181, 86, 47) if card == "tulips" else (95, 138, 79) if card == "daisies" else (196, 52, 78)
    title = (to or "Мамочка").strip()[:30] + ","
    d.text((540, 150), title, font=_font("unbounded-700.ttf", 58), fill=accent, anchor="mm")
    d.text((540, 240), "с Днём матери!", font=_font("unbounded-700.ttf", 62), fill=ink, anchor="mm")
    f = _font("onest-500.ttf", 38)
    lines = _wrap(d, (text or "").strip()[:300], f, 860)[:9]
    y = 340
    for ln in lines:
        d.text((540, y), ln, font=f, fill=ink, anchor="mm")
        y += 54
    if sign:
        d.text((540, y + 30), "— " + sign.strip()[:40], font=_font("onest-800.ttf", 38), fill=accent, anchor="mm")
    logo = Image.open(os.path.join(ROOT, "static", "brand", "season", "logo-mom.png")).convert("RGBA").resize((92, 92))
    im.paste(logo, (60, 60), logo)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


DEFAULT_TEXT = "Спасибо тебе за заботу, тепло и терпение. Ты самая лучшая! Люблю тебя ❤"


@router.get("/den-materi")
def mom_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not _can(user, "mom"):
        return redirect("/")
    return render(request, db, "packs/v3/mom_day.html", sidebar=False, cards=CARDS, default_text=DEFAULT_TEXT.replace(" ❤", ""),
                  sign=(user.name or user.username) if user else "", day=mothers_day(today().year))


@router.get("/den-materi/card.png")
def mom_card_png(request: Request, db: Session = Depends(get_db), c: str = "tulips", to: str = "", t: str = "", sg: str = "", dl: int = 0):
    user = current_user(request, db)
    if not _can(user, "mom"):
        return Response(status_code=404)
    from services.profanity import has_bad
    if any(has_bad(x) for x in (to, t, sg)):
        to, t, sg = "Мамочка", DEFAULT_TEXT.replace(" ❤", ""), ""
    headers = {"Cache-Control": "private, max-age=600"}
    if dl:
        headers["Content-Disposition"] = 'attachment; filename="den-materi.png"'
    return Response(mom_card(c, to, t.replace("❤", ""), sg), media_type="image/png", headers=headers)


# ---------------------------------------------------------------- Новый год: общая ёлка
def _slots(n=80):
    """Места для шариков на ёлке (в процентах от картинки 5:6). Зелёная часть — от 16% до 76% по высоте,
    полуширина растёт примерно от 6% до 31%. Порядок мест перемешан (одинаково всегда), чтобы первые шарики
    висели по всей ёлке, а не кучкой наверху."""
    out = []
    for r, y in enumerate(range(28, 75, 6)):
        half = 5 + (y - 20) * 0.47 - 5
        k = max(1, int(half * 2 / 9) + 1)
        for i in range(k):
            x = 50 - half + (2 * half) * (i + .5) / k + (2 if r % 2 else -2)
            out.append((round(x, 1), y + (2 if i % 2 else 0)))
    order = sorted(range(len(out)), key=lambda q: (q * 0.6180339887) % 1)
    return [out[q] for q in order][:n]


SLOTS = _slots()


@router.get("/yolka")
def yolka(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not _can(user, "ny"):
        return redirect("/")
    balls = db.query(YolkaBall).filter_by(hidden=False).order_by(YolkaBall.created_at.asc()).all()
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_([b.user_id for b in balls] or [0]))}
    items = [{"b": b, "u": users.get(b.user_id)} for b in balls if users.get(b.user_id)]
    mine = db.query(YolkaBall).filter_by(user_id=user.id).first() if user else None
    return render(request, db, "packs/v3/yolka.html", sidebar=False, items=items, slots=SLOTS, mine=mine, year=ny_year(),
                  can_mod=bool(user and (user.is_owner or user.is_moderator)))


@router.post("/yolka/ball")
async def yolka_ball(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("Войдите, чтобы повесить шарик", 401)
    if not _can(user, "ny"):
        return json_error("Ёлка откроется 15 декабря", 403)
    from routers.posts import read_payload
    data = await read_payload(request)
    m = re.match(r"^data:image/png;base64,([A-Za-z0-9+/=]+)$", s(data.get("png")))
    if not m or len(m.group(1)) > 700_000:
        return json_error("Не получилось сохранить рисунок")
    try:
        im = Image.open(io.BytesIO(base64.b64decode(m.group(1))))
        im.load()
        im = im.convert("RGBA").resize((200, 200), Image.LANCZOS)
    except Exception:
        return json_error("Не получилось прочитать рисунок")
    if im.getchannel("A").getextrema()[1] < 20:
        return json_error("Шарик пустой — нарисуйте что-нибудь")
    mask = Image.new("L", (200, 200), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, 199, 199), fill=255)
    out = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    os.makedirs(BALL_DIR, exist_ok=True)
    name = f"{user.id}_{int(time.time())}.png"
    out.save(os.path.join(BALL_DIR, name), optimize=True)
    ball = db.query(YolkaBall).filter_by(user_id=user.id).first()
    if ball and ball.image:
        old = os.path.join(config.UPLOAD_DIR, ball.image.split("/uploads/", 1)[-1])
        if os.path.dirname(os.path.abspath(old)) == os.path.abspath(BALL_DIR) and os.path.exists(old):
            os.remove(old)
    if not ball:
        ball = YolkaBall(user_id=user.id)
        db.add(ball)
    ball.image, ball.year, ball.hidden, ball.created_at = f"/uploads/yolka/{name}", ny_year(), False, ball.created_at or dt.datetime.utcnow()
    db.commit()
    return {"ok": True, "image": ball.image}


@router.post("/yolka/ball/{ball_id}/hide")
async def yolka_hide(ball_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user or not (user.is_owner or user.is_moderator):
        return json_error("Только для модераторов", 403)
    ball = db.get(YolkaBall, ball_id)
    if not ball:
        return json_error("Нет такого шарика", 404)
    ball.hidden = True
    log_mod(db, user, "yolka_hide", str(ball.user_id), "")
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- админка
@router.get("/admin/seasons")
def seasons_admin(request: Request, db: Session = Depends(get_db), ok: int = 0):
    user = current_user(request, db)
    if not user or not user.is_owner:
        return redirect("/")
    d = today()
    rows = [{"key": k, "title": TITLES[k], "mode": mode(k), "on": is_on(k), "cal": by_calendar(k, d)} for k in KEYS]
    return render(request, db, "packs/v3/admin_seasons.html", sidebar=False, rows=rows, ok=ok, mom_day=mothers_day(d.year if d.month <= 11 else d.year + 1),
                  balls=db.query(YolkaBall).count())


@router.post("/admin/seasons")
async def seasons_save(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user or not user.is_owner:
        return redirect("/")
    f = await request.form()
    val = {k: (s(f.get(k)) if s(f.get(k)) in ("auto", "on", "off") else "auto") for k in KEYS}
    site.put(db, "seasons", val)
    log_mod(db, user, "seasons", ", ".join(f"{k}={v}" for k, v in val.items()), "")
    db.commit()
    return redirect("/admin/seasons?ok=1")
