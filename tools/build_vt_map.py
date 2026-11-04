"""Карта Верх-Тулы для «Nuvora Карты» (/map): дороги, дома, вода и места из OpenStreetMap → static/packs/v3/map/vt.json.

Данные © участники OpenStreetMap, лицензия ODbL (подпись есть на карте).
Запуск:  python tools/build_vt_map.py                 (скачает квадрат вокруг Верх-Тулы с openstreetmap.org)
         python tools/build_vt_map.py путь/к/map.osm  (из уже скачанного файла)
"""
import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "static", "packs", "v3", "map", "vt.json")
BBOX = (82.70, 54.84, 82.84, 54.92)  # запад, юг, восток, север — Верх-Тула и соседи (Крупской, 8 Марта)
ROADS = {"motorway": 1, "trunk": 1, "primary": 1, "secondary": 1, "tertiary": 2, "unclassified": 3, "residential": 3,
         "living_street": 3, "service": 4, "track": 5, "footway": 6, "path": 6}
POI_KEYS = ("amenity", "shop", "leisure", "tourism", "office", "craft", "healthcare", "historic")
POI_TYPES = {"school": "Школа", "kindergarten": "Детский сад", "pharmacy": "Аптека", "post_office": "Почта", "clinic": "Поликлиника",
             "hospital": "Больница", "doctors": "Врач", "place_of_worship": "Храм", "library": "Библиотека", "community_centre": "Дом культуры",
             "cafe": "Кафе", "fuel": "Заправка", "bank": "Банк", "atm": "Банкомат", "townhall": "Администрация", "police": "Полиция",
             "fire_station": "Пожарная часть", "supermarket": "Супермаркет", "convenience": "Магазин", "playground": "Детская площадка",
             "stadium": "Стадион", "pitch": "Спортплощадка", "park": "Парк", "grave_yard": "Кладбище", "marketplace": "Рынок",
             "outpost": "Пункт выдачи", "car_repair": "Автосервис", "car_parts": "Автозапчасти", "alcohol": "Напитки", "brewery": "Пивоварня",
             "pet": "Зоомагазин", "cosmetics": "Косметика", "bathroom_furnishing": "Сантехника", "hardware": "Хозтовары",
             "clothes": "Одежда", "bakery": "Пекарня", "butcher": "Мясо", "florist": "Цветы", "mobile_phone": "Телефоны",
             "beauty": "Салон красоты", "hairdresser": "Парикмахерская", "dentist": "Стоматология", "veterinary": "Ветклиника",
             "restaurant": "Ресторан", "fast_food": "Кафе", "car_wash": "Автомойка", "waste_transfer_station": "Пункт приёма отходов"}


def r5(v):
    return round(float(v), 5)


def build(osm_xml):
    root = ET.fromstring(osm_xml)
    nodes = {n.get("id"): (r5(n.get("lon")), r5(n.get("lat"))) for n in root.iter("node")}
    out = {"roads": [], "buildings": [], "water": [], "rivers": [], "green": [], "pois": [], "places": []}
    for n in root.iter("node"):
        t = {x.get("k"): x.get("v") for x in n.iter("tag")}
        if not t:
            continue
        ll = nodes[n.get("id")]
        if t.get("place") in ("village", "hamlet", "town", "suburb", "neighbourhood", "isolated_dwelling") and t.get("name"):
            out["places"].append({"n": t["name"], "c": ll, "k": t["place"]})
        kind = next((t[k] for k in POI_KEYS if t.get(k)), None)
        if kind and (t.get("name") or kind in POI_TYPES):
            out["pois"].append({"n": t.get("name") or POI_TYPES.get(kind, ""), "t": POI_TYPES.get(kind, kind), "c": ll})
    for w in root.iter("way"):
        t = {x.get("k"): x.get("v") for x in w.iter("tag")}
        pts = [nodes[nd.get("ref")] for nd in w.iter("nd") if nd.get("ref") in nodes]
        if len(pts) < 2:
            continue
        hw = t.get("highway")
        if hw in ROADS:
            out["roads"].append({"c": pts, "k": ROADS[hw], **({"n": t["name"]} if t.get("name") else {})})
        elif t.get("building") and len(pts) > 3:
            b = {"c": pts}
            if t.get("addr:housenumber"):
                b["h"] = t["addr:housenumber"][:12]
                if t.get("addr:street") or t.get("addr:place"):
                    b["s"] = (t.get("addr:street") or t.get("addr:place"))[:60]
            if t.get("name"):
                b["n"] = t["name"][:60]
            out["buildings"].append(b)
            kind = next((t[k] for k in POI_KEYS if t.get(k)), None)
            if kind and (t.get("name") or kind in POI_TYPES):
                lon = sum(p[0] for p in pts) / len(pts)
                lat = sum(p[1] for p in pts) / len(pts)
                out["pois"].append({"n": t.get("name") or POI_TYPES.get(kind, ""), "t": POI_TYPES.get(kind, kind), "c": (r5(lon), r5(lat))})
        elif t.get("waterway") in ("river", "stream", "canal"):
            out["rivers"].append(pts)
        elif (t.get("natural") == "water" or t.get("landuse") in ("reservoir", "basin")) and len(pts) > 3:
            out["water"].append(pts)
        elif (t.get("landuse") in ("forest", "meadow", "grass", "cemetery", "allotments") or t.get("natural") in ("wood", "scrub")
              or t.get("leisure") in ("park", "pitch", "stadium")) and len(pts) > 3:
            out["green"].append({"c": pts, "k": t.get("landuse") or t.get("natural") or t.get("leisure")})
    out["bbox"] = BBOX
    return out


def main():
    if len(sys.argv) > 1:
        data = open(sys.argv[1], "rb").read()
    else:
        url = "https://www.openstreetmap.org/api/0.6/map?bbox=" + ",".join(map(str, BBOX))
        req = urllib.request.Request(url, headers={"User-Agent": "Nuvora-map/1.0 (nvurl.ru)"})
        data = urllib.request.urlopen(req, timeout=180).read()
    out = build(data)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("карта →", OUT, round(os.path.getsize(OUT) / 1024), "КБ;", {k: len(v) for k, v in out.items() if isinstance(v, list)})


if __name__ == "__main__":
    main()
