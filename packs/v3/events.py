"""Ивенты Nuvora (8.11.2026, список выбрал владелец).

Каждую неделю: двойные искры по субботам и воскресеньям (и весь день 1 июня).
По календарю (по Москве):
  15–17 ноября   Первый снег — поймай 10 золотых снежинок → 30 искр
  1–31 декабря   Адвент-календарь /advent — каждый день окошко с подарком, 31-го — 3 дня Nuvora+
  31 дек – 1 янв Новогодняя ночь — отсчёт, салют, 1 января подарок: 3 дня Nuvora+ и 50 искр
  13–14 февраля  День святого Валентина /valentine — валентинки друзьям, можно анонимно
  17–23 февраля  Турнир к 23 февраля /turnir — победы в играх в чате, тройке лучших владелец дарит неделю Nuvora+
  Масленица      /maslenitsa — каждый день недели блин за выполненное задание, 7 блинов → неделя Nuvora+
  7–8 марта      Открытки к 8 Марта /8-marta
  1 апреля       День смеха /1-aprelya — лайки-рыбки, кит плавает по экрану, самые смешные посты #первоеапреля
  24 апреля      День рождения Nuvora — торт, 100 искр и день Nuvora+
  9 мая          День Победы — только поздравление (решение владельца: без шуток и наград)
  1 июня         Начало лета — 50 искр и двойные искры весь день
  12 июня        День России — поздравление и 30 искр
  31 августа     Проводы лета — #моёлето и 50 искр
  день рождения создателя — дату вписывает владелец в админке (в коде её нет: репозиторий публичный)
Включить/выключить каждый — админка → «Ивенты» (/admin/events): по календарю / включить / выключить.
Владелец видит все страницы заранее."""
import datetime as dt
import io
import os
import random
import re

from fastapi import Depends, Request
from fastapi.responses import JSONResponse, Response
from PIL import Image, ImageDraw
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import current_user, json_error, log_mod, login_redirect, redirect, render
from services import gamification, ratelimit, social

from . import site
from .common import router, s
from .models import ChatGame, EventClaim, TttGame, Valentine
from .seasons import ROOT, _font, _wrap

ADV = {7: "plus1", 14: "plus1", 21: "plus1", 24: 60, 31: "plus3"}  # особые окошки адвента

INFO = {
    "x2": ("Двойные искры", "⚡", "Каждые выходные", "За задания и активность в субботу и воскресенье — в 2 раза больше искр", "/tasks"),
    "snow1": ("Первый снег", "❄️", "15–17 ноября", "По экрану летят золотые снежинки — поймай 10 и получи 30 искр", "/prazdniki"),
    "advent": ("Адвент-календарь", "🎄", "1–31 декабря", "Каждый день открывается окошко с подарком, 31 декабря — 3 дня Nuvora+", "/advent"),
    "nynight": ("Новогодняя ночь", "🎆", "31 декабря – 1 января", "Отсчёт до полуночи, салют на весь экран и подарок под ёлкой: 3 дня Nuvora+", "/prazdniki"),
    "valentine": ("День святого Валентина", "💌", "13–14 февраля", "Валентинки друзьям — можно анонимно, от «тайного поклонника»", "/valentine"),
    "feb23": ("Турнир к 23 февраля", "🛡️", "17–23 февраля", "Побеждай в играх в чате: тройка лучших получает неделю Nuvora+", "/turnir"),
    "maslenitsa": ("Масленица", "🥞", "неделя перед Великим постом", "Каждый день — блин за выполненное задание. 7 блинов = неделя Nuvora+", "/maslenitsa"),
    "mar8": ("8 Марта", "🌷", "7–8 марта", "Открытки с цветами для мам, сестёр и подруг", "/8-marta"),
    "apr1": ("День смеха", "🐟", "1 апреля", "Лайки превращаются в рыбок, по экрану плавает кит. Самые смешные посты #первоеапреля", "/1-aprelya"),
    "bday": ("День рождения Nuvora", "🎂", "24 апреля", "Торт, конфетти и подарок всем: 100 искр и день Nuvora+", "/prazdniki"),
    "may9": ("День Победы", "🎗️", "9 мая", "Помним и гордимся. С Днём Победы!", "/prazdniki"),
    "summer1": ("Ура, лето!", "☀️", "1 июня", "Первый день лета: 50 искр и двойные искры весь день", "/prazdniki"),
    "jun12": ("День России", "🇷🇺", "12 июня", "С Днём России! Подарок — 30 искр", "/prazdniki"),
    "summer_end": ("Проводы лета", "🌅", "31 августа", "Делитесь летними фото с #моёлето — и заберите 50 искр", "/prazdniki"),
    "owner_bday": ("День рождения создателя", "🥳", "дату задаёт владелец", "Поздравьте создателя Nuvora — и получите кусочек торта: 50 искр", "/prazdniki"),
}
KEYS = list(INFO)
# подарок «забрать» на странице ивентов: (искры, дней Nuvora+)
GIFTS = {"nynight": (50, 3), "bday": (100, 1), "summer1": (50, 0), "jun12": (30, 0), "summer_end": (50, 0), "owner_bday": (50, 0), "snow1": (30, 0)}
SPLASH = {"valentine", "mar8", "apr1", "bday", "may9", "summer1", "jun12", "summer_end", "owner_bday", "snow1", "nynight"}


def now_msk():
    return dt.datetime.utcnow() + dt.timedelta(hours=3)


def today():
    return now_msk().date()


def easter(y):
    """Православная Пасха (по григорианскому календарю, 1900–2099)."""
    a, b, c = y % 4, y % 7, y % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    m, day = divmod(d + e + 114, 31)
    return dt.date(y, m, day + 1) + dt.timedelta(days=13)


def owner_bday(y):
    m = re.match(r"^(\d{1,2})-(\d{1,2})$", str(site.get("owner_bday") or ""))
    if not m:
        return None
    try:
        return dt.date(y, int(m.group(1)), int(m.group(2)))
    except ValueError:
        return None


def span(key, y):
    """(начало, конец) ивента в году y — или None."""
    D = dt.date
    if key == "snow1":
        return D(y, 11, 15), D(y, 11, 17)
    if key == "advent":
        return D(y, 12, 1), D(y, 12, 31)
    if key == "nynight":
        return D(y, 12, 31), D(y + 1, 1, 1)
    if key == "valentine":
        return D(y, 2, 13), D(y, 2, 14)
    if key == "feb23":
        return D(y, 2, 17), D(y, 2, 23)
    if key == "maslenitsa":
        e = easter(y)
        return e - dt.timedelta(days=55), e - dt.timedelta(days=49)
    if key == "mar8":
        return D(y, 3, 7), D(y, 3, 8)
    one = {"apr1": (4, 1), "bday": (4, 24), "may9": (5, 9), "summer1": (6, 1), "jun12": (6, 12), "summer_end": (8, 31)}
    if key in one:
        d = D(y, *one[key])
        return d, d
    if key == "owner_bday":
        d = owner_bday(y)
        return (d, d) if d else None
    return None


def by_calendar(key, d):
    if key == "x2":
        return d.weekday() >= 5 or (d.month, d.day) == (6, 1)
    for y in (d.year - 1, d.year):
        sp = span(key, y)
        if sp and sp[0] <= d <= sp[1]:
            return True
    return False


def next_span(key, d=None):
    d = d or today()
    for y in (d.year - 1, d.year, d.year + 1):
        sp = span(key, y)
        if sp and sp[1] >= d:
            return sp
    return None


def cur_span(key, d=None):
    """Последний начавшийся (или идущий) раз ивента — для итогов турнира и Масленицы."""
    d = d or today()
    for y in (d.year, d.year - 1):
        sp = span(key, y)
        if sp and sp[0] <= d:
            return sp
    return next_span(key, d)


def mode(key):
    return (site.get("events") or {}).get(key, "auto")


def is_on(key, d=None):
    m = mode(key)
    return m == "on" or (m == "auto" and by_calendar(key, d or today()))


def can(user, key):
    return is_on(key) or bool(user and user.is_owner)  # владелец видит заранее


def double_now():
    if os.environ.get("EVENTS_X2") == "0":
        return False
    try:
        return is_on("x2")
    except Exception:  # noqa: BLE001
        return False


def active():
    return [k for k in KEYS if is_on(k)]


def year_tag(key, d=None):
    d = d or today()
    sp = next_span(key, d) if key != "x2" else None
    return str(sp[0].year if sp else d.year)


def claimed(db, user, key, tag):
    return bool(user and db.query(EventClaim.id).filter_by(user_id=user.id, key=key, tag=tag).first())


def claim(db, user, key, tag):
    """Отметить «получено» — один раз. False, если уже было."""
    if claimed(db, user, key, tag):
        return False
    db.add(EventClaim(user_id=user.id, key=key, tag=tag))
    try:
        db.flush()
    except Exception:  # noqa: BLE001  гонка двух нажатий — уникальный индекс не даст второй раз
        db.rollback()
        return False
    return True


def reward(db, user, sparks=0, plus_days=0, text=""):
    if sparks:
        user.total_points = (user.total_points or 0) + sparks  # подарок — ровно столько, без умножений
        user.level = gamification.level_for(user.total_points)
    if plus_days:
        gamification.grant_plus(user, plus_days)
    if text:
        db.add(models.Notification(user_id=user.id, type="holiday", text=text))


def gift_text(sparks, days):
    parts = []
    if days:
        parts.append(f"{days} {'день' if days == 1 else 'дня' if days < 5 else 'дней'} Nuvora+")
    if sparks:
        parts.append(f"{sparks} искр")
    return " и ".join(parts)


def state(user=None):
    """Для base.html: какие ивенты идут, что показать."""
    act = active()
    return {"on": act, "splash": [k for k in act if k in SPLASH], "info": INFO, "x2": "x2" in act}


GLOBALS = {"events_state": state}


# ---------------------------------------------------------------- страница всех ивентов
@router.get("/prazdniki")
def events_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    d = today()
    rows = []
    for k in KEYS:
        sp = next_span(k, d) if k != "x2" else None
        if k == "owner_bday" and not sp:
            continue
        g = GIFTS.get(k)
        rows.append({"key": k, "title": INFO[k][0], "emo": INFO[k][1], "when": INFO[k][2] if k not in ("owner_bday", "maslenitsa") or not sp else
                     f"{sp[0].day} {MONTHS[sp[0].month]}" + (f" – {sp[1].day} {MONTHS[sp[1].month]}" if sp[1] != sp[0] else ""),
                     "what": INFO[k][3], "link": INFO[k][4], "on": is_on(k), "start": sp[0] if sp else d,
                     "gift": g and gift_text(*g), "got": bool(g and user and claimed(db, user, k, year_tag(k)))})
    rows.sort(key=lambda r: (not r["on"], r["key"] != "x2", r["start"]))
    return render(request, db, "packs/v3/events.html", rows=rows, now=d)


MONTHS = ["", "января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]


@router.post("/prazdniki/{key}/gift")
def events_gift(key: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("Войдите, чтобы забрать подарок", 401)
    if key not in GIFTS or not is_on(key):
        return json_error("Сейчас этого подарка нет", 403)
    if key == "nynight" and not (today().month == 1):
        return json_error("Подарок откроется в полночь 🎆", 403)
    if not claim(db, user, key, year_tag(key)):
        return json_error("Вы уже забрали этот подарок")
    sp, days = GIFTS[key]
    reward(db, user, sp, days, f"{INFO[key][1]} {INFO[key][0]}: подарок — {gift_text(sp, days)}")
    db.commit()
    return {"ok": True, "text": f"Получено: {gift_text(sp, days)}"}


# ---------------------------------------------------------------- адвент-календарь
def advent_prize(day):
    p = ADV.get(day)
    if p == "plus1":
        return 0, 1
    if p == "plus3":
        return 0, 3
    if isinstance(p, int):
        return p, 0
    return 10 + (day * 7) % 4 * 5, 0  # 10–25 искр


@router.get("/advent")
def advent(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not can(user, "advent"):
        return redirect("/prazdniki")
    d = today()
    y = d.year if d.month == 12 else (d.year - 1 if d.month == 1 else d.year)
    cur = d.day if (d.month == 12 and is_on("advent")) else 0
    got = {int(c.tag[-2:]) for c in db.query(EventClaim).filter(EventClaim.user_id == user.id, EventClaim.key == "advent",
                                                               EventClaim.tag.like(f"{y}-%"))} if user else set()
    order = list(range(1, 32))
    random.Random(y).shuffle(order)  # окошки вразнобой, как в настоящем календаре
    days = [{"n": n, "got": n in got, "today": n == cur, "past": cur and n < cur, "prize": gift_text(*advent_prize(n))} for n in order]
    return render(request, db, "packs/v3/advent.html", days=days, cur=cur, y=y)


@router.post("/advent/open")
def advent_open(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("Войдите, чтобы открыть окошко", 401)
    d = today()
    if not is_on("advent") or d.month != 12:
        return json_error("Календарь откроется 1 декабря", 403)
    if not claim(db, user, "advent", f"{d.year}-{d.day:02d}"):
        return json_error("Сегодняшнее окошко уже открыто — приходите завтра!")
    sp, days = advent_prize(d.day)
    reward(db, user, sp, days)
    db.commit()
    return {"ok": True, "day": d.day, "text": gift_text(sp, days)}


# ---------------------------------------------------------------- Масленица
@router.get("/maslenitsa")
def maslenitsa(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not can(user, "maslenitsa"):
        return redirect("/prazdniki")
    a, b = next_span("maslenitsa")
    got = db.query(EventClaim).filter(EventClaim.user_id == user.id, EventClaim.key == "maslenitsa", EventClaim.tag.like(f"{a.year}-d%")).count() if user else 0
    names = ["Встреча", "Заигрыш", "Лакомка", "Разгуляй", "Тёщины вечорки", "Золовкины посиделки", "Прощёное воскресенье"]
    idx = (today() - a).days if a <= today() <= b else -1
    return render(request, db, "packs/v3/maslenitsa.html", start=a, end=b, got=got, names=names, idx=idx,
                  today_done=bool(user and idx >= 0 and claimed(db, user, "maslenitsa", f"{a.year}-d{idx}")), months=MONTHS)


def _did_task_today(db, user):
    return bool(db.query(models.UserDailyTask.id).filter_by(user_id=user.id, date=dt.date.today().isoformat(), is_completed=True).first())


@router.post("/maslenitsa/blin")
def maslenitsa_blin(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("Войдите", 401)
    if not is_on("maslenitsa"):
        return json_error("Масленица ещё не началась", 403)
    a, b = next_span("maslenitsa")
    idx = (today() - a).days
    if not 0 <= idx <= 6:
        return json_error("Масленица ещё не началась", 403)
    if not _did_task_today(db, user):
        return json_error("Сначала выполните любое задание дня — и блин ваш 🥞")
    if not claim(db, user, "maslenitsa", f"{a.year}-d{idx}"):
        return json_error("Сегодняшний блин уже ваш — приходите завтра!")
    n = db.query(EventClaim).filter(EventClaim.user_id == user.id, EventClaim.key == "maslenitsa", EventClaim.tag.like(f"{a.year}-d%")).count()
    text = f"Блин №{n}!"
    if n >= 7 and claim(db, user, "maslenitsa", f"{a.year}-full"):
        reward(db, user, 0, 7, "🥞 Масленица: вы собрали все 7 блинов — неделя Nuvora+ в подарок!")
        text = "Все 7 блинов! Неделя Nuvora+ — ваша 🎉"
    db.commit()
    return {"ok": True, "n": n, "text": text}


# ---------------------------------------------------------------- турнир к 23 февраля
def leaderboard(db, a, b, limit=20):
    start = dt.datetime.combine(a, dt.time()) - dt.timedelta(hours=3)
    end = dt.datetime.combine(b + dt.timedelta(days=1), dt.time()) - dt.timedelta(hours=3)
    wins = {}
    for M, when in ((ChatGame, ChatGame.created_at), (TttGame, TttGame.updated_at)):
        q = db.query(M.winner, func.count(M.id)).filter(M.winner > 0, when >= start, when < end).group_by(M.winner)
        for uid, n in q:
            wins[uid] = wins.get(uid, 0) + n
    top = sorted(wins.items(), key=lambda x: -x[1])[:limit]
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_([t[0] for t in top] or [0]))}
    return [{"u": users[uid], "n": n} for uid, n in top if uid in users]


@router.get("/turnir")
def turnir(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not can(user, "feb23"):
        return redirect("/prazdniki")
    a, b = cur_span("feb23") if is_on("feb23") or today().month <= 3 else next_span("feb23")
    rows = leaderboard(db, a, b)
    awarded = {c.user_id for c in db.query(EventClaim).filter_by(key="feb23", tag=f"{a.year}-prize")}
    return render(request, db, "packs/v3/turnir.html", rows=rows, start=a, end=b, awarded=awarded, months=MONTHS,
                  finished=today() > b, owner=bool(user and user.is_owner))


@router.post("/turnir/award/{uid}")
def turnir_award(uid: int, request: Request, db: Session = Depends(get_db)):
    me = current_user(request, db)
    if not me or not me.is_owner:
        return json_error("forbidden", 403)
    a, b = cur_span("feb23")
    u = db.get(models.User, uid)
    if not u or not claim(db, u, "feb23", f"{a.year}-prize"):
        return redirect("/turnir")
    reward(db, u, 0, 7, "🛡️ Турнир к 23 февраля: вы в тройке лучших! Неделя Nuvora+ в подарок")
    log_mod(db, me, "turnir_award", u.username, "")
    db.commit()
    return redirect("/turnir")


# ---------------------------------------------------------------- открытки: 8 Марта и валентинки
CARDS8 = {"tulips": "Тюльпаны", "daisies": "Ромашки", "hearts": "Сердечки"}
VCARDS = {"pink": ("Розовая", (252, 228, 236), (214, 51, 108)), "red": ("Красная", (200, 40, 62), (255, 255, 255)),
          "cream": ("Кремовая", (246, 241, 232), (181, 86, 47))}


def _logo(im, at=(60, 60), size=92):
    logo = Image.open(os.path.join(ROOT, "static", "brand", "logo-mark-warm.png")).convert("RGBA").resize((size, size))
    im.paste(logo, at, logo)


def _heart(d, cx, cy, r, fill):
    d.ellipse((cx - r, cy - r, cx, cy), fill=fill)
    d.ellipse((cx, cy - r, cx + r, cy), fill=fill)
    d.polygon([(cx - r, cy - r * 0.45), (cx + r, cy - r * 0.45), (cx, cy + r)], fill=fill)


def card8(card, to, text, sign):
    card = card if card in CARDS8 else "tulips"
    im = Image.open(os.path.join(ROOT, "static", "brand", "season", f"mom-{card}.png")).convert("RGB")
    d = ImageDraw.Draw(im)
    ink, accent = (43, 37, 32), (181, 86, 47) if card == "tulips" else (95, 138, 79) if card == "daisies" else (196, 52, 78)
    d.text((540, 150), (to or "Милая").strip()[:30] + ",", font=_font("unbounded-700.ttf", 58), fill=accent, anchor="mm")
    d.text((540, 240), "с 8 Марта!", font=_font("unbounded-700.ttf", 66), fill=ink, anchor="mm")
    _body(d, text, sign, ink, accent)
    _logo(im)
    return _png(im)


def vcard(card, text, sign):
    name, bg, fg = VCARDS.get(card) or VCARDS["pink"]
    im = Image.new("RGB", (1080, 1350), bg)
    d = ImageDraw.Draw(im)
    rnd = random.Random(card)
    soft = tuple(int(c * .82 + f * .18) for c, f in zip(bg, fg))
    for _ in range(26):
        _heart(d, rnd.randint(0, 1080), rnd.randint(0, 1350), rnd.randint(18, 60), soft)
    _heart(d, 540, 330, 150, fg)
    d.text((540, 600), "Валентинка", font=_font("unbounded-700.ttf", 74), fill=fg, anchor="mm")
    _body(d, text, sign, fg, fg, y=720)
    _logo(im)
    return _png(im)


def _body(d, text, sign, ink, accent, y=340):
    f = _font("onest-500.ttf", 40)
    for ln in _wrap(d, (text or "").strip()[:300], f, 860)[:9]:
        d.text((540, y), ln, font=f, fill=ink, anchor="mm")
        y += 56
    if sign:
        d.text((540, y + 30), "— " + sign.strip()[:40], font=_font("onest-800.ttf", 40), fill=accent, anchor="mm")


def _png(im):
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


TEXT8 = "Пусть весна приносит радость, а каждый день — повод улыбнуться. Ты самая лучшая!"


@router.get("/8-marta")
def mar8(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not can(user, "mar8"):
        return redirect("/prazdniki")
    return render(request, db, "packs/v3/mar8.html", sidebar=False, cards=CARDS8, default_text=TEXT8, sign=(user.name or user.username) if user else "")


@router.get("/8-marta/card.png")
def mar8_png(request: Request, db: Session = Depends(get_db), c: str = "tulips", to: str = "", t: str = "", sg: str = "", dl: int = 0):
    user = current_user(request, db)
    if not can(user, "mar8"):
        return Response(status_code=404)
    from services.profanity import has_bad
    if any(has_bad(x) for x in (to, t, sg)):
        to, t, sg = "Милая", TEXT8, ""
    h = {"Cache-Control": "private, max-age=600"}
    if dl:
        h["Content-Disposition"] = 'attachment; filename="8-marta.png"'
    return Response(card8(c, to, t, sg), media_type="image/png", headers=h)


@router.get("/valentine")
def valentine(request: Request, db: Session = Depends(get_db), to: str = ""):
    user = current_user(request, db)
    if not can(user, "valentine"):
        return redirect("/prazdniki")
    if not user:
        return login_redirect(request)
    inbox = db.query(Valentine).filter_by(to_id=user.id).order_by(Valentine.id.desc()).limit(50).all()
    senders = {u.id: u for u in db.query(models.User).filter(models.User.id.in_([v.from_id for v in inbox if not v.anon] or [0]))}
    for v in inbox:
        if not v.seen:
            v.seen = True
    db.commit()
    sent = db.query(Valentine).filter_by(from_id=user.id).count()
    return render(request, db, "packs/v3/valentine.html", cards=VCARDS, inbox=inbox, senders=senders, sent=sent, to=s(to)[:40])


@router.get("/valentine/preview.png")
def valentine_preview(request: Request, db: Session = Depends(get_db), c: str = "pink", t: str = "", sg: str = ""):
    user = current_user(request, db)
    if not user or not can(user, "valentine"):
        return Response(status_code=404)
    from services.profanity import has_bad
    if has_bad(t) or has_bad(sg):
        t, sg = "", ""
    return Response(vcard(c, t, sg), media_type="image/png", headers={"Cache-Control": "private, max-age=600"})


@router.get("/valentine/{vid}.png")
def valentine_png(vid: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    v = db.get(Valentine, vid)
    if not user or not v or user.id not in (v.to_id, v.from_id):
        return Response(status_code=404)
    sign = "Тайный поклонник" if v.anon else ""
    if not v.anon:
        u = db.get(models.User, v.from_id)
        sign = (u.name or u.username) if u else ""
    return Response(vcard(v.card, v.text, sign), media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


@router.post("/valentine/send")
async def valentine_send(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("Войдите", 401)
    if not is_on("valentine") and not user.is_owner:
        return json_error("Валентинки можно отправлять 13–14 февраля", 403)
    from routers.posts import read_payload
    from services.profanity import has_bad
    data = await read_payload(request)
    to = db.query(models.User).filter(func.lower(models.User.username) == s(data.get("to")).lstrip("@").lower()).first()
    if not to:
        return json_error("Нет такого человека")
    ok, why = social.can_message(db, user, to)
    if not ok:
        return json_error(why)
    text = s(data.get("text"))[:200]
    if has_bad(text):
        return json_error("Уберите грубые слова — это же валентинка 💌")
    if not ratelimit.hit(f"valentine:{user.id}", 30, 86400):
        return json_error("На сегодня хватит — 30 валентинок в день")
    card = s(data.get("card")) if s(data.get("card")) in VCARDS else "pink"
    anon = str(data.get("anon")) in ("1", "true", "on")
    v = Valentine(from_id=user.id, to_id=to.id, card=card, text=text, anon=anon)
    db.add(v)
    db.add(models.Notification(user_id=to.id, from_user_id=None if anon else user.id, type="valentine",
                               text="💌 Вам валентинка от тайного поклонника!" if anon else "💌 Вам валентинка!"))
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- 1 апреля
@router.get("/1-aprelya")
def apr1(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not can(user, "apr1"):
        return redirect("/prazdniki")
    y = today().year
    start = dt.datetime(y, 4, 1) - dt.timedelta(hours=3)
    posts = db.query(models.Post).filter(models.Post.created_at >= start, models.Post.created_at < start + dt.timedelta(days=1),
                                         models.Post.content.ilike("%#первоеапреля%")).all()
    posts = sorted(posts, key=lambda p: -len(p.likes))[:20]
    return render(request, db, "packs/v3/apr1.html", posts=posts)


# ---------------------------------------------------------------- снежинки «Первого снега»
@router.post("/prazdniki/snow1/catch")
def snow_catch(request: Request, db: Session = Depends(get_db)):
    """Поймал 10 снежинок — подарок (тот же, что и кнопка «забрать», но только после ловли)."""
    return events_gift("snow1", request, db)


# ---------------------------------------------------------------- админка
@router.get("/admin/events")
def events_admin(request: Request, db: Session = Depends(get_db), ok: int = 0):
    user = current_user(request, db)
    if not user or not user.is_owner:
        return redirect("/")
    d = today()
    rows = []
    for k in KEYS:
        sp = next_span(k, d) if k != "x2" else None
        when = "суббота и воскресенье, 1 июня" if k == "x2" else (f"{sp[0].day} {MONTHS[sp[0].month]} {sp[0].year}" + (
            f" – {sp[1].day} {MONTHS[sp[1].month]}" if sp[1] != sp[0] else "") if sp else "дата не задана")
        rows.append({"key": k, "title": INFO[k][0], "emo": INFO[k][1], "when": when, "mode": mode(k), "on": is_on(k), "link": INFO[k][4]})
    ob = str(site.get("owner_bday") or "")
    return render(request, db, "packs/v3/admin_events.html", sidebar=False, rows=rows, ok=ok, ob=ob)


@router.post("/admin/events")
async def events_save(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user or not user.is_owner:
        return redirect("/")
    f = await request.form()
    val = {k: (s(f.get(k)) if s(f.get(k)) in ("auto", "on", "off") else "auto") for k in KEYS}
    site.put(db, "events", val)
    if social.main_owner(db) and social.main_owner(db).id == user.id:  # дату своего дня рождения меняет только основатель
        m = re.match(r"^\d{4}-(\d{2})-(\d{2})$", s(f.get("owner_bday")))
        site.put(db, "owner_bday", f"{int(m.group(1))}-{int(m.group(2))}" if m else "")
    log_mod(db, user, "events", ", ".join(f"{k}={v}" for k, v in val.items() if v != "auto") or "все по календарю", "")
    db.commit()
    return redirect("/admin/events?ok=1")


@router.get("/prazdniki/state.json")
def events_json(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    snow = is_on("snow1") and user and not claimed(db, user, "snow1", year_tag("snow1"))
    return JSONResponse({"on": active(), "snow": bool(snow)})
