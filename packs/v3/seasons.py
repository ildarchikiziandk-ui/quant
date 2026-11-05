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
# 100 мест для шариков (в процентах от картинки 600×1000): случайный, но всегда одинаковый разброс внутри ярусов ёлки,
# шарики не налезают друг на друга; порядок перемешан — первые шарики висят по всей ёлке.
SLOTS = [(46.1, 15.8), (40.7, 42.2), (33.0, 35.2), (56.8, 74.5), (62.0, 81.9), (51.4, 58.7), (38.0, 25.3), (59.4, 18.6), (88.5, 81.8), (40.6, 76.7), (60.7, 37.4), (15.3, 69.6), (50.1, 80.1), (45.4, 23.7), (74.9, 76.7), (25.3, 75.5), (71.6, 67.3), (44.3, 83.0), (65.3, 74.0), (35.8, 53.7), (59.6, 59.2), (33.7, 75.5), (80.3, 55.8), (49.7, 39.7), (25.5, 65.7), (42.5, 28.3), (63.0, 48.2), (10.2, 72.5), (74.2, 72.4), (67.1, 78.8), (72.9, 57.1), (20.0, 54.4), (16.1, 80.5), (70.4, 48.2), (57.4, 41.4), (46.4, 49.1), (73.0, 81.0), (32.8, 67.7), (53.0, 25.7), (62.7, 55.6), (70.8, 52.4), (42.5, 52.8), (39.5, 20.3), (56.8, 66.3), (36.1, 59.2), (53.4, 16.2), (57.3, 70.3), (66.5, 24.5), (66.0, 33.6), (46.6, 66.4), (29.6, 49.0), (39.3, 63.3), (73.0, 41.3), (63.7, 43.3), (59.5, 31.8), (67.8, 38.5), (49.3, 54.2), (54.5, 35.8), (25.6, 81.2), (78.2, 66.7), (82.3, 79.0), (64.0, 65.4), (87.1, 72.5), (38.7, 80.6), (19.2, 73.1), (37.3, 32.0), (80.5, 83.1), (46.6, 62.3), (57.2, 78.5), (56.7, 45.6), (38.6, 37.7), (31.7, 63.4), (39.7, 71.3), (57.9, 51.5), (27.2, 53.1), (50.2, 20.5), (64.0, 69.4), (32.6, 82.3), (50.3, 12.1), (50.1, 70.8), (66.4, 61.4), (80.7, 71.2), (56.0, 55.7), (38.6, 47.7), (44.5, 35.8), (55.1, 62.3), (15.7, 57.5), (8.9, 81.7), (27.1, 71.6), (26.0, 57.7), (34.6, 44.5), (54.9, 83.1), (43.8, 56.8), (58.8, 22.9), (49.5, 45.3), (31.1, 39.2), (52.5, 31.6), (73.5, 63.3), (48.8, 75.4), (23.2, 42.0)]
TREE_SVG = '<svg class="tree" viewBox="0 0 600 1000" aria-hidden="true"><defs><radialGradient id="glow" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#fff6c8" stop-opacity=".9"/><stop offset="1" stop-color="#fff6c8" stop-opacity="0"/></radialGradient></defs><rect width="600" height="1000" rx="36" fill="#1d3557"/><circle cx="198" cy="149" r="1.5" fill="#fff" opacity="0.39"/><circle cx="321" cy="346" r="1.5" fill="#fff" opacity="0.80"/><circle cx="135" cy="89" r="3" fill="#fff" opacity="0.38"/><circle cx="63" cy="401" r="1.5" fill="#fff" opacity="0.82"/><circle cx="376" cy="546" r="1.5" fill="#fff" opacity="0.64"/><circle cx="240" cy="908" r="1.5" fill="#fff" opacity="0.63"/><circle cx="87" cy="396" r="1.5" fill="#fff" opacity="0.64"/><circle cx="335" cy="637" r="1.5" fill="#fff" opacity="0.64"/><circle cx="381" cy="353" r="1.5" fill="#fff" opacity="0.63"/><circle cx="369" cy="467" r="3" fill="#fff" opacity="0.74"/><circle cx="280" cy="860" r="2.5" fill="#fff" opacity="0.50"/><circle cx="471" cy="653" r="2" fill="#fff" opacity="0.39"/><circle cx="184" cy="466" r="2.5" fill="#fff" opacity="0.71"/><circle cx="177" cy="912" r="1.5" fill="#fff" opacity="0.61"/><circle cx="106" cy="325" r="3" fill="#fff" opacity="0.56"/><circle cx="568" cy="81" r="2.5" fill="#fff" opacity="0.52"/><circle cx="213" cy="467" r="3" fill="#fff" opacity="0.38"/><circle cx="64" cy="258" r="1.5" fill="#fff" opacity="0.38"/><circle cx="417" cy="605" r="3" fill="#fff" opacity="0.49"/><circle cx="234" cy="625" r="1.5" fill="#fff" opacity="0.82"/><circle cx="216" cy="572" r="3" fill="#fff" opacity="0.38"/><circle cx="456" cy="129" r="2" fill="#fff" opacity="0.55"/><circle cx="542" cy="467" r="2" fill="#fff" opacity="0.57"/><circle cx="329" cy="823" r="3" fill="#fff" opacity="0.78"/><circle cx="171" cy="392" r="2.5" fill="#fff" opacity="0.69"/><circle cx="231" cy="222" r="1.5" fill="#fff" opacity="0.44"/><circle cx="145" cy="225" r="3" fill="#fff" opacity="0.77"/><circle cx="116" cy="269" r="2" fill="#fff" opacity="0.56"/><circle cx="224" cy="531" r="2" fill="#fff" opacity="0.70"/><circle cx="309" cy="578" r="1.5" fill="#fff" opacity="0.58"/><circle cx="515" cy="886" r="3" fill="#fff" opacity="0.55"/><circle cx="239" cy="453" r="3" fill="#fff" opacity="0.38"/><circle cx="49" cy="202" r="2" fill="#fff" opacity="0.40"/><circle cx="358" cy="104" r="2" fill="#fff" opacity="0.62"/><circle cx="560" cy="575" r="1.5" fill="#fff" opacity="0.79"/><circle cx="366" cy="147" r="2.5" fill="#fff" opacity="0.83"/><circle cx="359" cy="446" r="1.5" fill="#fff" opacity="0.77"/><circle cx="586" cy="439" r="3" fill="#fff" opacity="0.51"/><circle cx="94" cy="700" r="2.5" fill="#fff" opacity="0.59"/><circle cx="411" cy="485" r="2" fill="#fff" opacity="0.83"/><circle cx="316" cy="145" r="1.5" fill="#fff" opacity="0.73"/><circle cx="183" cy="601" r="1.5" fill="#fff" opacity="0.70"/><circle cx="161" cy="347" r="2" fill="#fff" opacity="0.53"/><circle cx="139" cy="508" r="2.5" fill="#fff" opacity="0.67"/><circle cx="366" cy="735" r="2" fill="#fff" opacity="0.75"/><circle cx="485" cy="691" r="2" fill="#fff" opacity="0.45"/><circle cx="296" cy="683" r="1.5" fill="#fff" opacity="0.75"/><circle cx="284" cy="188" r="2.5" fill="#fff" opacity="0.57"/><circle cx="553" cy="919" r="2.5" fill="#fff" opacity="0.39"/><circle cx="69" cy="442" r="2.5" fill="#fff" opacity="0.45"/><circle cx="372" cy="838" r="1.5" fill="#fff" opacity="0.59"/><circle cx="389" cy="746" r="1.5" fill="#fff" opacity="0.77"/><circle cx="80" cy="367" r="2" fill="#fff" opacity="0.59"/><circle cx="114" cy="736" r="2.5" fill="#fff" opacity="0.39"/><circle cx="559" cy="674" r="3" fill="#fff" opacity="0.55"/><circle cx="559" cy="677" r="2" fill="#fff" opacity="0.85"/><circle cx="26" cy="554" r="3" fill="#fff" opacity="0.75"/><circle cx="95" cy="770" r="3" fill="#fff" opacity="0.68"/><circle cx="213" cy="515" r="2" fill="#fff" opacity="0.36"/><circle cx="474" cy="678" r="1.5" fill="#fff" opacity="0.61"/><circle cx="552" cy="409" r="2" fill="#fff" opacity="0.76"/><circle cx="132" cy="242" r="2.5" fill="#fff" opacity="0.60"/><circle cx="453" cy="310" r="3" fill="#fff" opacity="0.77"/><circle cx="45" cy="691" r="3" fill="#fff" opacity="0.68"/><circle cx="483" cy="485" r="2" fill="#fff" opacity="0.62"/><circle cx="314" cy="27" r="3" fill="#fff" opacity="0.74"/><circle cx="363" cy="724" r="2" fill="#fff" opacity="0.44"/><circle cx="285" cy="677" r="1.5" fill="#fff" opacity="0.51"/><circle cx="311" cy="521" r="1.5" fill="#fff" opacity="0.79"/><circle cx="43" cy="186" r="1.5" fill="#fff" opacity="0.74"/><path d="M0 880 Q150 855 300 868 T600 875 V1000 H0Z" fill="#eef3f8"/><path d="M0 930 Q200 912 380 926 T600 920 V1000 H0Z" fill="#dfe8f1"/><rect x="268" y="830" width="64" height="62" rx="8" fill="#6b3f24"/><rect x="268" y="830" width="30" height="62" rx="8" fill="#7d4c2d"/><path d="M300 580 L600 840 Q557 866 514 840 Q471 866 429 840 Q386 866 343 840 Q300 866 257 840 Q214 866 171 840 Q129 866 86 840 Q43 866 0 840 Z" fill="#2f7a4a"/><path d="M300 580 L0 840 Q43 866 86 840 Q129 866 171 840 Q214 866 257 840 L300 860Z" fill="#3a8f58"/><path d="M0 840 Q43 866 86 840" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M86 840 Q129 866 171 840" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M171 840 Q214 866 257 840" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M257 840 Q300 866 343 840" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M343 840 Q386 866 429 840" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M429 840 Q471 866 514 840" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M514 840 Q557 866 600 840" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M122 718 Q300 776 478 706" fill="none" stroke="#f0c24a" stroke-width="4" stroke-dasharray="1 11" stroke-linecap="round"/><path d="M300 450 L578 740 Q538 766 499 740 Q459 766 419 740 Q379 766 340 740 Q300 766 260 740 Q221 766 181 740 Q141 766 101 740 Q62 766 22 740 Z" fill="#2f7a4a"/><path d="M300 450 L22 740 Q62 766 101 740 Q141 766 181 740 Q221 766 260 740 L300 760Z" fill="#3a8f58"/><path d="M22 740 Q62 766 101 740" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M101 740 Q141 766 181 740" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M181 740 Q221 766 260 740" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M260 740 Q300 766 340 740" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M340 740 Q379 766 419 740" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M419 740 Q459 766 499 740" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M499 740 Q538 766 578 740" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M134 605 Q300 663 466 593" fill="none" stroke="#f0c24a" stroke-width="4" stroke-dasharray="1 11" stroke-linecap="round"/><path d="M300 315 L545 590 Q510 616 475 590 Q440 616 405 590 Q370 616 335 590 Q300 616 265 590 Q230 616 195 590 Q160 616 125 590 Q90 616 55 590 Z" fill="#2f7a4a"/><path d="M300 315 L55 590 Q90 616 125 590 Q160 616 195 590 Q230 616 265 590 L300 610Z" fill="#3a8f58"/><path d="M55 590 Q90 616 125 590" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M125 590 Q160 616 195 590" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M195 590 Q230 616 265 590" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M265 590 Q300 616 335 590" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M335 590 Q370 616 405 590" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M405 590 Q440 616 475 590" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M475 590 Q510 616 545 590" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M152 462 Q300 520 448 450" fill="none" stroke="#f0c24a" stroke-width="4" stroke-dasharray="1 11" stroke-linecap="round"/><path d="M300 185 L500 430 Q471 456 443 430 Q414 456 386 430 Q357 456 329 430 Q300 456 271 430 Q243 456 214 430 Q186 456 157 430 Q129 456 100 430 Z" fill="#2f7a4a"/><path d="M300 185 L100 430 Q129 456 157 430 Q186 456 214 430 Q243 456 271 430 L300 450Z" fill="#3a8f58"/><path d="M100 430 Q129 456 157 430" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M157 430 Q186 456 214 430" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M214 430 Q243 456 271 430" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M271 430 Q300 456 329 430" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M329 430 Q357 456 386 430" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M386 430 Q414 456 443 430" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M443 430 Q471 456 500 430" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M176 315 Q300 373 424 303" fill="none" stroke="#f0c24a" stroke-width="4" stroke-dasharray="1 11" stroke-linecap="round"/><path d="M300 75 L440 270 Q420 296 400 270 Q380 296 360 270 Q340 296 320 270 Q300 296 280 270 Q260 296 240 270 Q220 296 200 270 Q180 296 160 270 Z" fill="#2f7a4a"/><path d="M300 75 L160 270 Q180 296 200 270 Q220 296 240 270 Q260 296 280 270 L300 290Z" fill="#3a8f58"/><path d="M160 270 Q180 296 200 270" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M200 270 Q220 296 240 270" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M240 270 Q260 296 280 270" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M280 270 Q300 296 320 270" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M320 270 Q340 296 360 270" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M360 270 Q380 296 400 270" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M400 270 Q420 296 440 270" fill="none" stroke="#f4f8fc" stroke-width="9" stroke-linecap="round"/><path d="M210 178 Q300 236 390 166" fill="none" stroke="#f0c24a" stroke-width="4" stroke-dasharray="1 11" stroke-linecap="round"/><circle cx="300" cy="62" r="70" fill="url(#glow)"/><polygon points="300.0,24.0 310.0,50.2 338.0,51.6 316.2,69.3 323.5,96.4 300.0,81.0 276.5,96.4 283.8,69.3 262.0,51.6 290.0,50.2" fill="#f6cd4c" stroke="#d99a16" stroke-width="4" stroke-linejoin="round"/><rect x="120" y="905" width="76" height="60" rx="6" fill="#c8281e"/><rect x="153.0" y="905" width="10" height="60" fill="#f0c24a"/><rect x="120" y="917" width="76" height="9" fill="#f0c24a"/><path d="M158.0 905 q-18 -20 -22 -4 q8 8 22 4 q18 -20 22 -4 q-8 8 -22 4" fill="#f0c24a"/><rect x="370" y="899" width="90" height="66" rx="6" fill="#1d5fa5"/><rect x="410.0" y="899" width="10" height="66" fill="#f6f1e8"/><rect x="370" y="911" width="90" height="9" fill="#f6f1e8"/><path d="M415.0 899 q-18 -20 -22 -4 q8 8 22 4 q18 -20 22 -4 q-8 8 -22 4" fill="#f6f1e8"/><rect x="470" y="919" width="60" height="46" rx="6" fill="#f0c24a"/><rect x="495.0" y="919" width="10" height="46" fill="#c8281e"/><rect x="470" y="931" width="60" height="9" fill="#c8281e"/><path d="M500.0 919 q-18 -20 -22 -4 q8 8 22 4 q18 -20 22 -4 q-8 8 -22 4" fill="#c8281e"/><rect x="205" y="925" width="54" height="40" rx="6" fill="#8a6aa0"/><rect x="227.0" y="925" width="10" height="40" fill="#f6f1e8"/><rect x="205" y="937" width="54" height="9" fill="#f6f1e8"/><path d="M232.0 925 q-18 -20 -22 -4 q8 8 22 4 q18 -20 22 -4 q-8 8 -22 4" fill="#f6f1e8"/></svg>'


@router.get("/yolka")
def yolka(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not _can(user, "ny"):
        return redirect("/")
    balls = db.query(YolkaBall).filter_by(hidden=False).order_by(YolkaBall.created_at.asc()).all()
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_([b.user_id for b in balls] or [0]))}
    items = [{"b": b, "u": users.get(b.user_id)} for b in balls if users.get(b.user_id)]
    mine = db.query(YolkaBall).filter_by(user_id=user.id).first() if user else None
    return render(request, db, "packs/v3/yolka.html", sidebar=False, items=items, slots=SLOTS, tree_svg=TREE_SVG, mine=mine, year=ny_year(),
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
