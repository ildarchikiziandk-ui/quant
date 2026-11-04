"""Расписание маршруток и автобусов Верх-Тулы: nvra.ru/vt-transport.

Владелец вписывает расписание в админке (/admin/transport) простым текстом, сайт сам показывает его людям
(«ближайший через 7 мин»), а для каждой остановки готовит табличку для печати с QR-кодом (/vt-transport/sign/<остановка>).
Формат текста — см. EXAMPLE ниже. Время в строках «Будни/Суббота/...» — отправление с ПЕРВОЙ остановки маршрута,
число после названия остановки — сколько минут ехать до неё от первой."""
import html
import re

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

import config
from database import get_db
from deps import current_user, log_mod, redirect, render

from . import site
from .common import router, s

KEY = "vt_transport"
PATH = "/vt-transport"
DAYS = {  # как пишется в тексте → какие дни недели (0 = понедельник)
    "будни": (0, 1, 2, 3, 4), "выходные": (5, 6), "ежедневно": (0, 1, 2, 3, 4, 5, 6), "каждый день": (0, 1, 2, 3, 4, 5, 6),
    "понедельник": (0,), "вторник": (1,), "среда": (2,), "четверг": (3,), "пятница": (4,), "суббота": (5,), "воскресенье": (6,),
}
DAY_TITLE = {"будни": "Будни", "выходные": "Выходные", "ежедневно": "Ежедневно", "каждый день": "Ежедневно"}
EXAMPLE = """# Название: Транспорт Верх-Тулы
# Источник: расписание перевозчика (впишите, откуда взяли время)

Маршрут: 000 | автобус | Верх-Тула — Новосибирск
Остановки: Первая остановка 0, Вторая остановка 4, Третья остановка 9
Будни: 6:10 7:00 8:30
Выходные: 8:00 12:00
"""
_TR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя", ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f", "h", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))


def slug(name):
    t = "".join(_TR.get(c, c) for c in name.lower())
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:60] or "stop"


def _time(tok):
    m = re.fullmatch(r"(\d{1,2})[:.](\d{2})", tok.strip())
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def parse(text):
    """Текст из админки → {"title", "source", "routes": [...], "stops": [...]} и список ошибок («строка 5: …»)."""
    data = {"title": "Транспорт Верх-Тулы", "source": "", "routes": [], "stops": []}
    errors, cur = [], None
    for n, raw in enumerate((text or "").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            k, _, v = line.lstrip("# ").partition(":")
            if k.strip().lower() == "название" and v.strip():
                data["title"] = v.strip()[:80]
            elif k.strip().lower() == "источник":
                data["source"] = v.strip()[:200]
            continue
        key, sep, val = line.partition(":")
        key = key.strip().lower()
        if not sep:
            errors.append(f"строка {n}: нет двоеточия — непонятно, что это")
            continue
        if key == "маршрут":
            parts = [p.strip() for p in val.split("|")]
            cur = {"num": parts[0][:10] or "?", "kind": (parts[1] if len(parts) > 1 else "автобус")[:20].lower(),
                   "name": (parts[2] if len(parts) > 2 else "")[:100], "stops": [], "days": []}
            data["routes"].append(cur)
        elif cur is None:
            errors.append(f"строка {n}: сначала напишите строку «Маршрут: …»")
        elif key == "остановки":
            for item in val.split(","):
                # «~Больница -2»: ~ — время примерное (в расписании перевозчика его нет), минус — раньше опорной остановки
                m = re.fullmatch(r"\s*(~?)\s*(.+?)\s+(-?\d{1,3})\s*", item)
                if not m:
                    if item.strip():
                        errors.append(f"строка {n}: у остановки «{item.strip()}» нет минут в пути (например, «Школа 5»)")
                    continue
                cur["stops"].append({"name": m.group(2)[:60], "slug": slug(m.group(2)), "off": int(m.group(3)), "approx": bool(m.group(1))})
        elif key in DAYS:
            times, bad = [], []
            for tok in val.replace(",", " ").split():
                t = _time(tok)
                (times if t is not None else bad).append(t if t is not None else tok)
            if bad:
                errors.append(f"строка {n}: непонятное время {', '.join(bad)} — пишите так: 6:40")
            cur["days"].append({"key": key, "title": DAY_TITLE.get(key, key.capitalize()), "wd": DAYS[key], "times": sorted(times)})
        else:
            errors.append(f"строка {n}: «{key}» — не знаю такого. Можно: Маршрут, Остановки, Будни, Выходные, Ежедневно или день недели")
    seen = {}
    for r in data["routes"]:
        if not r["stops"]:
            errors.append(f"маршрут {r['num']}: нет остановок")
        if not r["days"]:
            errors.append(f"маршрут {r['num']}: нет времени отправления")
        for st in r["stops"]:
            seen.setdefault(st["slug"], st["name"])
    data["stops"] = [{"slug": k, "name": v} for k, v in seen.items()]
    return data, errors


def fmt(m):
    m %= 24 * 60
    return f"{m // 60}:{m % 60:02d}"


def at_stop(data, stop_slug):
    """Какие маршруты идут через остановку и во сколько они там бывают."""
    out = []
    for r in data["routes"]:
        st = next((x for x in r["stops"] if x["slug"] == stop_slug), None)
        if not st:
            continue
        last = r["stops"][-1]["name"] if r["stops"] else ""
        out.append({"num": r["num"], "kind": r["kind"], "name": r["name"], "to": last, "is_last": st is r["stops"][-1], "approx": st.get("approx", False),
                    "days": [{"title": d["title"], "wd": list(d["wd"]), "times": [fmt(t + st["off"]) for t in d["times"]],
                              "mins": [(t + st["off"]) % 1440 for t in d["times"]]} for d in r["days"]]})
    return out


def load():
    return parse(site.get(KEY) or "")[0]


def _qr_svg(url, size=10):
    import qrcode
    import qrcode.image.svg
    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=size, border=1)
    import io
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode()


PUBLIC = "https://nvurl.ru"  # адрес на табличках (QR и подпись). nvurl.ru останется рабочим и после возвращения nvra.ru: короткие ссылки переадресуют /vt-transport на nvra.ru


def _base():
    """Адрес для QR-кода и подписи на табличке — всегда nvurl.ru: напечатанные таблички не придётся переделывать."""
    return PUBLIC


def _short():
    return re.sub(r"^https?://", "", _base()) + PATH


@router.get(PATH)
def page(request: Request, db: Session = Depends(get_db), stop: str = ""):
    data = load()
    cur = next((x for x in data["stops"] if x["slug"] == stop), None)
    user = current_user(request, db)
    return render(request, db, "packs/v3/transport.html", sidebar=False, data=data, stop=cur,
                  rows=at_stop(data, cur["slug"]) if cur else [], is_owner=bool(user and user.is_owner))


def _sign_html(data, st, rows):
    url = f"{_base()}{PATH}?stop={st['slug']}"
    e = html.escape
    blocks = []
    for r in rows:
        days = "".join(f'<div class="d"><b>{e(d["title"])}</b><span>{"≈ " if r["approx"] else ""}{" ".join(e(t) for t in d["times"]) or "—"}</span></div>' for d in r["days"])
        to = "конечная" if r["is_last"] else "→ " + e(r["to"])
        blocks.append(f'<div class="r"><div class="h"><span class="n">{e(r["num"])}</span><span class="k">{e(r["kind"])}</span>'
                      f'<span class="to">{e(r["name"] or to)}</span></div>{days}</div>')
    total = sum(len(d["times"]) for r in rows for d in r["days"])
    size = "s1" if total <= 45 else "s2" if total <= 90 else "s3" if total <= 140 else "s4"  # шрифт под количество рейсов
    body = "".join(blocks) or '<p class="empty">Через эту остановку маршрутов пока нет</p>'
    if any(r["approx"] for r in rows):
        body += '<p class="note">≈ — примерное время: в расписании перевозчика оно указано только для основных остановок</p>'
    m = re.fullmatch(r"(.+?)\s*\((в сторону города|из города)\)", st["name"])
    title, side = (m.group(1), m.group(2)) if m else (st["name"], "")
    side_html = f'<div class="side">{"→ в сторону города" if side.startswith("в") else "← из города"}</div>' if side else ""
    return (f'<section class="sign"><div class="top"><div class="lbl">Остановка</div><h1>{e(title)}</h1>{side_html}</div>'
            f'<div class="list {size}">{body}</div>'
            f'<div class="bot"><div class="qr">{_qr_svg(url)}</div><div class="txt"><b>Расписание всех маршруток и автобусов</b>'
            f'<span class="u">{e(_short())}</span><small>Наведите камеру телефона на QR-код. Время может меняться — '
            f'актуальное всегда на сайте.</small></div></div></section>')


SIGN_CSS = """@page{size:A4 portrait;margin:0}*{box-sizing:border-box;margin:0}
body{font-family:Onest,Arial,sans-serif;color:#2b2520;background:#e9e2d8}
@font-face{font-family:Onest;src:url(/static/fonts/onest-cyrillic-wght-normal.woff2) format('woff2')}
@font-face{font-family:Unb;src:url(/static/fonts/unbounded-cyrillic-wght-normal.woff2) format('woff2')}
.sign{width:210mm;height:297mm;margin:0 auto 10mm;background:#fff;padding:14mm 13mm 12mm;display:flex;flex-direction:column;page-break-after:always;break-after:page}
.top{border-bottom:2.5mm solid #b5562f;padding-bottom:5mm;margin-bottom:6mm}.lbl{font-size:13pt;text-transform:uppercase;letter-spacing:.12em;color:#6e6254}
h1{font-family:Unb,Arial,sans-serif;font-size:34pt;line-height:1.1;margin-top:2mm}
.side{display:inline-block;margin-top:3mm;background:#b5562f;color:#fff;font-size:15pt;font-weight:700;padding:1.5mm 5mm;border-radius:3mm}
.list{flex:1;overflow:hidden;display:flex;flex-direction:column;gap:5mm}
.r{border:.6mm solid #d6c7b2;border-radius:5mm;padding:4mm 5mm}.h{display:flex;align-items:center;gap:4mm;margin-bottom:2.5mm}
.n{font-family:Unb,Arial,sans-serif;font-size:22pt;background:#2b2520;color:#fff;border-radius:3mm;padding:1mm 4mm;min-width:22mm;text-align:center}
.k{font-size:11pt;text-transform:uppercase;letter-spacing:.08em;color:#6e6254}.to{font-size:14pt;font-weight:600}
.d{display:flex;gap:4mm;font-size:17pt;line-height:1.45;padding:1mm 0}.d b{min-width:36mm}.d span{font-variant-numeric:tabular-nums;word-spacing:2mm}
.s2 .d{font-size:13pt;line-height:1.35}.s2 .r{padding:3mm 4mm}.s2{gap:3mm}
.s3 .d{font-size:11pt;line-height:1.3}.s3 .d b{min-width:28mm}.s3 .r{padding:2.5mm 4mm}.s3 .h{margin-bottom:1.5mm}.s3 .n{font-size:17pt}.s3{gap:2.5mm}
.s4 .d{font-size:9.5pt;line-height:1.25}.s4 .d b{min-width:24mm}.s4 .r{padding:2mm 3.5mm}.s4 .h{margin-bottom:1mm}.s4 .n{font-size:15pt}.s4{gap:2mm}
.empty{font-size:16pt;color:#6e6254}.note{font-size:11pt;color:#6e6254;margin-top:1mm}
.bot{display:flex;gap:7mm;align-items:center;border-top:.6mm solid #d6c7b2;padding-top:6mm;margin-top:5mm}
.qr svg{width:48mm;height:48mm;display:block}.txt{display:flex;flex-direction:column;gap:2mm}.txt b{font-size:17pt}
.u{font-family:Unb,Arial,sans-serif;font-size:24pt;color:#9a4625}.txt small{font-size:10.5pt;color:#6e6254}
.bar{max-width:210mm;margin:8mm auto;display:flex;gap:10px;font-size:15px}.bar button,.bar a{padding:10px 16px;border-radius:12px;border:none;background:#b5562f;color:#fff;font:inherit;cursor:pointer;text-decoration:none}
@media print{body{background:#fff}.bar{display:none}.sign{margin:0}}"""


def _sign_page(title, sections):
    return HTMLResponse(f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                        f'<title>{html.escape(title)}</title><style>{SIGN_CSS}</style></head><body>'
                        f'<div class="bar"><button onclick="print()">Напечатать</button><a href="{PATH}">← К расписанию</a></div>{sections}</body></html>')


@router.get(PATH + "/sign/{stop_slug}")
def sign(stop_slug: str, request: Request, db: Session = Depends(get_db)):
    data = load()
    st = next((x for x in data["stops"] if x["slug"] == stop_slug), None)
    if not st:
        return redirect(PATH)
    return _sign_page(f"Табличка «{st['name']}»", _sign_html(data, st, at_stop(data, st["slug"])))


@router.get(PATH + "/signs")
def signs(request: Request, db: Session = Depends(get_db)):
    data = load()
    if not data["stops"]:
        return redirect(PATH)
    return _sign_page("Все таблички", "".join(_sign_html(data, st, at_stop(data, st["slug"])) for st in data["stops"]))


@router.get(PATH + "/qr.svg")
def qr(stop: str = ""):
    url = f"{_base()}{PATH}" + (f"?stop={re.sub(r'[^a-z0-9-]', '', stop)}" if stop else "")
    return Response(_qr_svg(url), media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})


def _owner(request, db):
    u = current_user(request, db)
    return u if u and u.is_owner else None


@router.get("/admin/transport")
def admin_page(request: Request, db: Session = Depends(get_db), ok: str = ""):
    me = _owner(request, db)
    if not me:
        return redirect("/")
    text = site.get(KEY) or EXAMPLE
    data, errors = parse(text)
    return render(request, db, "packs/v3/admin_transport.html", sidebar=False, text=text, data=data, errors=errors, ok=ok)


@router.post("/admin/transport")
async def admin_save(request: Request, db: Session = Depends(get_db)):
    me = _owner(request, db)
    if not me:
        return redirect("/")
    f = await request.form()
    text = s(f.get("text")).replace("\r\n", "\n")[:60000]
    data, errors = parse(text)
    site.put(db, KEY, text)
    log_mod(db, me, "transport_save", "", f"маршрутов: {len(data['routes'])}, остановок: {len(data['stops'])}")
    db.commit()
    return render(request, db, "packs/v3/admin_transport.html", sidebar=False, text=text, data=data, errors=errors,
                  ok="Сохранено" + (" — но есть ошибки, посмотрите ниже" if errors else ""))
