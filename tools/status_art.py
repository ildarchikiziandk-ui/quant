"""Статусы у имени для Nuvora+ (6.11.2026): больше 200 маленьких нарисованных стикеров без подписей —
мордочки 12 персонажей Nuvora с разными настроениями и предметы в том же стиле (толстый контур, белая обводка).
Рисует SVG → Playwright → static/estatus/<id>.webp (128×128) и список static/estatus/index.json (его читает packs/v3/estatus.py).
Запуск: python3 tools/status_art.py [папка-для-черновиков]"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stickers_gen import INK, PINK, heart, sparkle, whale  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ------------------------------------------------------------------ мелкие помощники
def S(w, col=INK):
    return f'fill="none" stroke="{col}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"'


def P(d, fill, sw=10, extra=""):
    return f'<path d="{d}" fill="{fill}" stroke="{INK}" stroke-width="{sw}" stroke-linejoin="round" stroke-linecap="round" {extra}/>'


def C(x, y, r, fill, sw=10):
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{INK}" stroke-width="{sw}"/>'


def E(x, y, rx, ry, fill, sw=10, rot=0):
    return f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" fill="{fill}" stroke="{INK}" stroke-width="{sw}" transform="rotate({rot} {x} {y})"/>'


def dot(x, y, r, fill):
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}"/>'


def shine(d, w=14):
    return f'<path d="{d}" fill="none" stroke="#fff" stroke-width="{w}" stroke-linecap="round" opacity=".5"/>'


def star_pts(cx, cy, R, r, n=5, rot=-90):
    pts = []
    for i in range(n * 2):
        a = math.radians(rot + i * 180 / n)
        rr = R if i % 2 == 0 else r
        pts.append(f"{cx + rr * math.cos(a):.1f},{cy + rr * math.sin(a):.1f}")
    return " ".join(pts)


def star(cx, cy, R, fill, sw=10, n=5, k=.48):
    return f'<polygon points="{star_pts(cx, cy, R, R * k, n)}" fill="{fill}" stroke="{INK}" stroke-width="{sw}" stroke-linejoin="round"/>'


def blob(circles, fill, sw=10):
    """Облако из кругов: сначала общий контур, потом заливка поверх — без внутренних линий."""
    return ("".join(f'<circle cx="{x}" cy="{y}" r="{r + sw / 2}" fill="{INK}"/>' for x, y, r in circles)
            + "".join(f'<circle cx="{x}" cy="{y}" r="{r - sw / 2}" fill="{fill}"/>' for x, y, r in circles))


def ring(cx, cy, R, r):
    return (f"M{cx - R} {cy} a{R} {R} 0 1 0 {2 * R} 0 a{R} {R} 0 1 0 {-2 * R} 0 Z "
            f"M{cx - r} {cy} a{r} {r} 0 1 1 {2 * r} 0 a{r} {r} 0 1 1 {-2 * r} 0 Z")


def tears(pts):
    return "".join(f'<path d="M{x} {y} q-10 24 0 34 q11 4 13 -9 q0 -13 -13 -25 z" fill="#7fc3f0" stroke="{INK}" stroke-width="5"/>' for x, y in pts)


def zz(x, y):
    return (f'<text x="{x}" y="{y}" font-family="Unbounded" font-weight="800" font-size="70" fill="#7fb0d3" stroke="{INK}" stroke-width="6" paint-order="stroke">z</text>'
            f'<text x="{x + 44}" y="{y - 52}" font-family="Unbounded" font-weight="800" font-size="50" fill="#7fb0d3" stroke="{INK}" stroke-width="5" paint-order="stroke">z</text>')


def anger(x, y):
    return f'<path d="M{x - 24} {y - 26} q16 26 0 52 M{x + 24} {y - 26} q-16 26 0 52 M{x - 26} {y - 24} q26 16 52 0 M{x - 26} {y + 24} q26 -16 52 0" {S(11, "#e2474f")}/>'


CONFETTI = "".join(f'<rect x="{x}" y="{y}" width="22" height="12" rx="4" fill="{c}" stroke="{INK}" stroke-width="4" transform="rotate({r} {x} {y})"/>' for x, y, c, r in
                   [(70, 110, "#e2474f", 30), (430, 80, "#3c9a5f", -20), (110, 40, "#2f6487", 60), (450, 200, "#f2c14e", 15), (50, 230, "#c98a1b", -40)])


def hat(x=296, y=40, rot=14):
    return (f'<g transform="rotate({rot} {x} {y + 70})">'
            + P(f"M{x - 70} {y + 130} L{x} {y} L{x + 70} {y + 130} Q{x} {y + 150} {x - 70} {y + 130} Z", "#8a6aa0", 9)
            + f'<path d="M{x - 46} {y + 86} L{x + 46} {y + 86} M{x - 24} {y + 44} L{x + 24} {y + 44}" stroke="#f2c14e" stroke-width="14" stroke-linecap="round"/>'
            + C(x, y, 20, "#e2474f", 8) + "</g>")


# ------------------------------------------------------------------ глаза и рты
def eyes(kind, lx, ly, rx, ry, r=18, ink=INK, white="#fff"):
    def d(x, y, rr=r):
        return f'<circle cx="{x}" cy="{y}" r="{rr}" fill="{ink}"/><circle cx="{x + rr * .35:.0f}" cy="{y - rr * .4:.0f}" r="{rr * .36:.0f}" fill="{white}"/>'
    if kind == "dot":
        return d(lx, ly) + d(rx, ry)
    if kind == "happy":
        return f'<path d="M{lx - 20} {ly + 8} q20 -28 40 0" {S(11, ink)}/><path d="M{rx - 20} {ry + 8} q20 -28 40 0" {S(11, ink)}/>'
    if kind == "closed":
        return f'<path d="M{lx - 20} {ly} q20 18 40 0" {S(11, ink)}/><path d="M{rx - 20} {ry} q20 18 40 0" {S(11, ink)}/>'
    if kind == "angry":
        return d(lx, ly + 6, r - 2) + d(rx, ry + 6, r - 2) + f'<path d="M{lx - 28} {ly - 26} l44 18" {S(11, ink)}/><path d="M{rx + 28} {ry - 26} l-44 18" {S(11, ink)}/>'
    if kind == "sad":
        return d(lx, ly + 6) + d(rx, ry + 6) + f'<path d="M{lx - 26} {ly - 22} l36 -10" {S(10, ink)}/><path d="M{rx + 26} {ry - 22} l-36 -10" {S(10, ink)}/>'
    if kind == "wow":
        return "".join(f'<circle cx="{x}" cy="{y}" r="{r + 9}" fill="#fff" stroke="{INK}" stroke-width="8"/><circle cx="{x}" cy="{y + 2}" r="{r - 5}" fill="{INK}"/>' for x, y in ((lx, ly), (rx, ry)))
    if kind == "heart":
        return heart(lx, ly, 36, "#e2474f") + heart(rx, ry, 36, "#e2474f")
    if kind == "wink":
        return d(lx, ly) + f'<path d="M{rx - 20} {ry + 6} q20 -26 40 0" {S(11, ink)}/>'
    if kind == "cool":
        w = 44
        return (f'<path d="M{lx - w} {ly - 18} H{rx + w} V{ly - 4} Q{rx + w - 4} {ly + 34} {rx} {ly + 34} Q{rx - w + 4} {ly + 34} {rx - w + 2} {ly - 4} '
                f'H{lx + w - 2} Q{lx + w - 4} {ly + 34} {lx} {ly + 34} Q{lx - w + 4} {ly + 34} {lx - w} {ly - 4} Z" fill="{INK}"/>'
                f'<path d="M{lx - 26} {ly - 4} l18 0 M{rx - 26} {ry - 4} l18 0" stroke="#fff" stroke-width="7" stroke-linecap="round" opacity=".7"/>')
    return ""


def mouth(kind, x=256, y=340):
    return {
        "smile": f'<path d="M{x - 26} {y - 6} q26 24 52 0" {S(10)}/>',
        "grin": f'<path d="M{x - 34} {y - 10} q34 8 68 -2 q-8 42 -34 42 q-26 0 -34 -40 z" fill="#8f2a36" stroke="{INK}" stroke-width="8" stroke-linejoin="round"/>'
                f'<path d="M{x - 16} {y + 20} q16 10 32 0" fill="none" stroke="#e8737c" stroke-width="8" stroke-linecap="round"/>',
        "o": f'<ellipse cx="{x}" cy="{y + 6}" rx="15" ry="19" fill="#8f2a36" stroke="{INK}" stroke-width="8"/>',
        "sad": f'<path d="M{x - 24} {y + 12} q24 -20 48 0" {S(10)}/>',
        "flat": f'<path d="M{x - 22} {y + 2} h44" {S(10)}/>',
        "w": f'<path d="M{x - 30} {y - 6} q15 16 30 0 q15 16 30 0" {S(9)}/>',
        "tongue": f'<path d="M{x - 30} {y - 8} q30 22 60 0" {S(10)}/><path d="M{x - 10} {y + 4} q2 26 15 24 q13 -2 5 -24" fill="#e8737c" stroke="{INK}" stroke-width="6"/>',
        "none": "",
    }[kind]


def beak(m, x=256, y=330, col="#f29a38", dark="#c9662a"):
    if m in ("grin", "o", "tongue"):
        return (P(f"M{x - 36} {y - 10} q36 -20 72 0 q-36 14 -72 0 z", col, 7)
                + P(f"M{x - 30} {y + 6} q30 36 60 0 q-30 8 -60 0 z", dark, 7))
    if m == "sad":
        return P(f"M{x - 36} {y + 4} q36 20 72 0 q-36 -22 -72 0 z", col, 7)
    return P(f"M{x - 38} {y - 4} q38 -22 76 0 q-38 30 -76 0 z", col, 7)


# ------------------------------------------------------------------ персонажи (только голова — так их видно даже маленькими)
HX, HY, HRX, HRY = 256, 292, 160, 140
LX, RX, LY = 194, 318, 278

CHARS = [
    ("mur", "Кот Мур", dict(col="#f2a65a", light="#fde6c8",
        back=P("M112 230 L128 76 L240 170 Z", "#f2a65a", 10) + P("M400 230 L384 76 L272 170 Z", "#f2a65a", 10)
        + '<path d="M138 196 L146 116 L206 166 Z" fill="#f4a3a8"/><path d="M374 196 L366 116 L306 166 Z" fill="#f4a3a8"/>',
        front='<path d="M232 160 l6 34 M256 156 v36 M280 160 l-6 34" stroke="#cf7a35" stroke-width="10" stroke-linecap="round"/>'
        + P("M242 310 h28 l-14 14 z", "#e8737c", 5)
        + f'<path d="M120 318 l-62 -10 M120 340 l-60 10 M392 318 l62 -10 M392 340 l60 10" {S(7)}/>',
        mouth_y=346, rest="w")),
    ("kapi", "Капибара Капи", dict(col="#b07d4f", light="#c89668",
        back=C(142, 168, 30, "#8a5e38", 9) + C(370, 168, 30, "#8a5e38", 9),
        front=E(256, 338, 104, 70, "#c89668", 0) + E(230, 320, 11, 8, "#4a2f1c", 0) + E(282, 320, 11, 8, "#4a2f1c", 0),
        mouth_y=362, rest="smile", r=16)),
    ("ping", "Пингвин Пинг", dict(col="#34495e", light="#f4f1ea", beak=True, ink_bg=True,
        front='<path d="M256 214 C226 156 124 168 128 268 C132 364 208 410 256 410 C304 410 380 364 384 268 C388 168 286 156 256 214 Z" fill="#f4f1ea"/>')),
    ("fox", "Лиса Фыся", dict(col="#e8813a", light="#fbeee0",
        back=P("M114 240 L98 62 Q106 52 120 60 L240 162 Z", "#e8813a", 10) + P("M398 240 L414 62 Q406 52 392 60 L272 162 Z", "#e8813a", 10)
        + '<path d="M126 196 L118 96 L196 158 Z" fill="#3b3a38"/><path d="M386 196 L394 96 L316 158 Z" fill="#3b3a38"/>',
        front='<path d="M98 296 Q172 304 256 384 Q340 304 414 296 Q402 426 256 430 Q110 426 98 296 Z" fill="#fbeee0"/>' + E(256, 326, 17, 12, INK, 0),
        mouth_y=362)),
    ("panda", "Панда Бао", dict(col="#fbfaf6", light="#ffffff", panda=True,
        back=C(136, 162, 52, "#3b3a38", 10) + C(376, 162, 52, "#3b3a38", 10),
        front=E(256, 330, 16, 11, INK, 0), mouth_y=360)),
    ("duck", "Утёнок Кря", dict(col="#f6cf45", light="#fff1b8", beak=True,
        back=P("M248 162 q-16 -60 16 -80 q-2 36 16 42 q-22 8 -32 38 z", "#f6cf45", 8))),
    ("bear", "Мишка Топа", dict(col="#9a6a44", light="#e2c4a2",
        back=C(136, 168, 50, "#9a6a44", 10) + C(376, 168, 50, "#9a6a44", 10) + dot(136, 172, 24, "#e2c4a2") + dot(376, 172, 24, "#e2c4a2"),
        front=E(256, 346, 80, 58, "#e2c4a2", 0) + E(256, 320, 19, 14, INK, 0), mouth_y=364)),
    ("zayka", "Зайка Пуша", dict(col="#f4efe9", light="#ffffff",
        back=E(196, 118, 42, 96, "#f4efe9", 10, -10) + E(316, 118, 42, 96, "#f4efe9", 10, 10)
        + f'<ellipse cx="196" cy="124" rx="20" ry="66" fill="#f6b8c1" transform="rotate(-10 196 124)"/><ellipse cx="316" cy="124" rx="20" ry="66" fill="#f6b8c1" transform="rotate(10 316 124)"/>',
        front=E(256, 318, 14, 10, "#e8737c", 0), mouth_y=346, rest="w")),
    ("kva", "Лягушонок Ква", dict(col="#7cc35a", light="#c8e8a6", head=(256, 310, 172, 124), eyes_at=(176, 330, 174),
        back=C(176, 178, 64, "#7cc35a", 10) + C(336, 178, 64, "#7cc35a", 10), mouth_y=356, blush_y=334)),
    ("uhu", "Совёнок Уху", dict(col="#a77b52", light="#f1dfc4", owl=True,
        back=P("M120 214 L104 96 L210 160 Z", "#a77b52", 10) + P("M392 214 L408 96 L302 160 Z", "#a77b52", 10),
        front=C(194, 274, 60, "#f1dfc4", 8) + C(318, 274, 60, "#f1dfc4", 8)
        + '<path d="M150 380 q20 -14 40 0 M230 396 q20 -14 40 0 M310 380 q20 -14 40 0" fill="none" stroke="#7e5a38" stroke-width="8" stroke-linecap="round"/>')),
    ("yozh", "Ёжик Колючка", dict(col="#f0d2a8", light="#f8e6c8", spikes=True,
        front=E(256, 322, 17, 12, INK, 0), mouth_y=354)),
]

MOODS = [  # id, название, глаза, рот, сзади, спереди
    ("rad", "Радость", "happy", "grin", "", ""),
    ("love", "Влюблён", "heart", "smile", "LOVE", ""),
    ("cool", "Круто", "cool", "smile", "", ""),
    ("wink", "Подмигивает", "wink", "tongue", "", ""),
    ("lol", "До слёз", "happy", "grin", "", "LOL"),
    ("sad", "Грустит", "sad", "sad", "", "SAD"),
    ("wow", "Вау", "wow", "o", "", ""),
    ("sleep", "Спит", "closed", "flat", "", "ZZ"),
    ("angry", "Злится", "angry", "flat", "", "ANGRY"),
    ("party", "Праздник", "happy", "grin", "CONF", "HAT"),
]


def spikes():
    pts = []
    n = 26
    for i in range(n * 2):
        a = math.pi * i / n
        rr = 214 if i % 2 == 0 else 166
        pts.append(f"{256 + rr * math.cos(a):.1f},{292 + rr * .9 * math.sin(a):.1f}")
    return f'<polygon points="{" ".join(pts)}" fill="#7a5a3c" stroke="{INK}" stroke-width="10" stroke-linejoin="round"/>'


def head(c, eyes_kind, mouth_kind, back="", front=""):
    hx, hy, hrx, hry = c.get("head", (HX, HY, HRX, HRY))
    lx, rx, ly = c.get("eyes_at", (LX, RX, LY))
    my = c.get("mouth_y", 340)
    out = back
    if c.get("spikes"):
        out += spikes()
    out += c.get("back", "")
    out += E(hx, hy, hrx, hry, c["col"], 11)
    out += c.get("front", "")
    ink, white = INK, "#fff"
    if c.get("panda"):
        out += "".join(f'<ellipse cx="{x}" cy="{ly + 4}" rx="38" ry="46" fill="#3b3a38" transform="rotate({r} {x} {ly})"/>' for x, r in ((lx, 24), (rx, -24)))
        if eyes_kind in ("happy", "closed", "wink", "sad", "angry", "dot"):
            ink, white = "#fff", "#3b3a38"
    out += eyes(eyes_kind, lx, ly, rx, ly, r=c.get("r", 18), ink=ink, white=white)
    if c.get("beak"):
        out += beak(mouth_kind, y=338)
    elif c.get("owl"):
        out += P("M236 316 L276 316 L256 352 Z", "#f29a38", 7)
    else:
        out += mouth(mouth_kind, y=my)
    by = c.get("blush_y", 336)
    out += f'<ellipse cx="{hx - 112}" cy="{by}" rx="22" ry="13" fill="{PINK}" opacity=".9"/><ellipse cx="{hx + 112}" cy="{by}" rx="22" ry="13" fill="{PINK}" opacity=".9"/>'
    return out + front


def mood_extra(code, lx, rx, ly):
    return {"": "", "LOVE": heart(70, 96, 36, "#e2474f") + heart(446, 80, 30, "#f07a83"),
            "LOL": tears([(lx - 34, ly + 10), (rx + 34, ly + 10)]), "SAD": tears([(lx, ly + 34), (rx, ly + 34)]),
            "ZZ": zz(372, 150), "ANGRY": anger(420, 110), "CONF": CONFETTI, "HAT": hat()}[code]


def characters():
    out = []
    # Кит Нуви — у него своё тело из stickers_gen
    wm = {"rad": ("happy", "grin"), "love": ("heart", "smile"), "cool": ("cool", "smile"), "wink": ("wink", "tongue"), "lol": ("happy", "grin"),
          "sad": ("sad", "sad"), "wow": ("wow", "o"), "sleep": ("closed", "flat"), "angry": ("angry", "flat"), "party": ("happy", "grin")}
    items = []
    for mid, name, _, _, b, f in MOODS:
        e, m = wm[mid]
        extra_b = mood_extra(b, 0, 0, 0) if b != "HAT" else ""
        extra_f = {"LOL": tears([(276, 262), (404, 258)]), "SAD": tears([(300, 280), (380, 276)]), "ZZ": zz(380, 130),
                   "ANGRY": anger(440, 140), "HAT": hat(330, 30, 10), "": ""}[f]
        svg = whale(eyes=e, mouth=m, extra_back=extra_b, extra_front=extra_f)
        items.append((f"nuvi-{mid}", f"Нуви: {name.lower()}", f'<g transform="translate(-14 12) scale(1.06)">{svg}</g>'))
    out.append(("Кит Нуви", items))
    for slug, title, c in CHARS:
        lx, rx, ly = c.get("eyes_at", (LX, RX, LY))
        items = []
        for mid, name, e, m, b, f in MOODS:
            if c.get("rest") and mid in ("rad",) and False:
                m = c["rest"]
            svg = head(c, e, m, back=mood_extra(b, lx, rx, ly), front=mood_extra(f, lx, rx, ly))
            items.append((f"{slug}-{mid}", f"{title.split()[-1]}: {name.lower()}", svg))
        out.append((title, items))
    return out


# ------------------------------------------------------------------ предметы
HEART = "M256 440 C120 350 56 270 76 184 C96 98 204 88 256 162 C308 88 416 98 436 184 C456 270 392 350 256 440 Z"


def big_heart(col):
    return P(HEART, col, 12) + shine("M136 176 q18 -40 62 -38")


def signs():
    hearts = [("red", "Красное сердце", "#e2474f"), ("pink", "Розовое сердце", "#f39ab4"), ("orange", "Оранжевое сердце", "#f59a3a"),
              ("yellow", "Жёлтое сердце", "#f6cf45"), ("green", "Зелёное сердце", "#5cb85c"), ("blue", "Синее сердце", "#4a8cc0"),
              ("purple", "Фиолетовое сердце", "#9b6bc4"), ("black", "Чёрное сердце", "#3b3a38"), ("white", "Белое сердце", "#f7f4ee")]
    items = [(f"heart-{k}", n, big_heart(c)) for k, n, c in hearts]
    items += [
        ("heart-broken", "Разбитое сердце", P(HEART, "#e2474f", 12) + f'<path d="M256 162 l-30 70 l46 44 l-34 70 l18 94" {S(14, "#fff")}/><path d="M256 162 l-30 70 l46 44 l-34 70 l18 94" {S(5)}/>'),
        ("heart-sparkle", "Сияющее сердце", big_heart("#f07a83") + sparkle(420, 110, 2.2) + sparkle(90, 380, 1.5) + sparkle(440, 380, 1.2, "#fff")),
        ("heart-two", "Два сердца", f'<g transform="translate(80 -40) scale(.62)">{P(HEART, "#f39ab4", 16)}</g><g transform="translate(-10 120) scale(.72)">{P(HEART, "#e2474f", 14)}</g>'),
        ("star", "Звезда", star(256, 266, 220, "#f6cf45", 12) + shine("M196 210 l30 -50")),
        ("star-pink", "Розовая звезда", star(256, 266, 220, "#f39ab4", 12) + shine("M196 210 l30 -50")),
        ("star-shoot", "Падающая звезда", f'<path d="M80 440 L250 280 M60 360 L210 250 M160 470 L290 330" {S(22, "#f6cf45")}/>' + star(330, 200, 150, "#f6cf45", 12)),
        ("sparkle", "Искра", P("M256 50 C278 200 312 234 462 256 C312 278 278 312 256 462 C234 312 200 278 50 256 C200 234 234 200 256 50 Z", "#f6cf45", 12)
         + P("M410 60 C416 100 424 108 464 114 C424 120 416 128 410 168 C404 128 396 120 356 114 C396 108 404 100 410 60 Z", "#f6cf45", 7)),
        ("sparkle-blue", "Голубая искра", P("M256 50 C278 200 312 234 462 256 C312 278 278 312 256 462 C234 312 200 278 50 256 C200 234 234 200 256 50 Z", "#8fd0f0", 12)),
        ("fire", "Огонь", P("M256 460 C146 460 90 386 98 300 C106 216 176 186 178 96 C232 140 256 194 250 250 C282 220 292 176 284 132 C370 184 428 266 416 340 C404 412 344 460 256 460 Z", "#f57d2c", 12)
         + P("M256 446 C200 446 176 404 184 360 C192 318 232 300 238 258 C274 300 304 322 322 362 C338 404 312 446 256 446 Z", "#f6cf45", 0)),
        ("bolt", "Молния", P("M296 44 L112 292 H240 L198 468 L400 206 H274 L334 44 Z", "#f6cf45", 12) + shine("M290 80 L190 230")),
        ("gem", "Алмаз", P("M146 110 H366 L458 214 L256 444 L54 214 Z", "#7fd0f0", 12)
         + f'<path d="M54 214 H458 M146 110 L196 214 L256 444 L316 214 L366 110 M196 214 L256 110 L316 214" {S(7)}/>'),
        ("gem-pink", "Розовый алмаз", P("M146 110 H366 L458 214 L256 444 L54 214 Z", "#f39ab4", 12)
         + f'<path d="M54 214 H458 M146 110 L196 214 L256 444 L316 214 L366 110 M196 214 L256 110 L316 214" {S(7)}/>'),
        ("crown", "Корона", P("M80 370 L56 150 L170 256 L256 98 L342 256 L456 150 L432 370 Z", "#f2c14e", 12) + P("M80 368 h352 v62 h-352 z", "#e0a526", 12)
         + C(256, 300, 26, "#e2474f", 8) + C(150, 316, 18, "#4a8cc0", 7) + C(362, 316, 18, "#5cb85c", 7) + C(56, 150, 18, "#f2c14e", 7) + C(256, 98, 20, "#f2c14e", 7) + C(456, 150, 18, "#f2c14e", 7)),
        ("crown-silver", "Серебряная корона", P("M80 370 L56 150 L170 256 L256 98 L342 256 L456 150 L432 370 Z", "#d5dde4", 12) + P("M80 368 h352 v62 h-352 z", "#a9b6c2", 12)
         + C(256, 300, 26, "#4a8cc0", 8) + C(150, 316, 18, "#9b6bc4", 7) + C(362, 316, 18, "#9b6bc4", 7)),
        ("cup", "Кубок", P("M150 130 C70 120 64 250 168 260 M362 130 C442 120 448 250 344 260", "none", 16)
         + P("M146 76 H366 V196 C366 280 316 326 256 326 C196 326 146 280 146 196 Z", "#f2c14e", 12) + P("M226 322 h60 v58 h-60 z", "#e0a526", 10)
         + P("M164 380 h184 v66 h-184 z", "#b5562f", 12) + star(256, 190, 60, "#fff6d0", 7)),
        ("medal", "Золотая медаль", P("M150 40 L224 210 L282 210 L208 40 Z", "#4a8cc0", 10) + P("M362 40 L288 210 L230 210 L304 40 Z", "#e2474f", 10)
         + C(256, 320, 130, "#f2c14e", 12) + C(256, 320, 88, "#e0a526", 7) + star(256, 324, 60, "#fff6d0", 7)),
        ("medal-silver", "Серебряная медаль", P("M150 40 L224 210 L282 210 L208 40 Z", "#4a8cc0", 10) + P("M362 40 L288 210 L230 210 L304 40 Z", "#4a8cc0", 10)
         + C(256, 320, 130, "#d5dde4", 12) + C(256, 320, 88, "#a9b6c2", 7) + star(256, 324, 60, "#fff", 7)),
        ("bubble-heart", "Сообщение с сердцем", P("M90 90 H422 Q462 90 462 130 V316 Q462 356 422 356 H220 L130 440 L144 356 H90 Q50 356 50 316 V130 Q50 90 90 90 Z", "#fff", 12)
         + f'<g transform="translate(128 54) scale(.5)">{P(HEART, "#e2474f", 22)}</g>'),
    ]
    return items


def nature():
    rays = "".join(f'<path d="M{256 + 150 * math.cos(a):.0f} {256 + 150 * math.sin(a):.0f} L{256 + 214 * math.cos(a):.0f} {256 + 214 * math.sin(a):.0f}" {S(24, INK)}/>'
                   f'<path d="M{256 + 150 * math.cos(a):.0f} {256 + 150 * math.sin(a):.0f} L{256 + 214 * math.cos(a):.0f} {256 + 214 * math.sin(a):.0f}" {S(10, "#f6cf45")}/>'
                   for a in [i * math.pi / 6 for i in range(12)])
    face = eyes("happy", 214, 248, 298, 248, r=14) + mouth("smile", 256, 296) + f'<ellipse cx="190" cy="294" rx="18" ry="11" fill="{PINK}"/><ellipse cx="322" cy="294" rx="18" ry="11" fill="{PINK}"/>'
    petals = lambda n, R, rx, ry, col: "".join(E(256 + R * math.cos(2 * math.pi * i / n), 236 + R * math.sin(2 * math.pi * i / n), rx, ry, col, 8, 360 * i / n + 90) for i in range(n))
    cloud = [(170, 300, 86), (262, 236, 108), (352, 300, 80), (256, 324, 86), (120, 340, 52), (400, 342, 52)]
    flake = "".join(f'<path d="M256 256 L{256 + 200 * math.cos(a):.0f} {256 + 200 * math.sin(a):.0f} M{256 + 120 * math.cos(a) + 50 * math.cos(a + 2.4):.0f} {256 + 120 * math.sin(a) + 50 * math.sin(a + 2.4):.0f} L{256 + 120 * math.cos(a):.0f} {256 + 120 * math.sin(a):.0f} L{256 + 120 * math.cos(a) + 50 * math.cos(a - 2.4):.0f} {256 + 120 * math.sin(a) + 50 * math.sin(a - 2.4):.0f}" ' for a in [i * math.pi / 3 - math.pi / 2 for i in range(6)])
    rainbow = (f'<path d="M66 400 A190 190 0 0 1 446 400" {S(150, INK).replace("stroke-linecap=\"round\"", "stroke-linecap=\"butt\"")}/>'
               + "".join(f'<path d="M{256 - r} 400 A{r} {r} 0 0 1 {256 + r} 400" fill="none" stroke="{c}" stroke-width="34"/>' for r, c in ((246, "#e2474f"), (212, "#f6cf45"), (178, "#5cb85c"), (144, "#4a8cc0")))
               + blob([(96, 404, 46), (150, 420, 40), (52, 424, 34)], "#fff", 9) + blob([(416, 404, 46), (362, 420, 40), (460, 424, 34)], "#fff", 9))
    return [
        ("sun", "Солнышко", rays + C(256, 256, 130, "#f6cf45", 12) + face),
        ("moon", "Месяц", P("M330 62 C196 74 110 180 122 296 C134 410 252 466 368 430 C262 398 210 316 220 234 C230 152 280 92 330 62 Z", "#f6cf45", 12)
         + f'<path d="M182 262 q16 14 32 0" {S(9)}/>' + sparkle(380, 150, 2) + sparkle(430, 290, 1.2)),
        ("cloud", "Облачко", blob(cloud, "#fff", 12) + eyes("dot", 216, 300, 300, 300, r=13) + mouth("smile", 258, 336)),
        ("rain", "Дождик", f'<g transform="translate(0 -70)">{blob(cloud, "#dce7ef", 12)}</g>'
         + "".join(P(f"M{x} {y} q-16 30 0 42 q16 -12 0 -42 z", "#4a8cc0", 7) for x, y in ((170, 360), (256, 390), (342, 360)))),
        ("snow", "Снежинка", f'<path d="{" ".join(p.split("\"")[1] for p in flake.split("<path")[1:])}" {S(44, INK)}/>'
         + f'<path d="{" ".join(p.split("\"")[1] for p in flake.split("<path")[1:])}" {S(24, "#a9d6f5")}/>'),
        ("rainbow", "Радуга", rainbow),
        ("daisy", "Ромашка", petals(10, 120, 44, 78, "#fff") + C(256, 236, 74, "#f6cf45", 10) + f'<path d="M256 330 V470" {S(16)}/>'.replace(INK, "#3c9a5f") if False else
         f'<path d="M256 300 Q270 400 250 470" {S(28, INK)}/><path d="M256 300 Q270 400 250 470" {S(14, "#3c9a5f")}/>' + petals(10, 124, 44, 80, "#fff") + C(256, 236, 74, "#f6cf45", 10)),
        ("tulip", "Тюльпан", f'<path d="M256 300 V470" {S(28, INK)}/><path d="M256 300 V470" {S(14, "#3c9a5f")}/>'
         + P("M256 450 C180 440 150 360 170 320 C210 350 240 400 256 450 Z", "#5cb85c", 9) + P("M256 450 C332 440 362 360 342 320 C302 350 272 400 256 450 Z", "#5cb85c", 9)
         + P("M150 90 L206 170 L256 64 L306 170 L362 90 C384 236 340 314 256 314 C172 314 128 236 150 90 Z", "#e2474f", 12)),
        ("sunflower", "Подсолнух", petals(14, 150, 34, 70, "#f6cf45") + C(256, 236, 104, "#7a4a28", 11)
         + "".join(dot(256 + r * math.cos(a), 236 + r * math.sin(a), 8, "#4a2c16") for r in (40, 74) for a in [i * math.pi / 4 + r for i in range(8)])),
        ("leaf", "Кленовый лист", P("M256 52 L292 150 L352 118 L332 202 L436 190 L392 252 L446 292 L332 304 L354 386 L270 334 L266 464 L246 464 L242 334 L158 386 L180 304 L66 292 L120 252 L76 190 L180 202 L160 118 L220 150 Z", "#e8642c", 11)
         + f'<path d="M256 150 V440 M256 300 L170 240 M256 300 L342 240" {S(6)}/>'),
        ("clover", "Клевер", f'<path d="M256 256 Q300 380 360 460" {S(28, INK)}/><path d="M256 256 Q300 380 360 460" {S(14, "#3c9a5f")}/>'
         + "".join(f'<g transform="rotate({a} 256 256) translate(256 152) scale(.42) translate(-256 -270)">{P(HEART, "#5cb85c", 24)}</g>' for a in (0, 90, 180, 270))),
        ("mushroom", "Мухомор", P("M196 270 h120 C326 350 340 420 306 440 H206 C172 420 186 350 196 270 Z", "#f7efdc", 11)
         + P("M58 290 C58 150 150 76 256 76 C362 76 454 150 454 290 Q256 330 58 290 Z", "#e2474f", 12)
         + dot(160, 200, 26, "#fff") + dot(268, 140, 30, "#fff") + dot(360, 214, 24, "#fff") + dot(240, 250, 18, "#fff")),
        ("cactus", "Кактус", P("M136 380 h240 l-24 90 h-192 z", "#c8704a", 11)
         + P("M206 384 V140 C206 80 306 80 306 140 V384 Z", "#5cb85c", 11) + P("M206 300 H160 C120 300 110 270 110 240 V190 C110 160 150 160 150 190 V250 H206", "#5cb85c", 11)
         + P("M306 260 H350 C388 260 400 236 400 206 V170 C400 140 360 140 360 170 V220 H306", "#5cb85c", 11) + C(256, 82, 24, "#f39ab4", 8)),
        ("fir", "Ёлочка", P("M232 400 h48 v70 h-48 z", "#7a4a28", 10) + P("M256 60 L370 200 H310 L410 320 H330 L440 420 H72 L182 320 H102 L202 200 H142 Z", "#3c9a5f", 12)
         + star(256, 70, 50, "#f6cf45", 8) + dot(200, 360, 16, "#e2474f") + dot(320, 290, 16, "#4a8cc0") + dot(240, 250, 14, "#f6cf45") + dot(330, 390, 14, "#f39ab4")),
        ("planet", "Планета", P("M60 300 C30 340 160 340 256 310 C352 280 482 220 452 190", "none", 22)
         + C(256, 256, 150, "#9b6bc4", 12) + f'<path d="M140 210 q60 -30 120 -10 M160 320 q80 20 150 -20" {S(12, "#b996dc")}/>'
         + P("M88 262 C30 330 160 344 256 314 C352 284 482 224 424 186 C432 210 300 262 256 270 C200 280 120 290 88 262 Z", "#f6cf45", 10)),
        ("snowman", "Снеговик", C(256, 360, 110, "#fff", 12) + C(256, 186, 82, "#fff", 12) + P("M180 118 h152 v24 h-152 z", "#3b3a38", 10) + P("M206 120 V40 H306 V120 Z", "#3b3a38", 10)
         + eyes("dot", 228, 178, 284, 178, r=11) + P("M256 196 L320 210 L256 218 Z", "#f59a3a", 6) + dot(256, 330, 12, INK) + dot(256, 380, 12, INK)
         + P("M190 266 Q256 296 322 266 L330 290 Q256 320 182 290 Z", "#e2474f", 8)),
        ("drop", "Капелька", P("M256 56 C300 160 392 232 392 322 C392 402 330 456 256 456 C182 456 120 402 120 322 C120 232 212 160 256 56 Z", "#7fc3f0", 12)
         + shine("M180 320 q4 50 40 76") + eyes("dot", 214, 310, 298, 310, r=13) + mouth("smile", 256, 356)),
    ]


def food():
    return [
        ("apple", "Яблоко", f'<path d="M256 150 Q256 100 280 66" {S(16)}/>' + P("M282 96 C312 50 380 50 400 70 C370 110 320 120 282 96 Z", "#5cb85c", 9)
         + P("M256 150 C200 112 92 130 94 256 C96 384 190 454 256 424 C322 454 416 384 418 256 C420 130 312 112 256 150 Z", "#e2474f", 12) + shine("M150 220 q10 -40 50 -54")),
        ("cherry", "Вишенки", f'<path d="M170 320 Q200 160 300 70 Q310 200 352 300" {S(12)}/>' + P("M300 70 C340 40 420 50 430 90 C390 110 330 104 300 70 Z", "#5cb85c", 8)
         + C(170, 360, 86, "#c8281e", 12) + C(350, 340, 86, "#c8281e", 12) + shine("M130 340 q4 -30 30 -40") + shine("M310 320 q4 -30 30 -40")),
        ("strawberry", "Клубника", P("M256 456 C150 404 88 304 110 210 C130 150 200 140 256 160 C312 140 382 150 402 210 C424 304 362 404 256 456 Z", "#e2474f", 12)
         + "".join(f'<ellipse cx="{x}" cy="{y}" rx="7" ry="11" fill="#f6e08a"/>' for x, y in ((180, 230), (256, 240), (330, 230), (210, 300), (300, 300), (256, 360), (160, 300), (350, 300), (230, 410), (284, 410)))
         + P("M150 170 L196 140 L210 90 L256 130 L302 90 L316 140 L362 170 L300 190 L256 172 L212 190 Z", "#5cb85c", 9)),
        ("watermelon", "Арбуз", f'<g transform="rotate(-12 256 256)">{P("M56 180 A200 200 0 0 0 456 180 Z", "#3c9a5f", 12)}{P("M88 180 A168 168 0 0 0 424 180 Z", "#e2474f", 0)}'
         + "".join(f'<ellipse cx="{x}" cy="{y}" rx="9" ry="14" fill="{INK}"/>' for x, y in ((180, 230), (256, 260), (330, 230), (220, 300), (296, 300)))
         + f'<path d="M56 180 H456" {S(12)}/></g>'),
        ("banana", "Банан", P("M116 110 C84 300 230 450 430 360 C440 336 428 324 404 330 C250 362 176 262 166 126 Z", "#f6cf45", 12) + P("M116 110 l-6 -40 l40 6 l16 50 z", "#7a4a28", 8)),
        ("orange", "Апельсин", C(256, 280, 170, "#f59a3a", 12) + P("M256 112 C270 60 340 40 380 60 C350 110 300 120 256 112 Z", "#5cb85c", 9)
         + "".join(dot(256 + 110 * math.cos(a), 280 + 110 * math.sin(a), 6, "#d9772a") for a in (0.4, 1.3, 2.2, 3.4, 4.4, 5.5)) + shine("M150 230 q14 -50 60 -70")),
        ("avocado", "Авокадо", P("M256 52 C330 52 360 160 402 262 C442 384 362 460 256 460 C150 460 70 384 110 262 C152 160 182 52 256 52 Z", "#3c7a3a", 12)
         + '<path d="M256 84 C310 84 334 176 370 268 C402 370 340 428 256 428 C172 428 110 370 142 268 C178 176 202 84 256 84 Z" fill="#c8e8a6"/>' + C(256, 320, 72, "#9a5f34", 10)
         + shine("M230 300 q8 -20 24 -26", 10)),
        ("pizza", "Пицца", P("M256 456 L84 128 C200 76 312 76 428 128 Z", "#f6cf45", 12) + P("M72 104 C200 40 312 40 440 104 L426 136 C312 84 200 84 86 136 Z", "#d08a3c", 11)
         + C(220, 190, 32, "#e2474f", 8) + C(310, 230, 30, "#e2474f", 8) + C(250, 320, 26, "#e2474f", 8) + dot(300, 160, 9, "#3c9a5f") + dot(200, 270, 9, "#3c9a5f")),
        ("burger", "Бургер", P("M84 230 C84 110 428 110 428 230 Z", "#e0a050", 12) + "".join(f'<ellipse cx="{x}" cy="{y}" rx="9" ry="5" fill="#fff6d0"/>' for x, y in ((180, 170), (256, 150), (330, 176), (220, 200), (300, 206)))
         + P("M70 248 Q110 220 150 248 Q190 276 230 248 Q270 220 310 248 Q350 276 390 248 Q420 226 442 248 L442 262 H70 Z", "#5cb85c", 9)
         + P("M80 262 H432 Q450 300 432 330 H80 Q62 300 80 262 Z", "#7a4a28", 11) + P("M74 332 H438 L440 350 H72 Z", "#f6cf45", 8)
         + P("M84 350 H428 Q428 420 360 420 H152 Q84 420 84 350 Z", "#e0a050", 12)),
        ("fries", "Картошка фри", "".join(P(f"M{x} {y} h34 v260 h-34 z", "#f6cf45", 9) for x, y in ((150, 120), (198, 90), (246, 110), (294, 80), (338, 124)))
         + P("M130 250 H382 L346 460 H166 Z", "#e2474f", 12) + P("M196 330 Q256 380 316 330", "none", 10)),
        ("donut", "Пончик", P(ring(256, 256, 196, 64), "#e0a050", 12, 'fill-rule="evenodd"')
         + P("M90 230 C110 120 400 110 424 230 C440 290 404 330 380 300 C350 340 320 290 290 320 C256 340 230 300 200 330 C160 340 150 300 120 320 C90 320 80 280 90 230 Z", "#f39ab4", 9)
         + C(256, 256, 64, "none", 10) + "".join(f'<rect x="{x}" y="{y}" width="26" height="9" rx="4" fill="{c}" transform="rotate({r} {x} {y})"/>' for x, y, c, r in ((150, 200, "#4a8cc0", 30), (220, 150, "#f6cf45", -20), (330, 170, "#5cb85c", 50), (360, 250, "#fff", -30), (170, 280, "#fff", 10), (300, 330, "#4a8cc0", -40)))),
        ("cupcake", "Капкейк", P("M130 280 H382 L350 456 H162 Z", "#4a8cc0", 12) + f'<path d="M196 290 L210 450 M256 290 V450 M316 290 L302 450" {S(8)}/>'
         + blob([(150, 262, 56), (256, 230, 84), (362, 262, 56), (256, 160, 60)], "#f7d6e0", 12) + C(256, 90, 30, "#e2474f", 9)),
        ("cake", "Торт", P("M86 270 H426 V440 H86 Z", "#f7d6e0", 12) + P("M86 270 H426 V300 Q404 340 382 300 Q360 340 338 300 Q316 340 294 300 Q272 340 250 300 Q228 340 206 300 Q184 340 162 300 Q140 340 118 300 Q100 330 86 300 Z", "#fff", 9)
         + P("M86 370 H426", "none", 9) + "".join(P(f"M{x - 12} 270 V170 H{x + 12} V270 Z", c, 8) + P(f"M{x} 150 q-18 -24 0 -50 q18 26 0 50 z", "#f59a3a", 6) for x, c in ((176, "#4a8cc0"), (256, "#f6cf45"), (336, "#5cb85c")))),
        ("icecream", "Мороженое", P("M150 250 L256 470 L362 250 Z", "#e0a050", 12) + f'<path d="M180 280 L300 400 M250 260 L330 340 M226 300 L180 350" {S(7)}/>'
         + blob([(196, 240, 70), (316, 240, 70)], "#f39ab4", 12) + blob([(256, 150, 84)], "#fff2cc", 12) + C(256, 60, 22, "#e2474f", 8)),
        ("lollipop", "Леденец", f'<path d="M256 300 V480" {S(30, INK)}/><path d="M256 300 V480" {S(16, "#fff")}/>' + C(256, 200, 150, "#f39ab4", 12)
         + '<path d="M256 200 m0 0 a20 20 0 0 1 40 0 a40 40 0 0 1 -80 0 a60 60 0 0 1 120 0 a80 80 0 0 1 -160 0 a100 100 0 0 1 200 0 a120 120 0 0 1 -240 0" fill="none" stroke="#e2474f" stroke-width="16" stroke-linecap="round"/>'),
        ("candy", "Конфета", P("M150 256 L50 170 L70 256 L50 342 Z", "#f6cf45", 10) + P("M362 256 L462 170 L442 256 L462 342 Z", "#f6cf45", 10)
         + E(256, 256, 130, 100, "#e2474f", 12) + f'<path d="M190 180 Q230 256 190 330 M256 160 Q296 256 256 350 M320 180 Q360 256 320 330" {S(14, "#fff")}/>'),
        ("coffee", "Кофе", f'<path d="M200 130 q-26 -36 0 -70 M262 130 q-26 -36 0 -70 M324 130 q-26 -36 0 -70" {S(12)}/>' + E(250, 430, 200, 44, "#fff", 12)
         + P("M386 240 C460 240 460 340 380 344", "none", 18) + P("M100 170 H400 V300 C400 380 340 420 250 420 C160 420 100 380 100 300 Z", "#fff", 12)
         + E(250, 170, 150, 26, "#7a4a28", 10) + f'<g transform="translate(142 196) scale(.42)">{P(HEART, "#e2474f", 24)}</g>'),
        ("boba", "Бабл-ти", f'<path d="M290 120 L340 30" {S(34, INK)}/><path d="M290 120 L340 30" {S(18, "#f39ab4")}/>' + P("M120 130 H392 L360 460 H152 Z", "#f3d9b8", 12)
         + P("M108 110 H404 V150 H108 Z", "#fff", 10) + "".join(dot(x, y, 18, "#3b2a22") for x, y in ((180, 420), (230, 400), (280, 424), (330, 404), (200, 370), (310, 362), (256, 380)))),
        ("cookie", "Печенька", C(256, 256, 196, "#d9a060", 12) + "".join(E(x, y, 22, 18, "#5a3620", 0, r) for x, y, r in ((180, 170, 20), (310, 160, -10), (360, 280, 30), (230, 260, 0), (170, 340, -20), (290, 370, 10)))),
        ("popcorn", "Попкорн", blob([(150, 160, 56), (230, 120, 62), (310, 130, 58), (370, 180, 50), (256, 190, 60)], "#fff6d0", 12)
         + P("M120 200 H392 L360 460 H152 Z", "#fff", 12) + "".join(f'<path d="M{x} 200 L{x - 6 + (x - 256) * .1:.0f} 460" stroke="#e2474f" stroke-width="30"/>' for x in (170, 256, 342)) + P("M120 200 H392 L360 460 H152 Z", "none", 12)),
    ]


def hobby():
    return [
        ("gamepad", "Геймпад", P("M136 160 H376 C448 160 482 256 472 330 C464 394 406 404 376 352 L346 306 H166 L136 352 C106 404 48 394 40 330 C30 256 64 160 136 160 Z", "#6b7c93", 12)
         + P("M120 230 h30 v-30 h32 v30 h30 v32 h-30 v30 h-32 v-30 h-30 z", "#2b2f3a", 7) + C(360, 220, 20, "#e2474f", 7) + C(400, 260, 20, "#5cb85c", 7) + C(320, 260, 20, "#4a8cc0", 7) + C(360, 300, 20, "#f6cf45", 7)),
        ("dice", "Кубик", f'<g transform="rotate(-12 256 256)">{P("M110 80 H402 Q432 80 432 110 V402 Q432 432 402 432 H110 Q80 432 80 402 V110 Q80 80 110 80 Z", "#fff", 12)}'
         + "".join(dot(x, y, 28, "#e2474f" if (x, y) == (256, 256) else INK) for x, y in ((166, 166), (346, 166), (256, 256), (166, 346), (346, 346))) + "</g>"),
        ("palette", "Палитра", P("M256 66 C384 66 464 160 454 262 C444 344 364 334 344 374 C324 424 366 452 302 456 C160 460 56 374 58 252 C60 140 148 66 256 66 Z", "#f3d9b8", 12)
         + C(170, 190, 30, "#e2474f", 8) + C(256, 140, 30, "#f6cf45", 8) + C(350, 170, 30, "#5cb85c", 8) + C(380, 260, 26, "#4a8cc0", 8) + C(150, 300, 30, "#9b6bc4", 8) + C(250, 370, 36, "#fff", 10)),
        ("guitar", "Гитара", f'<g transform="rotate(35 256 256)">{P("M232 40 H280 V250 H232 Z", "#7a4a28", 10)}{P("M220 20 H292 V70 H220 Z", "#3b2a22", 9)}'
         + P("M256 230 C330 230 340 290 320 320 C370 340 380 450 256 460 C132 450 142 340 192 320 C172 290 182 230 256 230 Z", "#e8813a", 12)
         + C(256, 340, 30, "#3b2a22", 8) + P("M216 410 H296", "none", 12) + "</g>"),
        ("headphones", "Наушники", P("M90 320 C70 120 442 120 422 320", "none", 30) + P("M90 320 C70 120 442 120 422 320", "none", 0).replace(INK, "#4a8cc0")
         + f'<path d="M90 320 C70 120 442 120 422 320" {S(14, "#4a8cc0")}/>' + P("M60 290 H150 V440 H60 Q40 440 40 420 V310 Q40 290 60 290 Z", "#e2474f", 12) + P("M362 290 H452 Q472 290 472 310 V420 Q472 440 452 440 H362 Z", "#e2474f", 12)),
        ("mic", "Микрофон", f'<g transform="rotate(-25 256 256)">{P("M220 250 H292 L276 470 H236 Z", "#3b3a38", 12)}{C(256, 170, 104, "#c9ced6", 12)}'
         + f'<path d="M180 120 L330 240 M160 170 L320 290 M200 80 L340 190 M330 120 L180 240 M350 170 L200 290" {S(6, "#8a929e")}/>{C(256, 170, 104, "none", 12)}</g>'),
        ("note", "Музыка", P("M190 120 L420 60 V140 L190 200 Z", INK, 10) + P("M190 140 V380", "none", 22) + P("M420 80 V330", "none", 22)
         + E(150, 380, 62, 46, "#9b6bc4", 12, -20) + E(380, 330, 62, 46, "#9b6bc4", 12, -20)),
        ("camera", "Камера", P("M170 140 L196 96 H316 L342 140 Z", "#3b3a38", 10) + P("M80 140 H432 Q462 140 462 170 V400 Q462 430 432 430 H80 Q50 430 50 400 V170 Q50 140 80 140 Z", "#6b7c93", 12)
         + C(256, 284, 110, "#2b2f3a", 12) + C(256, 284, 66, "#4a8cc0", 10) + dot(230, 260, 18, "#fff") + C(400, 190, 18, "#f6cf45", 7)),
        ("book", "Книга", P("M256 140 C200 100 120 96 50 120 V420 C120 396 200 400 256 440 Z", "#fff", 12) + P("M256 140 C312 100 392 96 462 120 V420 C392 396 312 400 256 440 Z", "#fff", 12)
         + P("M40 140 V440 C120 416 200 420 256 456 C312 420 392 416 472 440 V140", "none", 12).replace('fill="none"', 'fill="none"')
         + f'<path d="M100 190 Q160 176 210 196 M100 250 Q160 236 210 256 M100 310 Q160 296 210 316 M302 196 Q352 176 412 190 M302 256 Q352 236 412 250" {S(8, "#8a929e")}/>'),
        ("pencil", "Карандаш", f'<g transform="rotate(45 256 256)">{P("M210 60 H302 V380 H210 Z", "#f6cf45", 12)}{P("M210 380 H302 L256 476 Z", "#f3d9b8", 12)}{P("M240 440 H272 L256 476 Z", INK, 6)}'
         + P("M210 30 H302 V70 H210 Z", "#c9ced6", 10) + P("M210 0 Q256 -20 302 0 V34 H210 Z", "#f39ab4", 10) + f'<path d="M240 70 V380" {S(8, "#e0a526")}/></g>'),
        ("rocket", "Ракета", f'<g transform="rotate(40 256 256)">{P("M220 380 Q256 480 292 380 Z", "#f59a3a", 9)}{P("M232 380 Q256 440 280 380 Z", "#f6cf45", 0)}'
         + P("M176 300 L120 400 L200 370 Z", "#e2474f", 10) + P("M336 300 L392 400 L312 370 Z", "#e2474f", 10)
         + P("M256 30 C340 100 350 260 312 380 H200 C162 260 172 100 256 30 Z", "#eef2f6", 12) + C(256, 200, 44, "#7fc3f0", 10) + P("M200 380 H312 V396 H200 Z", "#6b7c93", 8) + "</g>"),
        ("ufo", "НЛО", '<path d="M196 320 L120 470 H392 L316 320 Z" fill="#f6e08a" opacity=".7"/>' + P("M156 210 C156 100 356 100 356 210 Z", "#a9e0f5", 12)
         + E(256, 250, 210, 70, "#9aa6b4", 12) + dot(130, 256, 16, "#f6cf45") + dot(200, 274, 16, "#e2474f") + dot(256, 280, 16, "#5cb85c") + dot(312, 274, 16, "#e2474f") + dot(382, 256, 16, "#f6cf45")),
        ("car", "Машинка", P("M60 330 Q60 270 110 260 L160 170 Q170 150 196 150 H330 Q356 150 370 170 L420 260 Q460 270 460 330 V370 H60 Z", "#e2474f", 12)
         + P("M180 180 H246 V260 H140 Z", "#a9e0f5", 9) + P("M270 180 H336 L376 260 H270 Z", "#a9e0f5", 9) + C(150, 380, 50, "#3b3a38", 12) + C(370, 380, 50, "#3b3a38", 12)
         + dot(150, 380, 18, "#c9ced6") + dot(370, 380, 18, "#c9ced6") + E(440, 300, 14, 10, "#f6cf45", 6)),
        ("soccer", "Мяч", '<clipPath id="ball"><circle cx="256" cy="256" r="194"/></clipPath>' + C(256, 256, 200, "#fff", 12)
         + '<g clip-path="url(#ball)">' + f'<polygon points="{star_pts(256, 256, 72, 72, 5)}" fill="{INK}"/>'
         + "".join(f'<path d="M{256 + 72 * math.cos(a):.0f} {256 + 72 * math.sin(a):.0f} L{256 + 150 * math.cos(a):.0f} {256 + 150 * math.sin(a):.0f}" {S(10)}/>'
                   + f'<polygon points="{star_pts(256 + 210 * math.cos(a), 256 + 210 * math.sin(a), 70, 70, 5, math.degrees(a) + 180)}" fill="{INK}"/>' for a in [math.radians(-90 + 72 * i) for i in range(5)])
         + "</g>" + C(256, 256, 200, "none", 12)),
        ("basket", "Баскетбол", C(256, 256, 196, "#f59a3a", 12) + f'<path d="M60 256 H452 M256 60 V452 M120 112 Q210 256 120 400 M392 112 Q302 256 392 400" {S(10)}/>'),
        ("plane", "Бумажный самолётик", P("M50 250 L460 70 L330 440 L250 320 Z", "#fff", 12) + P("M250 320 L460 70 L200 290 Z", "#dce7ef", 10) + P("M200 290 L250 320 L220 400 Z", "#c9d6e2", 9)),
        ("phone", "Телефон", P("M150 40 H362 Q392 40 392 70 V442 Q392 472 362 472 H150 Q120 472 120 442 V70 Q120 40 150 40 Z", "#3b3a38", 12) + P("M144 90 H368 V410 H144 Z", "#a9e0f5", 0)
         + dot(256, 440, 14, "#8a929e") + f'<g transform="translate(146 140) scale(.43)">{P(HEART, "#e2474f", 24)}</g>'),
        ("mail", "Письмо", P("M60 120 H452 Q472 120 472 140 V380 Q472 400 452 400 H60 Q40 400 40 380 V140 Q40 120 60 120 Z", "#fff", 12) + P("M44 130 L256 290 L468 130", "none", 12)
         + f'<g transform="translate(184 210) scale(.28)">{P(HEART, "#e2474f", 36)}</g>'),
        ("bulb", "Идея", P("M206 360 H306 V420 H206 Z", "#9aa6b4", 10) + P("M222 420 H290 Q290 456 256 456 Q222 456 222 420 Z", "#6b7c93", 9)
         + P("M206 360 C206 300 120 270 120 190 C120 110 186 56 256 56 C326 56 392 110 392 190 C392 270 306 300 306 360 Z", "#f6cf45", 12)
         + f'<path d="M230 360 V280 L256 250 L282 280 V360" {S(8, "#e0a526")}/>' + shine("M170 170 q10 -50 60 -70")),
    ]


def holidays():
    return [
        ("gift", "Подарок", P("M80 210 H432 V290 H80 Z", "#e2474f", 12) + P("M100 290 H412 V450 H100 Z", "#e2474f", 12) + P("M226 210 H286 V450 H226 Z", "#f6cf45", 10)
         + P("M256 210 C200 120 120 140 150 190 C170 216 230 214 256 210 Z", "#f6cf45", 10) + P("M256 210 C312 120 392 140 362 190 C342 216 282 214 256 210 Z", "#f6cf45", 10)),
        ("balloon", "Шарик", f'<path d="M256 380 Q230 430 270 470" {S(8)}/>' + P("M240 366 H272 L256 390 Z", "#c8281e", 7)
         + P("M256 50 C370 50 420 150 410 230 C396 320 316 372 256 372 C196 372 116 320 102 230 C92 150 142 50 256 50 Z", "#e2474f", 12) + shine("M160 160 q16 -50 60 -60")),
        ("popper", "Хлопушка", P("M70 450 L200 210 L310 320 Z", "#9b6bc4", 12) + f'<path d="M130 340 L210 390 M170 270 L270 330" {S(14, "#f6cf45")}/>'
         + CONFETTI.replace("translate", "translate") + star(350, 140, 40, "#f6cf45", 7) + C(420, 260, 18, "#4a8cc0", 7) + C(270, 110, 16, "#e2474f", 7) + sparkle(430, 400, 1.6)),
        ("xmas", "Новогодняя ёлка", P("M232 400 h48 v70 h-48 z", "#7a4a28", 10) + P("M256 60 L370 200 H310 L410 320 H330 L440 420 H72 L182 320 H102 L202 200 H142 Z", "#2e8b57", 12)
         + f'<path d="M150 300 Q256 340 360 280 M120 400 Q256 440 400 380" {S(10, "#f6cf45")}/>' + star(256, 64, 56, "#f6cf45", 8)
         + C(196, 250, 18, "#e2474f", 6) + C(316, 230, 18, "#4a8cc0", 6) + C(220, 360, 18, "#f39ab4", 6) + C(340, 350, 18, "#e2474f", 6)),
        ("pumpkin", "Тыква", P("M256 120 Q250 80 280 50", "none", 18) + blob([(160, 290, 120), (352, 290, 120), (256, 290, 140)], "#f59a3a", 12)
         + f'<path d="M190 180 Q160 290 190 400 M322 180 Q352 290 322 400" {S(9, "#c9662a")}/>' + P("M200 250 L236 290 H164 Z", INK, 0) + P("M312 250 L348 290 H276 Z", INK, 0)
         + P("M180 340 Q256 400 332 340 Q256 370 180 340 Z", INK, 6)),
        ("bell", "Колокольчик", P("M256 60 C340 60 370 140 370 220 C370 300 400 340 430 370 H82 C112 340 142 300 142 220 C142 140 172 60 256 60 Z", "#f2c14e", 12)
         + C(256, 410, 40, "#e0a526", 10) + C(256, 56, 24, "#e0a526", 9) + P("M150 330 Q256 360 362 330", "none", 0) + shine("M190 140 q6 -40 40 -50")),
        ("wand", "Волшебная палочка", f'<path d="M100 440 L300 220" {S(40, INK)}/><path d="M100 440 L300 220" {S(24, "#9b6bc4")}/>' + star(330, 180, 120, "#f6cf45", 12)
         + sparkle(120, 140, 2) + sparkle(440, 380, 1.6) + sparkle(200, 60, 1.2, "#f39ab4")),
        ("ghost", "Привидение", P("M130 450 V230 C130 130 186 64 256 64 C326 64 382 130 382 230 V450 L340 418 L298 450 L256 418 L214 450 L172 418 Z", "#fff", 12)
         + eyes("dot", 210, 230, 302, 230, r=20) + mouth("o", 256, 290) + f'<ellipse cx="180" cy="290" rx="20" ry="12" fill="{PINK}"/><ellipse cx="332" cy="290" rx="20" ry="12" fill="{PINK}"/>'),
    ]


def creatures():
    return [
        ("robot", "Робот", f'<path d="M256 120 V60" {S(12)}/>' + C(256, 52, 22, "#e2474f", 8) + P("M100 120 H412 Q442 120 442 150 V370 Q442 400 412 400 H100 Q70 400 70 370 V150 Q70 120 100 120 Z", "#c9ced6", 12)
         + P("M40 210 H70 V310 H40 Z", "#9aa6b4", 10) + P("M442 210 H472 V310 H442 Z", "#9aa6b4", 10) + P("M140 190 H230 V270 H140 Z", "#7fc3f0", 9) + P("M282 190 H372 V270 H282 Z", "#7fc3f0", 9)
         + dot(185, 230, 18, INK) + dot(327, 230, 18, INK) + P("M170 320 H342 V356 H170 Z", "#fff", 9) + f'<path d="M212 320 V356 M256 320 V356 M300 320 V356" {S(6)}/>'),
        ("alien", "Инопланетянин", P("M256 50 C380 50 440 150 420 250 C400 350 320 460 256 460 C192 460 112 350 92 250 C72 150 132 50 256 50 Z", "#8fd06a", 12)
         + E(176, 250, 62, 38, INK, 0, 30) + E(336, 250, 62, 38, INK, 0, -30) + dot(160, 240, 12, "#fff") + dot(320, 240, 12, "#fff") + mouth("smile", 256, 380)),
        ("paw", "Лапка", E(256, 330, 120, 104, "#f39ab4", 12) + E(116, 196, 46, 58, "#f39ab4", 11, -20) + E(206, 120, 48, 60, "#f39ab4", 11, -6) + E(306, 120, 48, 60, "#f39ab4", 11, 6) + E(396, 196, 46, 58, "#f39ab4", 11, 20)),
        ("butterfly", "Бабочка", E(160, 180, 110, 90, "#9b6bc4", 12, -30) + E(352, 180, 110, 90, "#9b6bc4", 12, 30) + E(176, 350, 80, 70, "#f39ab4", 12, 20) + E(336, 350, 80, 70, "#f39ab4", 12, -20)
         + dot(150, 180, 30, "#f6cf45") + dot(362, 180, 30, "#f6cf45") + E(256, 270, 26, 150, "#3b3a38", 10) + f'<path d="M244 130 Q220 70 180 60 M268 130 Q292 70 332 60" {S(9)}/>'),
        ("bee", "Пчёлка", E(170, 150, 70, 90, "#dcefff", 10, -30) + E(320, 140, 70, 90, "#dcefff", 10, 20) + E(256, 300, 180, 130, "#f6cf45", 12)
         + f'<path d="M190 182 Q160 300 190 418 M270 172 Q240 300 270 428" {S(42)}/>' + E(256, 300, 180, 130, "none", 12)
         + P("M436 300 L480 310 L436 320 Z", INK, 6) + eyes("dot", 120, 280, 330, 280, r=0)[:0] + dot(116, 280, 16, INK) + dot(116, 274, 5, "#fff") + mouth("smile", 120, 330)),
        ("ladybug", "Божья коровка", C(256, 130, 80, "#3b3a38", 12) + C(256, 290, 170, "#e2474f", 12) + P("M256 120 V460", "none", 10)
         + "".join(dot(x, y, 28, "#3b3a38") for x, y in ((180, 230), (332, 230), (160, 340), (352, 340), (220, 400), (292, 400))) + dot(226, 110, 14, "#fff") + dot(286, 110, 14, "#fff")),
        ("fish", "Рыбка", P("M380 256 L470 170 V342 Z", "#f59a3a", 12) + E(240, 256, 170, 120, "#f59a3a", 12) + f'<path d="M210 146 Q180 256 210 366 M290 146 Q260 256 290 366" {S(26, "#fff")}/>'
         + E(240, 256, 170, 120, "none", 12) + dot(140, 236, 20, INK) + dot(146, 228, 7, "#fff") + mouth("smile", 120, 290)),
        ("octopus", "Осьминожка", "".join(P(f"M{x} 300 Q{x + d} 400 {x + 2 * d} 460 Q{x + 3 * d} 470 {x + 2.6 * d:.0f} 440 Q{x + d * 1.6:.0f} 380 {x + 40} 300 Z", "#9b6bc4", 10) for x, d in ((100, -20), (170, -6), (250, 6), (330, 20)))
         + P("M100 310 C70 120 160 50 256 50 C352 50 442 120 412 310 Z", "#b38ad6", 12) + eyes("dot", 206, 220, 306, 220, r=20) + mouth("smile", 256, 268)
         + f'<ellipse cx="160" cy="270" rx="20" ry="12" fill="{PINK}"/><ellipse cx="352" cy="270" rx="20" ry="12" fill="{PINK}"/>'),
        ("snail", "Улитка", P("M40 420 Q40 370 120 370 H400 Q460 370 470 300 L440 280 Q420 330 380 330 Q420 210 340 220 V370 H120 Z", "#f3d9b8", 11)
         + f'<path d="M420 296 L400 220 M450 290 L460 220" {S(9)}/>' + dot(400, 216, 14, INK) + dot(460, 216, 14, INK)
         + C(230, 260, 140, "#e8813a", 12) + '<path d="M230 260 m0 0 a24 24 0 0 1 48 0 a48 48 0 0 1 -96 0 a72 72 0 0 1 144 0 a96 96 0 0 1 -192 0" fill="none" stroke="#1f1d1a" stroke-width="10" stroke-linecap="round"/>'),
    ]


def everything():
    groups = characters()
    groups += [("Знаки", signs()), ("Природа", nature()), ("Вкусное", food()), ("Увлечения", hobby()), ("Праздники", holidays()), ("Зверушки и чудики", creatures())]
    return groups


def page(groups):
    items = "".join(f'<div class="s" id="{k}"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">'
                    f'<g filter="url(#o)"><g transform="translate(36 36) scale(.86)">{svg}</g></g></svg></div>' for _, items in groups for k, _, svg in items)
    fonts = ROOT + "/static/fonts/"
    return f'''<!doctype html><meta charset=utf-8><style>
@font-face{{font-family:Unbounded;font-weight:200 900;src:url({fonts}unbounded-latin-wght-normal.woff2) format("woff2")}}
body{{margin:0;background:transparent}} .s{{width:512px;height:512px}}</style>
<svg width="0" height="0" style="position:absolute"><filter id="o" x="-10%" y="-10%" width="120%" height="120%"><feMorphology in="SourceAlpha" operator="dilate" radius="14" result="d"/><feFlood flood-color="#fff"/><feComposite in2="d" operator="in" result="w"/><feGaussianBlur in="d" stdDeviation="7" result="b"/><feFlood flood-color="#000" flood-opacity=".18"/><feComposite in2="b" operator="in" result="sh"/><feOffset in="sh" dy="6" result="sh2"/><feMerge><feMergeNode in="sh2"/><feMergeNode in="w"/><feMergeNode in="SourceGraphic"/></feMerge></filter></svg>
{items}'''


if __name__ == "__main__":
    import subprocess
    work = sys.argv[1] if len(sys.argv) > 1 else "/tmp/status_art"
    os.makedirs(work, exist_ok=True)
    groups = everything()
    ids = [k for _, items in groups for k, _, _ in items]
    assert len(ids) == len(set(ids)), "повтор id"
    open(os.path.join(work, "page.html"), "w").write(page(groups))
    json.dump(ids, open(os.path.join(work, "ids.json"), "w"))
    js = """const {chromium}=require('playwright');(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:600,height:600}});
await p.goto('file://'+process.argv[2]+'/page.html');await p.evaluate(()=>document.fonts.ready);
for(const k of require(process.argv[2]+'/ids.json')){await p.locator('#'+k).screenshot({path:process.argv[2]+'/'+k+'.png',omitBackground:true});}
await b.close()})()"""
    open(os.path.join(work, "shoot.js"), "w").write(js)
    subprocess.run(["node", os.path.join(work, "shoot.js"), work], check=True)
    from PIL import Image
    out = os.path.join(ROOT, "static", "estatus")
    os.makedirs(out, exist_ok=True)
    for k in ids:
        Image.open(os.path.join(work, k + ".png")).resize((128, 128), Image.LANCZOS).save(os.path.join(out, k + ".webp"), "WEBP", quality=90, method=6)
    json.dump([{"title": t, "items": [[k, n] for k, n, _ in items]} for t, items in groups], open(os.path.join(out, "index.json"), "w"), ensure_ascii=False, indent=0)
    print("готово:", len(ids))
