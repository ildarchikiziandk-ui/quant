"""Собирает справочник населённых пунктов России (города, сёла, посёлки, деревни) для поля «Город».

Источник — GeoNames (бесплатно, CC BY 4.0): https://download.geonames.org/export/dump/
Скачивает ~30 МБ, работает пару минут, на выходе places.sqlite (~30 МБ) рядом с сайтом.
Названия — по-русски. Подпись: «Ивановка, Амурская область».

Запуск на сервере: python tools/build_places.py   (или bash deploy/places.sh)
"""
import io
import os
import re
import sqlite3
import sys
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.places import PLACES_DB, norm  # noqa: E402

BASE = "https://download.geonames.org/export/dump/"
SKIP_CODES = {"PPLX", "PPLH", "PPLQ", "PPLW", "PPLCH"}  # районы городов, исторические, заброшенные, разрушенные
RU_ONLY = re.compile(r"^[А-Яа-яЁё0-9 .,()«»'\-–—]+$")  # кириллица без украинских/белорусских/тюркских букв
HOME = "RU"  # для своей страны регион пишем без названия страны


def fetch(name, work):
    path = os.path.join(work, name.replace("/", "-"))
    if not os.path.exists(path):
        print("скачиваю", name, flush=True)
        urllib.request.urlretrieve(BASE + name, path + ".part")
        os.replace(path + ".part", path)
    return path


def lines(path, inner=None):
    if path.endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            inner = inner or next(n for n in z.namelist() if n.endswith(".txt") and not n.lower().startswith(("readme", "iso")))
            with z.open(inner) as f:
                for raw in io.TextIOWrapper(f, encoding="utf-8"):
                    if not raw.startswith("#"):
                        yield raw.rstrip("\n").split("\t")
    else:
        with open(path, encoding="utf-8") as f:
            for raw in f:
                if not raw.startswith("#"):
                    yield raw.rstrip("\n").split("\t")


def russian_names(path):
    """geonameid → русское название (предпочтительное, если отмечено)."""
    ru, pref = {}, set()
    for c in lines(path):
        if len(c) < 8 or c[2] != "ru" or c[6] == "1" or c[7] == "1":  # без разговорных и исторических
            continue
        gid = int(c[1])
        if c[4] == "1" and gid not in pref:
            ru[gid] = c[3]
            pref.add(gid)
        elif gid not in ru:
            ru[gid] = c[3]
    return ru


def build(all_countries, alt_names, admin1, country_info, out):
    ru = russian_names(alt_names)
    print("русских названий:", len(ru), flush=True)
    countries = {}
    for c in lines(country_info):
        if len(c) > 16 and c[16]:
            countries[c[0]] = ru.get(int(c[16]), c[4])
    regions = {}  # код → (название, есть ли по-русски)
    for c in lines(admin1):
        if len(c) > 3 and c[3]:
            regions[c[0]] = (ru.get(int(c[3]), c[1]), int(c[3]) in ru)
    tmp = out + ".part"
    if os.path.exists(tmp):
        os.remove(tmp)
    db = sqlite3.connect(tmp)
    db.execute("PRAGMA journal_mode=OFF")
    db.execute("PRAGMA synchronous=OFF")
    db.execute("CREATE TABLE places (id INTEGER PRIMARY KEY, label TEXT, pop INTEGER)")
    db.execute("CREATE TABLE names (key TEXT, pop INTEGER, id INTEGER)")
    n, batch_p, batch_n = 0, [], []
    for c in lines(all_countries):
        if len(c) < 15 or c[6] != "P" or c[7] in SKIP_CODES or c[8] != HOME:  # только Россия
            continue
        gid, cc = int(c[0]), c[8]
        name = ru.get(gid)
        if not name and cc in ("RU", "BY", "KZ", "KG", "UA", "MD", "TJ", "UZ", "AB"):
            name = next((a for a in c[3].split(",") if a and RU_ONLY.match(a) and re.search("[А-Яа-я]", a)), None)
        name = (name or c[1]).strip()
        if not name:
            continue
        parts = [name]
        region, region_ru = regions.get(f"{cc}.{c[10]}", ("", False))
        cyr = bool(re.search("[А-Яа-я]", name))
        if region and norm(region) != norm(name) and (region_ru or not cyr):  # не мешаем кириллицу с латиницей
            parts.append(region)
        if cc != HOME and countries.get(cc) and norm(countries[cc]) != norm(name):
            parts.append(countries[cc])
        label = ", ".join(parts)[:120]
        pop = int(c[14] or 0)
        batch_p.append((gid, label, pop))
        for key in {norm(name), norm(c[1]), norm(c[2])}:
            if key:
                batch_n.append((key, pop, gid))
        n += 1
        if len(batch_p) >= 50000:
            db.executemany("INSERT INTO places VALUES (?,?,?)", batch_p)
            db.executemany("INSERT INTO names VALUES (?,?,?)", batch_n)
            batch_p, batch_n = [], []
            print("  мест:", n, flush=True)
    db.executemany("INSERT INTO places VALUES (?,?,?)", batch_p)
    db.executemany("INSERT INTO names VALUES (?,?,?)", batch_n)
    print("строю поиск…", flush=True)
    db.execute("CREATE INDEX names_key ON names (key, pop DESC, id)")
    db.execute("CREATE INDEX places_label ON places (label)")
    db.commit()
    db.close()
    os.replace(tmp, out)
    print(f"готово: {n} населённых пунктов → {out}", flush=True)
    return n


def main():
    work = os.path.join(os.path.dirname(PLACES_DB), "places-download")
    os.makedirs(work, exist_ok=True)
    files = [fetch(f, work) for f in (HOME + ".zip", "alternatenames/" + HOME + ".zip", "admin1CodesASCII.txt", "countryInfo.txt")]
    build(*files, PLACES_DB)
    for f in os.listdir(work):
        os.remove(os.path.join(work, f))
    os.rmdir(work)


if __name__ == "__main__":
    main()
