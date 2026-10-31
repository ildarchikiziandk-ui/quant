"""Пять наборов стикеров (31.10.2026): «Пингвин Пинг», «Лиса Фыся», «Панда Бао», «Утёнок Кря», «Мишка Топа».
Общий «скелет» персонажа + лицо из stickers_more.py. Рендер: python3 tools/stickers_new.py <папка-вывода>
(рисует SVG на странице через Playwright и сохраняет static/stickers/<набор>/<имя>.webp 320×320)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stickers_gen import INK, S, heart, label, sparkle  # noqa: E402
from stickers_more import blush, eyes, tears  # noqa: E402

LX, LY, RX, RY = 212, 232, 300, 232  # глаза
MX, MY = 256, 284  # рот


def mouth(kind, y=MY):
    return {
        "smile": f'<path d="M{MX - 22} {y - 4} q22 20 44 0" {S(8)}/>',
        "grin": f'<path d="M{MX - 28} {y - 8} q28 6 56 -2 q-6 34 -28 34 q-22 0 -28 -32 z" fill="#8f2a36" stroke="{INK}" stroke-width="6" stroke-linejoin="round"/>',
        "o": f'<ellipse cx="{MX}" cy="{y + 4}" rx="12" ry="15" fill="#8f2a36" stroke="{INK}" stroke-width="6"/>',
        "sad": f'<path d="M{MX - 20} {y + 10} q20 -16 40 0" {S(8)}/>',
        "flat": f'<path d="M{MX - 18} {y + 2} h36" {S(8)}/>',
        "w": f'<path d="M{MX - 24} {y - 4} q12 12 24 0 q12 12 24 0" {S(7)}/>',
        "tongue": f'<path d="M{MX - 24} {y - 6} q24 18 48 0" {S(8)}/><path d="M{MX - 8} {y + 4} q2 20 12 18 q10 -2 4 -18" fill="#e8737c" stroke="{INK}" stroke-width="5"/>',
        "none": "",
    }[kind]


def zz(x, y):
    return (f'<text x="{x}" y="{y}" font-family="Unbounded" font-weight="800" font-size="56" fill="#7fb0d3" stroke="{INK}" stroke-width="5" paint-order="stroke">z</text>'
            f'<text x="{x + 36}" y="{y - 44}" font-family="Unbounded" font-weight="800" font-size="40" fill="#7fb0d3" stroke="{INK}" stroke-width="4" paint-order="stroke">z</text>')


def wave_paw(color):
    return f'<path d="M340 372 q46 -34 44 -104 q-40 12 -54 70 z" fill="{color}" stroke="{INK}" stroke-width="9" stroke-linejoin="round"/>'


def character(kind, eyes_kind="dot", mouth_kind="smile", extra_back="", extra_front="", tilt=0, cheeks=True, paw=False):
    c = CHARS[kind]
    col, dark, light = c["col"], c["dark"], c["light"]
    body = (f'<ellipse cx="256" cy="372" rx="104" ry="72" fill="{col}" stroke="{INK}" stroke-width="9"/>'
            f'<ellipse cx="256" cy="386" rx="62" ry="46" fill="{light}"/>'
            f'<ellipse cx="208" cy="436" rx="30" ry="18" fill="{c.get("feet", dark)}" stroke="{INK}" stroke-width="8"/>'
            f'<ellipse cx="304" cy="436" rx="30" ry="18" fill="{c.get("feet", dark)}" stroke="{INK}" stroke-width="8"/>')
    head = c["ears"] + f'<ellipse cx="256" cy="236" rx="128" ry="112" fill="{col}" stroke="{INK}" stroke-width="10"/>' + c.get("mask", "")
    face = ""
    if c.get("patches"):
        face += "".join(f'<ellipse cx="{x}" cy="{LY + 4}" rx="30" ry="36" fill="#3b3a38" transform="rotate({r} {x} {LY})"/>' for x, r in ((LX, 20), (RX, -20)))
        face += f'<circle cx="{LX}" cy="{LY}" r="19" fill="#fff"/><circle cx="{RX}" cy="{RY}" r="19" fill="#fff"/>'
    face += eyes(eyes_kind, LX, LY, RX, RY)
    face += c.get("nose", "")
    face += c["beak"](mouth_kind) if c.get("beak") else mouth(mouth_kind)
    if cheeks:
        face += blush(176, 270, 336, 270)
    front = wave_paw(col) if paw else ""
    return f'<g transform="rotate({tilt} 256 300)">{extra_back}{body}{head}{face}{front}{extra_front}</g>'


def _beak(color, dark):
    def draw(m):
        if m in ("grin", "o", "tongue"):
            return (f'<path d="M226 272 q30 -16 60 0 q-30 12 -60 0 z" fill="{color}" stroke="{INK}" stroke-width="6" stroke-linejoin="round"/>'
                    f'<path d="M230 286 q26 30 52 0 q-26 6 -52 0 z" fill="{dark}" stroke="{INK}" stroke-width="6" stroke-linejoin="round"/>')
        if m == "sad":
            return f'<path d="M226 280 q30 16 60 0 q-30 -18 -60 0 z" fill="{color}" stroke="{INK}" stroke-width="6" stroke-linejoin="round"/>'
        return f'<path d="M224 274 q32 -18 64 0 q-32 24 -64 0 z" fill="{color}" stroke="{INK}" stroke-width="6" stroke-linejoin="round"/>'
    return draw


CHARS = {
    "ping": {"col": "#34495e", "dark": "#22313f", "light": "#f4f1ea", "feet": "#f29a38",
             "ears": "", "mask": '<path d="M176 210 q0 -60 80 -56 q80 -4 80 56 q0 96 -80 104 q-80 -8 -80 -104 z" fill="#f4f1ea"/>',
             "beak": _beak("#f29a38", "#c9662a")},
    "fox": {"col": "#e8813a", "dark": "#b85d22", "light": "#fbeee0",
            "ears": ('<path d="M150 200 L132 76 Q140 68 152 76 L240 140 Z" fill="#e8813a" stroke="#1f1d1a" stroke-width="9" stroke-linejoin="round"/>'
                     '<path d="M362 200 L380 76 Q372 68 360 76 L272 140 Z" fill="#e8813a" stroke="#1f1d1a" stroke-width="9" stroke-linejoin="round"/>'
                     '<path d="M160 168 L150 100 L212 144 Z" fill="#3b3a38"/><path d="M352 168 L362 100 L300 144 Z" fill="#3b3a38"/>'),
            "mask": '<path d="M140 250 q60 20 116 70 q56 -50 116 -70 q-10 80 -116 92 q-106 -12 -116 -92 z" fill="#fbeee0"/>',
            "nose": '<ellipse cx="256" cy="262" rx="13" ry="9" fill="#1f1d1a"/>'},
    "panda": {"col": "#fbfaf6", "dark": "#3b3a38", "light": "#ffffff", "patches": True,
              "ears": '<circle cx="152" cy="142" r="44" fill="#3b3a38" stroke="#1f1d1a" stroke-width="9"/><circle cx="360" cy="142" r="44" fill="#3b3a38" stroke="#1f1d1a" stroke-width="9"/>',
              "nose": '<ellipse cx="256" cy="264" rx="14" ry="10" fill="#1f1d1a"/>'},
    "duck": {"col": "#f6cf45", "dark": "#e0a92a", "light": "#fff1b8", "feet": "#f29a38",
             "ears": '<path d="M250 128 q-10 -40 14 -54 q-2 26 12 30 q-18 6 -26 24 z" fill="#f6cf45" stroke="#1f1d1a" stroke-width="7" stroke-linejoin="round"/>',
             "beak": _beak("#f29a38", "#c9662a")},
    "bear": {"col": "#9a6a44", "dark": "#7a5234", "light": "#e2c4a2",
             "ears": '<circle cx="156" cy="146" r="42" fill="#9a6a44" stroke="#1f1d1a" stroke-width="9"/><circle cx="356" cy="146" r="42" fill="#9a6a44" stroke="#1f1d1a" stroke-width="9"/><circle cx="156" cy="148" r="20" fill="#e2c4a2"/><circle cx="356" cy="148" r="20" fill="#e2c4a2"/>',
             "mask": '<ellipse cx="256" cy="280" rx="56" ry="40" fill="#e2c4a2"/>',
             "nose": '<ellipse cx="256" cy="262" rx="15" ry="11" fill="#1f1d1a"/>'},
}

CONFETTI = "".join(f'<rect x="{x}" y="{y}" width="16" height="9" rx="3" fill="{c}" transform="rotate({r} {x} {y})"/>' for x, y, c, r in
                   [(100, 120, "#e2474f", 30), (420, 90, "#3c9a5f", -20), (150, 60, "#2f6487", 60), (430, 190, "#f2c14e", 15), (80, 220, "#c98a1b", -40)])


def pack(kind, prefix, phrases):
    """phrases: 10 подписей в фиксированном порядке настроений."""
    moods = [
        dict(eyes_kind="happy", mouth_kind="grin", paw=True, extra_back=sparkle(420, 120, 1)),               # привет
        dict(eyes_kind="closed", mouth_kind="smile", extra_front=heart(256, 400, 34, "#e2474f")),            # спасибо
        dict(eyes_kind="heart", mouth_kind="smile", extra_back=heart(110, 120, 34, "#e2474f") + heart(410, 110, 28, "#f07a83")),  # люблю
        dict(eyes_kind="happy", mouth_kind="tongue", tilt=-6, extra_front=tears(180, 250, 332, 250)),         # ха-ха
        dict(eyes_kind="wink", mouth_kind="smile", extra_back=sparkle(110, 130, .9)),                       # ок
        dict(eyes_kind="happy", mouth_kind="grin", extra_back=CONFETTI),                                    # ура
        dict(eyes_kind="sad", mouth_kind="sad", cheeks=False, extra_front=tears(196, 252, 316, 252)),        # грущу
        dict(eyes_kind="wow", mouth_kind="o", extra_back=sparkle(110, 140, 1.1) + sparkle(420, 130, .9)),    # вау
        dict(eyes_kind="closed", mouth_kind="flat", tilt=4, extra_back=zz(372, 130)),                       # сплю
        dict(eyes_kind="closed", mouth_kind="w", extra_back=heart(120, 120, 30, "#e2474f") + heart(400, 100, 24, "#f07a83")),  # обнимаю
    ]
    out = []
    for i, (slug, text) in enumerate(phrases):
        size = 58 if len(text) <= 7 else 48 if len(text) <= 10 else 40
        out.append((f"{prefix}-{slug}", text, character(kind, **moods[i]) + label(text, size=size, color="#c6303a" if i == 2 else INK)))
    return out


BASE = [("privet", "Привет!"), ("spasibo", "Спасибо"), ("lyublyu", "Люблю"), ("haha", "Ха-ха"), ("ok", "Окей"),
        ("ura", "Ура!"), ("grust", "Грущу"), ("vau", "Вау!"), ("splyu", "Сплю"), ("obnimayu", "Обнимаю")]


def with_(*changes):
    p = list(BASE)
    for i, slug, text in changes:
        p[i] = (slug, text)
    return p


PACKS = [
    ("ping", "Пингвин Пинг", pack("ping", "ping", with_((5, "kruto", "Круто!"), (8, "holodno", "Холодно")))),
    ("fox", "Лиса Фыся", pack("fox", "fox", with_((0, "hey", "Хей!"), (4, "hitro", "Хитро"), (5, "pobeda", "Победа!")))),
    ("panda", "Панда Бао", pack("panda", "panda", with_((4, "ladno", "Ладно"), (8, "len", "Лень…")))),
    ("duck", "Утёнок Кря", pack("duck", "duck", with_((0, "krya", "Кря!"), (5, "uii", "Уиии!")))),
    ("bear", "Мишка Топа", pack("bear", "bear", with_((4, "norm", "Норм"), (6, "obidno", "Обидно"), (9, "obnimashki", "Обнимашки")))),
]


def page():
    items = "".join(f'<div class="s" id="{k}"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">'
                    f'<g filter="url(#o)"><g transform="translate(20 26) scale(.9)">{svg}</g></g></svg></div>' for _, _, items in PACKS for k, _, svg in items)
    fonts = "/home/user/quant/static/fonts/"
    return f'''<!doctype html><meta charset=utf-8><style>
@font-face{{font-family:Unbounded;font-weight:200 900;src:url({fonts}unbounded-cyrillic-wght-normal.woff2) format("woff2");unicode-range:U+0400-045F}}
@font-face{{font-family:Unbounded;font-weight:200 900;src:url({fonts}unbounded-latin-wght-normal.woff2) format("woff2");unicode-range:U+0000-00FF,U+2000-206F}}
body{{margin:0;background:transparent}} .s{{width:512px;height:512px}}</style>
<svg width="0" height="0" style="position:absolute"><filter id="o" x="-10%" y="-10%" width="120%" height="120%"><feMorphology in="SourceAlpha" operator="dilate" radius="9" result="d"/><feFlood flood-color="#fff"/><feComposite in2="d" operator="in" result="w"/><feGaussianBlur in="d" stdDeviation="6" result="b"/><feFlood flood-color="#000" flood-opacity=".18"/><feComposite in2="b" operator="in" result="sh"/><feOffset in="sh" dy="6" result="sh2"/><feMerge><feMergeNode in="sh2"/><feMergeNode in="w"/><feMergeNode in="SourceGraphic"/></feMerge></filter></svg>
{items}'''


if __name__ == "__main__":
    import json
    import subprocess
    work = sys.argv[1] if len(sys.argv) > 1 else "/tmp/stickers_new"
    os.makedirs(work, exist_ok=True)
    open(os.path.join(work, "page.html"), "w").write(page())
    ids = [(pid, k) for pid, _, items in PACKS for k, _, _ in items]
    json.dump(ids, open(os.path.join(work, "ids.json"), "w"))
    js = """const {chromium}=require('playwright');(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:600,height:600}});
await p.goto('file://'+process.argv[2]+'/page.html');await p.evaluate(()=>document.fonts.ready);
for(const [pid,k] of require(process.argv[2]+'/ids.json')){await p.locator('#'+k).screenshot({path:process.argv[2]+'/'+k+'.png',omitBackground:true});}
await b.close()})()"""
    open(os.path.join(work, "shoot.js"), "w").write(js)
    subprocess.run(["node", os.path.join(work, "shoot.js"), work], check=True)
    from PIL import Image
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "stickers")
    for pid, k in ids:
        os.makedirs(os.path.join(root, pid), exist_ok=True)
        Image.open(os.path.join(work, k + ".png")).resize((320, 320), Image.LANCZOS).save(os.path.join(root, pid, k + ".webp"), "WEBP", quality=88, method=6)
    print("готово:", len(ids))
