"""Плитки (картинки 512×512) для «Nuvora Карты»: сервер рисует их один раз из static/packs/v3/map/vt.json,
и карта на телефоне при приближении плавно увеличивается, а не перерисовывается заново.
Запуск: python tools/render_vt_tiles.py   (≈10 минут; update.sh сам запускает в фоне deploy/map-tiles.sh,
если плиток нет или vt.json изменился; --if-needed — ничего не делать, если плитки уже свежие)
Плитки: static/packs/v3/map/tiles/{z}/{x}/{y}.png, масштабы 13–18."""
import hashlib
import json
import math
import os
import shutil
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "static", "packs", "v3", "map", "vt.json")
OUT = os.path.join(ROOT, "static", "packs", "v3", "map", "tiles")
ZOOMS = range(13, 19)  # номер плитки; карта показывает её на масштабе на 1 больше (плитки 512 px)
T = 512           # размер готовой плитки
SS = 2            # рисуем вдвое крупнее и уменьшаем — линии получаются гладкими
BG, GREEN, CEM, WATER, RIVER = (244, 237, 227), (223, 230, 207), (217, 220, 203), (188, 211, 227), (143, 179, 207)
BLD, BLD_EDGE = (230, 217, 199), (214, 199, 178)
ROAD = {1: ((232, 162, 127), 11), 2: ((241, 195, 166), 9), 3: ((255, 255, 255), 7), 4: ((255, 255, 255), 4), 5: ((214, 199, 178), 3), 6: ((214, 199, 178), 2)}
CASING = (205, 184, 158)


def world(lon, lat):
    """Координаты → «мировые» пиксели масштаба 0 (как у всех веб-карт)."""
    x = (lon + 180) / 360
    s = math.sin(math.radians(lat))
    y = 0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)
    return x, y


def bbox(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def prep(items, key=None):
    out = []
    for it in items:
        c = it[key] if key else it
        w = [world(*p) for p in c]
        if len(w) >= 2:
            out.append((bbox(w), w, it))
    return out


def src_hash():
    return hashlib.sha1(open(SRC, "rb").read()).hexdigest()[:10]


def fresh():
    try:
        return json.load(open(os.path.join(OUT, "meta.json")))["v"] == src_hash()
    except (OSError, ValueError, KeyError):
        return False


def main():
    if "--if-needed" in sys.argv and fresh():
        print("плитки уже свежие")
        return 0
    d = json.load(open(SRC, encoding="utf-8"))
    tmp = OUT + ".tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    green, water = prep(d["green"], "c"), prep(d["water"])
    rivers, blds, roads = prep(d["rivers"]), prep(d["buildings"], "c"), prep(d["roads"], "c")
    lon0, lat0, lon1, lat1 = d["bbox"]
    total = 0
    for z in ZOOMS:
        n = 2 ** z
        mpp = 40075016 * math.cos(math.radians((lat0 + lat1) / 2)) / (n * T)  # метров в пикселе плитки
        x0, y1 = world(lon0, lat0)
        x1, y0 = world(lon1, lat1)
        tx0, tx1, ty0, ty1 = int(x0 * n), int(x1 * n), int(y0 * n), int(y1 * n)
        for tx in range(tx0, tx1 + 1):
            for ty in range(ty0, ty1 + 1):
                bx0, by0, bx1, by1 = tx / n, ty / n, (tx + 1) / n, (ty + 1) / n
                pad = 20 / (n * T)
                S = T * SS

                def px(p):
                    return ((p[0] - bx0) * n * S, (p[1] - by0) * n * S)

                def hit(b):
                    return not (b[2] < bx0 - pad or b[0] > bx1 + pad or b[3] < by0 - pad or b[1] > by1 + pad)
                im = Image.new("RGB", (S, S), BG)
                dr = ImageDraw.Draw(im)
                for b, w, it in green:
                    if hit(b):
                        dr.polygon([px(p) for p in w], fill=CEM if it.get("k") == "cemetery" else GREEN)
                for b, w, _ in water:
                    if hit(b):
                        dr.polygon([px(p) for p in w], fill=WATER)
                rw = max(2, int(6 / mpp)) * SS
                for b, w, _ in rivers:
                    if hit(b):
                        dr.line([px(p) for p in w], fill=RIVER, width=rw, joint="curve")
                if z >= 14:
                    edge = SS if z >= 16 else 0
                    for b, w, _ in blds:
                        if hit(b):
                            dr.polygon([px(p) for p in w], fill=BLD, outline=BLD_EDGE if edge else None, width=edge or 1)
                for k in (6, 5, 4, 3, 2, 1):
                    col, metres = ROAD[k]
                    if z < 15 and k >= 4:
                        continue
                    width = max(1 if k >= 4 else 2, int(metres / mpp)) * SS
                    for b, w, it in roads:
                        if it["k"] == k and hit(b):
                            pts = [px(p) for p in w]
                            if k <= 3 and z >= 14:
                                dr.line(pts, fill=CASING, width=width + 2 * SS, joint="curve")
                            dr.line(pts, fill=col, width=width, joint="curve")
                im = im.resize((T, T), Image.LANCZOS)
                path = os.path.join(tmp, str(z), str(tx))
                os.makedirs(path, exist_ok=True)
                im.save(os.path.join(path, f"{ty}.png"), optimize=True)
                total += 1
        print(f"масштаб {z}: готово", flush=True)
    json.dump({"v": src_hash(), "zooms": [min(ZOOMS), max(ZOOMS)], "tiles": total, "bbox": d["bbox"]}, open(os.path.join(tmp, "meta.json"), "w"))
    old = OUT + ".old"
    shutil.rmtree(old, ignore_errors=True)
    if os.path.isdir(OUT):
        os.rename(OUT, old)
    os.rename(tmp, OUT)  # подмена разом — карта никогда не видит половину плиток
    shutil.rmtree(old, ignore_errors=True)
    print("плиток:", total, "→", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
