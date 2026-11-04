"""«Nuvora Карты»: карта Верх-Тулы (/map) — улицы и дома из OpenStreetMap (static/packs/v3/map/vt.json,
собирает tools/build_vt_map.py), остановки из расписания (packs/v3/transport.py) с ближайшими рейсами,
линии маршрутов и «где я». Всё лежит на нашем сервере: без чужих скриптов и карт.
Остановки стоят по карте владельца (4.11.2026); владелец может перетащить точку — она запоминается (site «vt_geo»)."""
import math
import re

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from database import get_db
from deps import current_user, json_error, render

from . import site, transport
from .common import router, s

# центр остановки — по карте владельца; стороны дороги разводятся на ~15 м
BASE = {
    "Поворот на Верх-Тулу": (54.897137, 82.783606), "Река Верх-Тула": (54.892608, 82.777298), "Больница": (54.890104, 82.779861),
    "Центр": (54.885646, 82.780766), "Библиотека": (54.883183, 82.777295), "Совхозная": (54.880122, 82.772871),
    "Новая — ул. Советская": (54.874235, 82.76467), "Строительная": (54.868796, 82.756911), "ул. Луговая": (54.865522, 82.750508),
    "Автотехцентр": (54.862357, 82.744098), "мкр. Радужный": (54.86604, 82.75987), "конечная (кладбище)": (54.855085, 82.762549),
}
SIDE_SHIFT = {"в сторону города": 1, "из города": -1}
COLORS = ["#b5562f", "#3f6f86", "#5f8a4f", "#8a6aa0", "#c48a20", "#9a4625", "#2b2520"]


def _split(name):
    m = re.fullmatch(r"(.+?)\s*\((в сторону города|из города)\)", name)
    return (m.group(1), m.group(2)) if m else (name, "")


def _default_geo(name):
    base, side = _split(name)
    if base not in BASE:
        return None
    lat, lon = BASE[base]
    if side:  # сдвиг поперёк главной дороги (она идёт с северо-востока на юго-запад)
        k = SIDE_SHIFT[side] * 0.00011
        lat, lon = lat - k * 0.7, lon + k * 1.2
    return [round(lat, 6), round(lon, 6)]


def geo_for(name, saved):
    return saved.get(transport.slug(name)) or _default_geo(name)


def map_data():
    data = transport.load()
    saved = site.get("vt_geo") or {}
    stops = []
    for st in data["stops"]:
        g = geo_for(st["name"], saved)
        if not g:
            continue
        base, side = _split(st["name"])
        stops.append({"slug": st["slug"], "name": st["name"], "base": base, "side": side, "lat": g[0], "lon": g[1],
                      "rows": transport.at_stop(data, st["slug"])})
    routes, nums = [], []
    for r in data["routes"]:
        pts = [geo_for(x["name"], saved) for x in r["stops"]]
        pts = [p for p in pts if p]
        if len(pts) >= 2:
            if r["num"] not in nums:
                nums.append(r["num"])
            routes.append({"num": r["num"], "name": r["name"], "pts": pts, "color": COLORS[nums.index(r["num"]) % len(COLORS)]})
    return {"title": data["title"], "stops": stops, "routes": routes, "source": data["source"]}


@router.get("/map")
def map_page(request: Request, db: Session = Depends(get_db), stop: str = ""):
    user = current_user(request, db)
    return render(request, db, "packs/v3/map.html", sidebar=False, md=map_data(), focus=re.sub(r"[^a-z0-9-]", "", stop),
                  can_edit=bool(user and user.is_owner))


@router.post("/admin/map/stop")
async def map_stop_save(request: Request, db: Session = Depends(get_db)):
    me = current_user(request, db)
    if not me or not me.is_owner:
        return json_error("Только для владельца", 403)
    from routers.posts import read_payload
    d = await read_payload(request)
    slug_ = re.sub(r"[^a-z0-9-]", "", s(d.get("slug")))[:80]
    try:
        lat, lon = float(d.get("lat")), float(d.get("lon"))
    except (TypeError, ValueError):
        return json_error("Нет координат")
    if not slug_ or not (-90 <= lat <= 90 and -180 <= lon <= 180) or math.isnan(lat):
        return json_error("Неверные координаты")
    geo = dict(site.get("vt_geo") or {})
    geo[slug_] = [round(lat, 6), round(lon, 6)]
    site.put(db, "vt_geo", geo)
    return {"ok": True}
