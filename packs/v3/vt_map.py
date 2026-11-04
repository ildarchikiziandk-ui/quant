"""«Nuvora Карты»: карта Верх-Тулы (/map) — улицы и дома из OpenStreetMap (static/packs/v3/map/vt.json,
собирает tools/build_vt_map.py), остановки из расписания (packs/v3/transport.py) с ближайшими рейсами,
линии маршрутов и «где я». Всё лежит на нашем сервере: без чужих скриптов и карт.
Остановки стоят по карте владельца (4.11.2026); владелец может перетащить точку — она запоминается (site «vt_geo»)."""
import json
import math
import os
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
COLORS = ["#b5562f", "#3f6f86", "#5f8a4f", "#8a6aa0", "#c48a20", "#9a4625", "#2b2520"]
EDGE_M = 9  # остановка — на обочине, в 9 м от середины дороги
# у двух крайних точек названия разные по сторонам — считаем их сторонами одной остановки
SIDE_OF = {"Поворот на Верх-Тулу": "в сторону города", "Река Верх-Тула": "из города"}
_roads = []
# ошибки адресов в OpenStreetMap, которые поправил владелец (ключ — первая точка контура дома «долгота,широта»);
# свои правки владелец делает на карте: «Править» → долгое нажатие на дом (site «vt_addr»)
ADDR_FIX = {
    "82.78468,54.88599": {"s": "Рабочая улица", "h": "51а"},  # в OSM записан как «улица Кирова, 51а» (4.11.2026)
}
TILES = os.path.join(os.path.dirname(__file__), "..", "..", "static", "packs", "v3", "map", "tiles")


def tiles_version():
    """Версия готовых плиток (tools/render_vt_tiles.py) или "" — тогда карта рисуется в браузере, как раньше."""
    try:
        return str(json.load(open(os.path.join(TILES, "meta.json")))["v"])
    except (OSError, ValueError, KeyError):
        return ""


def addr_fixes():
    out = dict(ADDR_FIX)
    out.update(site.get("vt_addr") or {})
    return out


def _load_roads():
    if not _roads:
        path = os.path.join(os.path.dirname(__file__), "..", "..", "static", "packs", "v3", "map", "vt.json")
        try:
            d = json.load(open(path, encoding="utf-8"))
            _roads.extend(r for r in d["roads"] if r["k"] <= 3)
        except (OSError, ValueError, KeyError):
            _roads.append({"c": [], "k": 9})
    return _roads


def _snap(lat, lon, side):
    """Ближайшая точка главной дороги и сдвиг на обочину: в России ездят справа, поэтому автобус «в сторону города»
    (на север, к выезду на Новосибирск) останавливается справа по ходу, а «из города» — с другой стороны."""
    kx = 111320 * math.cos(math.radians(lat))
    ky = 111320

    def m(p):
        return ((p[0] - lon) * kx, (p[1] - lat) * ky)
    best = None
    for limit in (2, 3):
        for r in _load_roads():
            if r["k"] > limit:
                continue
            pts = [m(p) for p in r["c"]]
            for a, b in zip(pts, pts[1:]):
                dx, dy = b[0] - a[0], b[1] - a[1]
                ln2 = dx * dx + dy * dy
                if not ln2:
                    continue
                t = max(0.0, min(1.0, -(a[0] * dx + a[1] * dy) / ln2))
                px, py = a[0] + t * dx, a[1] + t * dy
                dist = math.hypot(px, py)
                if best is None or dist < best[0]:
                    best = (dist, px, py, dx, dy)
        if best and best[0] < 160:  # главная дорога рядом — к ней, а не к соседней улочке
            break
    if not best or best[0] > 200:
        return lat, lon
    _, px, py, dx, dy = best
    if dy < 0 or (dy == 0 and dx < 0):  # направление «в сторону города» — на север
        dx, dy = -dx, -dy
    ln = math.hypot(dx, dy) or 1
    rx, ry = dy / ln, -dx / ln  # вправо по ходу движения на север
    sign = 1 if side == "в сторону города" else -1 if side == "из города" else 0
    px, py = px + sign * rx * EDGE_M, py + sign * ry * EDGE_M
    return lat + py / ky, lon + px / kx


def _split(name):
    m = re.fullmatch(r"(.+?)\s*\((в сторону города|из города)\)", name)
    if m:
        return m.group(1), m.group(2)
    return name, SIDE_OF.get(name, "")


def _default_geo(name):
    base, side = _split(name)
    if base not in BASE:
        return None
    lat, lon = _snap(*BASE[base], side)
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
    return {"title": data["title"], "stops": stops, "routes": routes, "source": data["source"],
            "addr": addr_fixes(), "tiles": tiles_version()}


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


@router.post("/admin/map/addr")
async def map_addr_save(request: Request, db: Session = Depends(get_db)):
    """Владелец исправляет адрес дома: улица и номер. Пустой номер — убрать правку."""
    me = current_user(request, db)
    if not me or not me.is_owner:
        return json_error("Только для владельца", 403)
    from routers.posts import read_payload
    d = await read_payload(request)
    key = s(d.get("key"))[:40]
    if not re.fullmatch(r"-?\d{1,3}\.\d{1,7},-?\d{1,2}\.\d{1,7}", key):
        return json_error("Не понял, какой это дом")
    street, num = s(d.get("s"))[:80], s(d.get("h"))[:20]
    fixes = dict(site.get("vt_addr") or {})
    if num:
        fixes[key] = {"s": street, "h": num}
    else:
        fixes.pop(key, None)
    site.put(db, "vt_addr", fixes)
    return {"ok": True}
