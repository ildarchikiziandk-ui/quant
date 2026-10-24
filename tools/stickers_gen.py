"""Генератор стикеров «Кит Нуви»: SVG 512×512 → страница для рендера."""
import json, sys

INK = "#1f1d1a"
BODY = "#4a8cc0"
BODY_D = "#2f6487"
BELLY = "#dcecf7"
PINK = "#f4a3a8"

def whale(eyes="dot", mouth="smile", blush=True, color=BODY, shade=BODY_D, tilt=0, fin="down", extra_back="", extra_front=""):
    eyes_svg = {
        "dot": f'<circle cx="300" cy="248" r="15" fill="{INK}"/><circle cx="380" cy="244" r="15" fill="{INK}"/><circle cx="305" cy="242" r="5" fill="#fff"/><circle cx="385" cy="238" r="5" fill="#fff"/>',
        "happy": f'<path d="M282 252 q18 -24 36 0" {S(9)}/><path d="M362 248 q18 -24 36 0" {S(9)}/>',
        "closed": f'<path d="M282 248 q18 14 36 0" {S(9)}/><path d="M362 244 q18 14 36 0" {S(9)}/>',
        "sad": f'<circle cx="300" cy="254" r="14" fill="{INK}"/><circle cx="380" cy="250" r="14" fill="{INK}"/><circle cx="304" cy="249" r="4.5" fill="#fff"/><circle cx="384" cy="245" r="4.5" fill="#fff"/><path d="M278 226 l34 10" {S(8)}/><path d="M402 222 l-34 10" {S(8)}/>',
        "angry": f'<circle cx="302" cy="254" r="13" fill="{INK}"/><circle cx="378" cy="250" r="13" fill="{INK}"/><path d="M276 224 l40 18" {S(10)}/><path d="M404 220 l-40 18" {S(10)}/>',
        "wow": f'<circle cx="300" cy="246" r="20" fill="#fff" stroke="{INK}" stroke-width="7"/><circle cx="380" cy="242" r="20" fill="#fff" stroke="{INK}" stroke-width="7"/><circle cx="302" cy="248" r="9" fill="{INK}"/><circle cx="382" cy="244" r="9" fill="{INK}"/>',
        "heart": f'{heart(300,248,30,"#e2474f")}{heart(380,244,30,"#e2474f")}',
        "wink": f'<circle cx="300" cy="248" r="15" fill="{INK}"/><circle cx="305" cy="242" r="5" fill="#fff"/><path d="M362 246 q18 -20 36 0" {S(9)}/>',
        "think": f'<circle cx="306" cy="242" r="14" fill="{INK}"/><circle cx="386" cy="238" r="14" fill="{INK}"/><circle cx="310" cy="237" r="4.5" fill="#fff"/><circle cx="390" cy="233" r="4.5" fill="#fff"/><path d="M362 210 q20 -12 40 -4" {S(8)}/>',
        "meh": f'<path d="M284 250 h32" {S(9)}/><path d="M364 246 h32" {S(9)}/>',
        "cool": f'<path d="M268 230 h150 v14 q-6 34 -40 34 q-30 0 -34 -30 h-6 q-4 30 -34 30 q-34 0 -36 -34 z" fill="{INK}"/><path d="M288 240 l22 0" stroke="#fff" stroke-width="5" stroke-linecap="round" opacity=".6"/>',
    }[eyes]
    mouth_svg = {
        "smile": f'<path d="M322 290 q20 18 40 -2" {S(8)}/>',
        "grin": f'<path d="M314 284 q28 4 56 -4 q-6 34 -30 34 q-22 0 -26 -30 z" fill="#8f2a36" stroke="{INK}" stroke-width="7" stroke-linejoin="round"/><path d="M326 306 q14 8 30 0" fill="none" stroke="#e8737c" stroke-width="7" stroke-linecap="round"/>',
        "o": f'<ellipse cx="342" cy="300" rx="14" ry="18" fill="#8f2a36" stroke="{INK}" stroke-width="7"/>',
        "sad": f'<path d="M322 302 q20 -16 40 2" {S(8)}/>',
        "flat": f'<path d="M324 296 h36" {S(8)}/>',
        "kiss": f'<path d="M336 286 q12 6 0 12 q12 6 0 12" {S(7)}/>',
        "tongue": f'<path d="M318 288 q24 16 48 -2" {S(8)}/><path d="M338 296 q2 22 14 20 q12 -2 6 -22" fill="#e8737c" stroke="{INK}" stroke-width="6" stroke-linejoin="round"/>',
        "zz": f'<ellipse cx="342" cy="298" rx="9" ry="7" fill="{INK}"/>',
    }[mouth]
    blush_svg = f'<ellipse cx="270" cy="282" rx="18" ry="11" fill="{PINK}" opacity=".85"/><ellipse cx="410" cy="276" rx="18" ry="11" fill="{PINK}" opacity=".85"/>' if blush else ""
    fin_svg = {
        "down": f'<path d="M250 330 q-10 46 -54 56 q24 -36 14 -64 z" fill="{shade}" stroke="{INK}" stroke-width="9" stroke-linejoin="round"/>',
        "wave": f'<path d="M438 304 q52 -24 62 -96 q-50 14 -76 70 z" fill="{shade}" stroke="{INK}" stroke-width="9" stroke-linejoin="round"/><path d="M478 196 q14 -10 22 -26 M492 238 q16 -2 18 -18" fill="none" stroke="{INK}" stroke-width="6" stroke-linecap="round"/>',
        "none": "",
    }[fin]
    body = (
        # хвост
        f'<path d="M132 292 C96 280 72 252 58 214 C84 226 104 228 120 222 C110 196 112 170 124 146 C142 180 152 222 168 262 Z" fill="{shade}" stroke="{INK}" stroke-width="9" stroke-linejoin="round"/>'
        # тело
        f'<path d="M150 300 C126 220 186 152 296 150 C402 148 462 210 456 290 C450 370 380 404 296 404 C220 404 170 370 150 300 Z" fill="{color}" stroke="{INK}" stroke-width="10" stroke-linejoin="round"/>'
        # брюшко
        f'<path d="M196 352 C236 392 360 404 430 346 C418 384 368 398 300 398 C246 398 214 382 196 352 Z" fill="{BELLY}"/>'
        f'<path d="M150 300 C126 220 186 152 296 150 C402 148 462 210 456 290 C450 370 380 404 296 404 C220 404 170 370 150 300 Z" fill="none" stroke="{INK}" stroke-width="10" stroke-linejoin="round"/>'
        # блик
        f'<path d="M222 196 q40 -30 90 -26" fill="none" stroke="#fff" stroke-width="12" stroke-linecap="round" opacity=".35"/>'
    )
    return (f'<g transform="rotate({tilt} 256 280)">{extra_back}{body}{fin_svg}{blush_svg}{eyes_svg}{mouth_svg}{extra_front}</g>')

def S(w):
    return f'fill="none" stroke="{INK}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"'

def heart(x, y, s, c):
    k = s / 30
    return (f'<path transform="translate({x} {y}) scale({k})" d="M0 12 C-26 -6 -18 -30 0 -18 C18 -30 26 -6 0 12 Z" fill="{c}" stroke="{INK}" stroke-width="{6/k:.1f}" stroke-linejoin="round"/>')

def spout(c="#7fb6dd"):
    return (f'<path d="M300 150 q-2 -30 -26 -44 M300 150 q2 -30 26 -44 M300 150 v-52" fill="none" stroke="{c}" stroke-width="12" stroke-linecap="round"/>'
            f'<circle cx="268" cy="96" r="9" fill="{c}"/><circle cx="332" cy="96" r="9" fill="{c}"/><circle cx="300" cy="84" r="10" fill="{c}"/>')

def label(text, color="#1f1d1a", bg="#fff", y=468, size=58, rot=-4):
    return (f'<g transform="rotate({rot} 256 {y})"><text x="256" y="{y}" text-anchor="middle" font-family="Unbounded" font-weight="800" font-size="{size}" '
            f'fill="{color}" stroke="{bg}" stroke-width="16" stroke-linejoin="round" paint-order="stroke">{text}</text></g>')

def sparkle(x, y, s, c="#f2c14e"):
    return f'<path transform="translate({x} {y}) scale({s})" d="M0 -20 Q3 -3 20 0 Q3 3 0 20 Q-3 3 -20 0 Q-3 -3 0 -20 Z" fill="{c}" stroke="{INK}" stroke-width="{4/s:.1f}" stroke-linejoin="round"/>'

STICKERS = [
    ("privet", "Привет!", "👋", whale(eyes="happy", mouth="grin", fin="wave", extra_back=spout()) + label("Привет!")),
    ("spasibo", "Спасибо", "🙏", whale(eyes="closed", mouth="smile", extra_front=heart(440, 170, 34, "#e2474f") + sparkle(120, 120, 1.1)) + label("Спасибо")),
    ("lyublyu", "Люблю", "❤️", whale(eyes="heart", mouth="kiss", extra_back=heart(130, 120, 40, "#e2474f") + heart(420, 110, 30, "#f07a83")) + label("Люблю", color="#c6303a")),
    ("haha", "Ха-ха", "😂", whale(eyes="happy", mouth="grin", tilt=-8,
        extra_front=f'<path d="M276 268 q-10 26 -2 40 q10 6 14 -8 q2 -16 -12 -32 z" fill="#7fc3f0" stroke="{INK}" stroke-width="5"/><path d="M406 262 q12 26 4 40 q-10 6 -14 -8 q-2 -16 10 -32 z" fill="#7fc3f0" stroke="{INK}" stroke-width="5"/>') + label("Ха-ха", rot=4)),
    ("ok", "Окей", "👌", whale(eyes="wink", mouth="smile", fin="wave",
        extra_back=sparkle(110, 120, .9)) + label("Окей")),
    ("ura", "Ура!", "🎉", whale(eyes="happy", mouth="grin",
        extra_back=f'<path d="M300 152 l-34 -86 l76 20 z" fill="#f2c14e" stroke="{INK}" stroke-width="8" stroke-linejoin="round"/><circle cx="270" cy="66" r="12" fill="#e2474f" stroke="{INK}" stroke-width="6"/>'
                   + "".join(f'<rect x="{x}" y="{y}" width="16" height="9" rx="3" fill="{c}" transform="rotate({r} {x} {y})"/>' for x, y, c, r in
                             [(110, 120, "#e2474f", 30), (420, 90, "#3c9a5f", -20), (160, 70, "#2f6487", 60), (440, 170, "#f2c14e", 15), (90, 200, "#c98a1b", -40), (380, 60, "#e2474f", 45)])) + label("Ура!")),
    ("grust", "Грущу", "😢", whale(eyes="sad", mouth="sad", color="#6f9cbf", shade="#40688a",
        extra_front=f'<path d="M296 276 q-8 22 0 34 q10 4 12 -8 q0 -12 -12 -26 z" fill="#7fc3f0" stroke="{INK}" stroke-width="5"/>') + f'<path d="M130 120 q30 -30 60 0 q30 -26 56 4 q20 30 -14 40 h-96 q-34 -10 -6 -44 z" fill="#c9ced6" stroke="{INK}" stroke-width="7"/>' + "".join(f'<path d="M{x} 182 l-6 18" stroke="#5aa0d8" stroke-width="6" stroke-linecap="round"/>' for x in (150, 180, 210)) + label("Грущу", color="#40688a")),
    ("zlyus", "Злюсь", "😠", whale(eyes="angry", mouth="flat", color="#d9534f", shade="#a83a36", blush=False,
        extra_back=f'<path d="M240 140 q-12 -24 6 -40 q-2 22 14 26" fill="none" stroke="#9aa0a6" stroke-width="10" stroke-linecap="round"/><path d="M372 134 q12 -26 -4 -42 q0 22 -14 28" fill="none" stroke="#9aa0a6" stroke-width="10" stroke-linecap="round"/>') + label("Злюсь", color="#a83a36")),
    ("vau", "Вау!", "😮", whale(eyes="wow", mouth="o", extra_back=sparkle(110, 140, 1.3) + sparkle(430, 120, 1) + sparkle(150, 70, .7)) + label("Вау!")),
    ("splyu", "Сплю", "😴", whale(eyes="closed", mouth="zz", color="#5d7fa6", shade="#3c5878", blush=True,
        extra_back=f'<text x="380" y="120" font-family="Unbounded" font-weight="800" font-size="64" fill="#7fb0d3" stroke="{INK}" stroke-width="5" paint-order="stroke">z</text><text x="420" y="74" font-family="Unbounded" font-weight="800" font-size="44" fill="#7fb0d3" stroke="{INK}" stroke-width="4" paint-order="stroke">z</text>'
                   + f'<path d="M150 150 a60 60 0 1 0 70 -76 a46 46 0 1 1 -70 76 z" fill="#f2c14e" stroke="{INK}" stroke-width="7"/>') + label("Сплю", color="#3c5878")),
    ("kofe", "Кофе?", "☕", whale(eyes="dot", mouth="smile", fin="none",
        extra_front=f'<path d="M206 300 h70 v40 q0 34 -35 34 q-35 0 -35 -34 z" fill="#fff" stroke="{INK}" stroke-width="8" stroke-linejoin="round"/><path d="M276 312 q24 0 22 18 q-2 18 -24 16" fill="none" stroke="{INK}" stroke-width="8"/><path d="M216 312 h50" stroke="#8a5a2b" stroke-width="10"/>'
                    f'<path d="M228 288 q-10 -16 2 -30 M252 288 q-10 -16 2 -30" fill="none" stroke="#b3a99b" stroke-width="6" stroke-linecap="round"/>') + label("Кофе?")),
    ("ogon", "Огонь", "🔥", whale(eyes="cool", mouth="grin",
        extra_back=f'<g transform="translate(320 -96)"><path d="M86 300 C70 240 120 210 110 150 C150 180 160 220 150 250 C170 236 176 214 172 196 C206 230 210 290 176 330 Z" fill="#f59a3a" stroke="{INK}" stroke-width="8" stroke-linejoin="round"/><path d="M118 316 C110 286 132 266 132 236 C152 260 156 290 146 318 Z" fill="#f2d14e"/></g>') + label("Огонь", color="#c2410c")),
    ("obnimayu", "Обнимаю", "🤗", whale(eyes="closed", mouth="smile", fin="none",
        extra_front=f'<path d="M190 300 q-40 -40 -10 -84 q30 34 56 70 z" fill="{BODY_D}" stroke="{INK}" stroke-width="9" stroke-linejoin="round"/><path d="M450 284 q44 -36 18 -84 q-34 30 -58 66 z" fill="{BODY_D}" stroke="{INK}" stroke-width="9" stroke-linejoin="round"/>' + heart(330, 110, 30, "#e2474f")) + label("Обнимаю", size=52)),
    ("dumayu", "Думаю…", "🤔", whale(eyes="think", mouth="flat",
        extra_back=f'<circle cx="150" cy="140" r="12" fill="#fff" stroke="{INK}" stroke-width="6"/><circle cx="124" cy="104" r="18" fill="#fff" stroke="{INK}" stroke-width="6"/><path d="M60 40 h120 q22 0 22 22 v28 q0 22 -22 22 h-120 q-22 0 -22 -22 v-28 q0 -22 22 -22 z" fill="#fff" stroke="{INK}" stroke-width="7"/><text x="120" y="96" text-anchor="middle" font-family="Unbounded" font-weight="800" font-size="52" fill="{BODY_D}">?</text>') + label("Думаю…", size=52)),
    ("zhdu", "Жду", "⏳", whale(eyes="meh", mouth="flat",
        extra_back=f'<g transform="translate(440 150) rotate(12)"><path d="M-30 -60 h60 M-30 60 h60" stroke="{INK}" stroke-width="10" stroke-linecap="round"/><path d="M-22 -56 q0 40 22 56 q-22 16 -22 56 h44 q0 -40 -22 -56 q22 -16 22 -56 z" fill="#fff" stroke="{INK}" stroke-width="7"/><path d="M-12 40 q12 -14 24 0 v12 h-24 z" fill="#f2c14e"/></g>') + label("Жду")),
    ("poka", "Пока!", "👋", whale(eyes="wink", mouth="tongue", fin="wave", tilt=6, extra_back=spout("#a6c9e2")) + label("Пока!", rot=3)),
    ("pshikalka", "Пшикалка", "💦", '<g transform="translate(-46 0)">' + whale(eyes="wink", mouth="tongue", fin="none", tilt=-4,
        extra_front=(
            # плавник держит пшикалку
            f'<g transform="translate(466 412) scale(.92)">'
            f'<path d="M-30 -112 h60 v98 q0 14 -14 14 h-32 q-14 0 -14 -14 z" fill="#9fd8cf" stroke="{INK}" stroke-width="8" stroke-linejoin="round"/>'
            f'<path d="M-30 -70 h60 v28 h-60 z" fill="#fff" stroke="{INK}" stroke-width="6"/>'
            f'<path d="M-18 -64 l8 0 M-4 -64 l20 0 M-18 -52 l30 0" stroke="{BODY_D}" stroke-width="5" stroke-linecap="round"/>'
            f'<path d="M-14 -112 v-16 h28 v16" fill="#f3ece1" stroke="{INK}" stroke-width="7" stroke-linejoin="round"/>'
            f'<path d="M-22 -128 q-2 -34 22 -38 h44 q8 0 8 9 v10 q0 8 -8 8 h-22 q-6 0 -8 6 l-4 5 z" fill="#e2474f" stroke="{INK}" stroke-width="7" stroke-linejoin="round"/>'
            f'<path d="M6 -134 q14 6 12 30" fill="none" stroke="{INK}" stroke-width="7" stroke-linecap="round"/>'
            f'<rect x="52" y="-164" width="10" height="12" rx="3" fill="{INK}"/>'
            f'</g>'
            f'<path d="M420 344 q34 14 52 -12 q-24 -26 -56 -8 z" fill="{BODY_D}" stroke="{INK}" stroke-width="9" stroke-linejoin="round"/>'
            # облачко брызг
            + "".join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#bfe6fb" stroke="{INK}" stroke-width="4"/>' for x, y, r in
                      [(536, 272, 12), (550, 252, 9), (552, 288, 8), (530, 244, 6)])
            + "".join(f'<path d="M{x} {y} l10 -6" stroke="#5aa0d8" stroke-width="5" stroke-linecap="round"/>' for x, y in [(520, 296), (540, 232)])
        )) + "</g>" + label("Пшикалка", size=52)),
]

def page():
    items = "".join(f'<div class="s" id="{k}"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">'
                    f'<g filter="url(#o)"><g transform="translate(20 26) scale(.9)">{svg}</g></g></svg></div>' for k, _, _, svg in STICKERS)
    return f'''<!doctype html><meta charset=utf-8><style>
@font-face{{font-family:Unbounded;font-weight:200 900;src:url(unb-c.woff2) format("woff2");unicode-range:U+0400-045F}}
@font-face{{font-family:Unbounded;font-weight:200 900;src:url(unb-l.woff2) format("woff2");unicode-range:U+0000-00FF,U+2000-206F}}
body{{margin:0;background:transparent}} .s{{width:512px;height:512px}}</style>
<svg width="0" height="0" style="position:absolute"><filter id="o" x="-10%" y="-10%" width="120%" height="120%"><feMorphology in="SourceAlpha" operator="dilate" radius="9" result="d"/><feFlood flood-color="#fff"/><feComposite in2="d" operator="in" result="w"/><feGaussianBlur in="d" stdDeviation="6" result="b"/><feFlood flood-color="#000" flood-opacity=".18"/><feComposite in2="b" operator="in" result="sh"/><feOffset in="sh" dy="6" result="sh2"/><feMerge><feMergeNode in="sh2"/><feMergeNode in="w"/><feMergeNode in="SourceGraphic"/></feMerge></filter></svg>
{items}'''

if __name__ == "__main__":
    open(sys.argv[1], "w").write(page())
    json.dump([[k, n, e] for k, n, e, _ in STICKERS], open(sys.argv[2], "w"), ensure_ascii=False)
