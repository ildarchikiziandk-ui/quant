"""Ещё два набора стикеров: «Кот Мур» и «Капибара Капи». Использует общие детали из stickers_gen.py.
Запуск: python3 tools/stickers_more.py page.html list.json → рендер страницы в PNG (как для «Кита Нуви»)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stickers_gen import INK, PINK, S, heart, label, page as _page_unused, sparkle  # noqa: E402,F401

# ------------------------------------------------------------------ общие глаза и рты по координатам
def eyes(kind, lx, ly, rx, ry, r=14):
    dot = lambda x, y, rr=r: f'<circle cx="{x}" cy="{y}" r="{rr}" fill="{INK}"/><circle cx="{x + rr * .35:.0f}" cy="{y - rr * .4:.0f}" r="{rr * .35:.0f}" fill="#fff"/>'
    if kind == "dot":
        return dot(lx, ly) + dot(rx, ry)
    if kind == "big":  # огромные просящие глаза
        return "".join(f'<circle cx="{x}" cy="{y}" r="{r + 12}" fill="{INK}"/><circle cx="{x + 8}" cy="{y - 9}" r="9" fill="#fff"/><circle cx="{x - 8}" cy="{y + 8}" r="4" fill="#fff"/>' for x, y in ((lx, ly), (rx, ry)))
    if kind == "happy":
        return f'<path d="M{lx - 16} {ly + 6} q16 -22 32 0" {S(9)}/><path d="M{rx - 16} {ry + 6} q16 -22 32 0" {S(9)}/>'
    if kind == "closed":
        return f'<path d="M{lx - 16} {ly} q16 14 32 0" {S(9)}/><path d="M{rx - 16} {ry} q16 14 32 0" {S(9)}/>'
    if kind == "half":  # спокойные полуприкрытые
        return "".join(f'<path d="M{x - 16} {y} h32" {S(8)}/><path d="M{x - 13} {y} q13 14 26 0" fill="{INK}"/>' for x, y in ((lx, ly), (rx, ry)))
    if kind == "angry":
        return dot(lx, ly + 4, r - 2) + dot(rx, ry + 4, r - 2) + f'<path d="M{lx - 22} {ly - 22} l36 14" {S(9)}/><path d="M{rx + 22} {ry - 22} l-36 14" {S(9)}/>'
    if kind == "sad":
        return dot(lx, ly + 4) + dot(rx, ry + 4) + f'<path d="M{lx - 20} {ly - 20} l30 -8" {S(8)}/><path d="M{rx + 20} {ry - 20} l-30 -8" {S(8)}/>'
    if kind == "wow":
        return "".join(f'<circle cx="{x}" cy="{y}" r="{r + 6}" fill="#fff" stroke="{INK}" stroke-width="7"/><circle cx="{x}" cy="{y + 2}" r="{r - 5}" fill="{INK}"/>' for x, y in ((lx, ly), (rx, ry)))
    if kind == "heart":
        return heart(lx, ly, 28, "#e2474f") + heart(rx, ry, 28, "#e2474f")
    if kind == "wink":
        return dot(lx, ly) + f'<path d="M{rx - 16} {ry + 4} q16 -20 32 0" {S(9)}/>'
    if kind == "side":  # косится в сторону
        return "".join(f'<circle cx="{x}" cy="{y}" r="{r + 4}" fill="#fff" stroke="{INK}" stroke-width="6"/><circle cx="{x + 8}" cy="{y + 2}" r="{r - 6}" fill="{INK}"/>' for x, y in ((lx, ly), (rx, ry)))
    return ""


def tears(lx, ly, rx, ry):
    return "".join(f'<path d="M{x} {y} q-9 22 0 32 q10 4 12 -8 q0 -12 -12 -24 z" fill="#7fc3f0" stroke="{INK}" stroke-width="5"/>' for x, y in ((lx, ly), (rx, ry)))


def blush(lx, ly, rx, ry):
    return f'<ellipse cx="{lx}" cy="{ly}" rx="18" ry="11" fill="{PINK}" opacity=".9"/><ellipse cx="{rx}" cy="{ry}" rx="18" ry="11" fill="{PINK}" opacity=".9"/>'


# ------------------------------------------------------------------ Кот Мур
CAT, CAT_D, CAT_B = "#f2a65a", "#cf7a35", "#fde6c8"


def cat(eyes_kind="dot", mouth="w", tail=True, extra_back="", extra_front="", tilt=0, cheeks=True):
    m = {
        "w": f'<path d="M232 282 q12 12 24 0 q12 12 24 0" {S(7)}/>',
        "open": f'<path d="M236 278 q20 6 40 0 q-4 30 -20 30 q-16 0 -20 -30 z" fill="#8f2a36" stroke="{INK}" stroke-width="6" stroke-linejoin="round"/>',
        "sad": f'<path d="M236 294 q20 -16 40 0" {S(7)}/>',
        "flat": f'<path d="M238 288 h36" {S(7)}/>',
        "o": f'<ellipse cx="256" cy="292" rx="11" ry="14" fill="#8f2a36" stroke="{INK}" stroke-width="6"/>',
        "tongue": f'<path d="M232 280 q12 12 24 0 q12 12 24 0" {S(7)}/><path d="M248 288 q2 20 12 18 q10 -2 4 -18" fill="#e8737c" stroke="{INK}" stroke-width="5"/>',
    }[mouth]
    tail_svg = (f'<path d="M340 392 C420 400 446 330 410 290 C396 276 380 290 392 304 C414 330 392 368 336 360 Z" fill="{CAT}" stroke="{INK}" stroke-width="9" stroke-linejoin="round"/>'
                f'<path d="M404 300 l16 -6 M412 322 l18 2" stroke="{CAT_D}" stroke-width="8" stroke-linecap="round"/>') if tail else ""
    body = (
        f'<ellipse cx="256" cy="368" rx="104" ry="70" fill="{CAT}" stroke="{INK}" stroke-width="9"/>'
        f'<ellipse cx="256" cy="380" rx="62" ry="46" fill="{CAT_B}"/>'
        # уши
        f'<path d="M150 190 L144 82 Q150 74 160 80 L236 136 Z" fill="{CAT}" stroke="{INK}" stroke-width="9" stroke-linejoin="round"/>'
        f'<path d="M362 190 L368 82 Q362 74 352 80 L276 136 Z" fill="{CAT}" stroke="{INK}" stroke-width="9" stroke-linejoin="round"/>'
        f'<path d="M164 160 L160 104 L210 140 Z" fill="#f6b3b8"/><path d="M348 160 L352 104 L302 140 Z" fill="#f6b3b8"/>'
        # голова
        f'<ellipse cx="256" cy="236" rx="132" ry="110" fill="{CAT}" stroke="{INK}" stroke-width="10"/>'
        f'<path d="M236 132 l4 26 M256 128 v30 M276 132 l-4 26" stroke="{CAT_D}" stroke-width="9" stroke-linecap="round"/>'
        f'<path d="M126 236 l26 4 M128 262 l24 -4 M386 236 l-26 4 M384 262 l-24 -4" stroke="{CAT_D}" stroke-width="8" stroke-linecap="round"/>'
        f'<ellipse cx="256" cy="282" rx="58" ry="40" fill="{CAT_B}"/>'
        f'<path d="M248 262 h16 l-8 10 z" fill="#e8737c" stroke="{INK}" stroke-width="4" stroke-linejoin="round"/>'
        # усы
        f'<path d="M196 276 h-52 M198 290 l-48 10 M316 276 h52 M314 290 l48 10" stroke="{INK}" stroke-width="4" stroke-linecap="round" opacity=".55"/>'
        # лапки
        f'<ellipse cx="212" cy="428" rx="30" ry="20" fill="{CAT}" stroke="{INK}" stroke-width="8"/><ellipse cx="300" cy="428" rx="30" ry="20" fill="{CAT}" stroke="{INK}" stroke-width="8"/>'
    )
    face = eyes(eyes_kind, 206, 232, 306, 232) + m + (blush(178, 268, 334, 268) if cheeks else "")
    return f'<g transform="rotate({tilt} 256 300)">{extra_back}{tail_svg}{body}{face}{extra_front}</g>'


CAT_STICKERS = [
    ("mur-myau", "Мяу!", cat("happy", "open", extra_front=sparkle(420, 130, 1)) + label("Мяу!")),
    ("mur-murmur", "Мур-мур", cat("closed", "w", extra_back=heart(410, 120, 30, "#e2474f") + heart(110, 130, 24, "#f07a83")) + label("Мур-мур")),
    ("mur-spasibo", "Спасибо", cat("happy", "w", extra_front=heart(256, 410, 34, "#e2474f")) + label("Спасибо")),
    ("mur-pozhaluysta", "Ну пожалуйста", cat("big", "o", cheeks=True) + label("Ну пожалуйста", size=40)),
    ("mur-obidelsya", "Обиделся", cat("side", "flat", tail=True, tilt=-6, cheeks=False,
        extra_front=f'<path d="M160 330 q96 40 192 0" fill="none" stroke="{INK}" stroke-width="0"/>') + label("Обиделся", color="#a83a36")),
    ("mur-golodny", "Голодный", cat("big", "open",
        extra_front=f'<ellipse cx="256" cy="440" rx="80" ry="22" fill="#9aa0a6" stroke="{INK}" stroke-width="7"/><ellipse cx="256" cy="432" rx="60" ry="10" fill="#c9ced6"/>') + label("Голодный")),
    ("mur-oy-vsyo", "Ой всё", cat("closed", "flat", tilt=8,
        extra_front=f'<path d="M370 200 q30 -10 40 -40" {S(8)}/><path d="M394 150 l20 4 l-8 18" {S(8)}/>') + label("Ой всё")),
    ("mur-lyublyu", "Люблю", cat("heart", "w", extra_back=heart(110, 120, 34, "#e2474f") + heart(410, 110, 28, "#f07a83")) + label("Люблю", color="#c6303a")),
    ("mur-hihi", "Хи-хи", cat("happy", "tongue", tilt=-6, extra_front=tears(180, 250, 332, 250)) + label("Хи-хи")),
    ("mur-splyu", "Сплю", cat("closed", "w", tilt=4,
        extra_back=f'<text x="380" y="130" font-family="Unbounded" font-weight="800" font-size="56" fill="#7fb0d3" stroke="{INK}" stroke-width="5" paint-order="stroke">z</text><text x="416" y="86" font-family="Unbounded" font-weight="800" font-size="40" fill="#7fb0d3" stroke="{INK}" stroke-width="4" paint-order="stroke">z</text>') + label("Сплю", color="#3c5878")),
    ("mur-zhdu", "Жду", cat("side", "flat", extra_back=sparkle(110, 120, .8)) + label("Жду")),
    ("mur-poka", "Пока!", cat("wink", "open",
        extra_front=f'<path d="M352 360 q40 -40 30 -110 q-36 16 -46 76 z" fill="{CAT}" stroke="{INK}" stroke-width="9" stroke-linejoin="round"/>') + label("Пока!")),
]


# ------------------------------------------------------------------ Капибара Капи
KAP, KAP_D, KAP_L = "#b07d4f", "#9a6a40", "#c89668"


def eye1(kind, x, y, r=12):
    """Один глаз (капибара в профиль)."""
    if kind in ("dot",):
        return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{INK}"/><circle cx="{x + 4}" cy="{y - 5}" r="4" fill="#fff"/>'
    if kind in ("happy", "wink"):
        return f'<path d="M{x - 15} {y + 5} q15 -20 30 0" {S(8)}/>'
    if kind == "closed":
        return f'<path d="M{x - 15} {y} q15 13 30 0" {S(8)}/>'
    if kind == "half":
        return f'<path d="M{x - 15} {y} h30" {S(7)}/><path d="M{x - 12} {y} q12 12 24 0" fill="{INK}"/>'
    if kind == "wow":
        return f'<circle cx="{x}" cy="{y}" r="{r + 6}" fill="#fff" stroke="{INK}" stroke-width="6"/><circle cx="{x}" cy="{y + 1}" r="{r - 3}" fill="{INK}"/>'
    if kind == "side":
        return f'<circle cx="{x}" cy="{y}" r="{r + 4}" fill="#fff" stroke="{INK}" stroke-width="6"/><circle cx="{x - 6}" cy="{y + 2}" r="{r - 5}" fill="{INK}"/>'
    return ""


def kapi(eyes_kind="half", mouth="calm", extra_back="", extra_front="", tilt=0, orange=False, cheeks=True):
    """Капибара в профиль, смотрит вправо: «буханка» с тупой мордой."""
    m = {
        "calm": f'<path d="M404 312 q10 8 22 2" {S(6)}/>',
        "smile": f'<path d="M398 308 q14 16 30 2" {S(6)}/>',
        "open": f'<path d="M398 306 q16 4 30 -2 q0 22 -14 24 q-14 0 -16 -22 z" fill="#8f2a36" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>',
        "flat": f'<path d="M402 312 h24" {S(6)}/>',
        "o": f'<ellipse cx="414" cy="314" rx="8" ry="10" fill="#8f2a36" stroke="{INK}" stroke-width="5"/>',
        "yawn": f'<ellipse cx="412" cy="318" rx="14" ry="18" fill="#8f2a36" stroke="{INK}" stroke-width="5"/>',
    }[mouth]
    body = (
        # ножки
        "".join(f'<rect x="{x}" y="380" width="40" height="62" rx="16" fill="{KAP_D}" stroke="{INK}" stroke-width="8"/>' for x in (120, 186, 286, 340))
        # туловище-«буханка»
        + f'<path d="M80 320 Q80 200 200 196 L320 196 Q400 200 400 300 L400 340 Q400 410 320 410 L150 410 Q80 410 80 340 Z" fill="{KAP}" stroke="{INK}" stroke-width="10" stroke-linejoin="round"/>'
        # ушко
        + f'<ellipse cx="318" cy="150" rx="20" ry="16" fill="{KAP_D}" stroke="{INK}" stroke-width="7"/>'
        # голова: тупая прямоугольная морда вправо
        + f'<path d="M262 220 Q262 150 330 146 L420 150 Q458 154 458 210 L458 300 Q458 340 418 342 L320 342 Q262 340 262 280 Z" fill="{KAP}" stroke="{INK}" stroke-width="10" stroke-linejoin="round"/>'
        # нос
        + f'<path d="M434 226 q22 0 22 28 q0 26 -22 26 q-12 0 -12 -26 q0 -28 12 -28 z" fill="#4a2f1c"/>'
        + f'<path d="M442 242 q6 6 0 12" stroke="#a8754a" stroke-width="5" stroke-linecap="round" fill="none"/>'
        # блик на спине
        + f'<path d="M130 236 q40 -26 100 -28" fill="none" stroke="#fff" stroke-width="12" stroke-linecap="round" opacity=".22"/>'
        # хвостика у капибары нет — зато шёрстка
        + f'<path d="M110 300 q8 -8 16 0 M140 260 q8 -8 16 0 M180 300 q8 -8 16 0" fill="none" stroke="{KAP_D}" stroke-width="6" stroke-linecap="round"/>'
    )
    orange_svg = (f'<circle cx="360" cy="122" r="28" fill="#f59a3a" stroke="{INK}" stroke-width="7"/><path d="M360 96 q12 -16 28 -12 q-6 16 -28 12 z" fill="#3c9a5f" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>'
                  f'<circle cx="350" cy="114" r="5" fill="#fff" opacity=".6"/>') if orange else ""
    face = eye1(eyes_kind, 362, 210) + m + (f'<ellipse cx="368" cy="262" rx="20" ry="12" fill="{PINK}" opacity=".9"/>' if cheeks else "")
    return f'<g transform="rotate({tilt} 256 300) translate(-6 -10)">{extra_back}{body}{orange_svg}{face}{extra_front}</g>'


def zz(x=380, y=120):
    return (f'<text x="{x}" y="{y}" font-family="Unbounded" font-weight="800" font-size="56" fill="#7fb0d3" stroke="{INK}" stroke-width="5" paint-order="stroke">z</text>'
            f'<text x="{x + 36}" y="{y - 44}" font-family="Unbounded" font-weight="800" font-size="40" fill="#7fb0d3" stroke="{INK}" stroke-width="4" paint-order="stroke">z</text>')


KAPI_STICKERS = [
    ("kapi-spokoyno", "Спокойно", kapi("half", "calm", orange=True) + label("Спокойно")),
    ("kapi-kayf", "Кайф", kapi("closed", "smile", orange=True,
        extra_back=f'<path d="M80 420 q80 -30 176 0 q96 30 176 0 v40 h-352 z" fill="#7fc3f0" opacity=".7"/>' + sparkle(420, 150, .9) + sparkle(100, 170, .7)) + label("Кайф")),
    ("kapi-norm", "Норм", kapi("half", "flat", extra_back=sparkle(120, 140, .8)) + label("Норм")),
    ("kapi-utro", "Доброе утро", kapi("dot", "smile",
        extra_back=f'<circle cx="140" cy="110" r="44" fill="#f2c14e" stroke="{INK}" stroke-width="7"/>' + "".join(f'<path d="M{140 + 66 * c:.0f} {110 + 66 * s:.0f} l{14 * c:.0f} {14 * s:.0f}" stroke="#f2c14e" stroke-width="9" stroke-linecap="round"/>' for c, s in ((1, 0), (.7, .7), (0, 1), (-.7, .7), (.7, -.7), (0, -1), (-1, 0)))) + label("Доброе утро", size=46)),
    ("kapi-noch", "Спокойной ночи", kapi("closed", "calm",
        extra_back=f'<path d="M100 150 a60 60 0 1 0 70 -76 a46 46 0 1 1 -70 76 z" fill="#f2c14e" stroke="{INK}" stroke-width="7"/>' + zz(200, 140)) + label("Спокойной ночи", size=38)),
    ("kapi-ustal", "Устал", kapi("half", "yawn", tilt=-4, cheeks=False, extra_back=zz(190, 150)) + label("Устал", color="#6f685e")),
    ("kapi-rabotayu", "Работаю", kapi("dot", "flat",
        extra_back=f'<g transform="translate(60 70)"><rect x="0" y="40" width="150" height="100" rx="12" fill="#c9ced6" stroke="{INK}" stroke-width="8"/><rect x="14" y="54" width="122" height="72" rx="6" fill="#7fb0d3"/><path d="M50 152 h50" stroke="{INK}" stroke-width="9" stroke-linecap="round"/><path d="M75 140 v12" stroke="{INK}" stroke-width="8"/></g>') + label("Работаю")),
    ("kapi-pyatnica", "Пятница!", kapi("happy", "open", orange=True,
        extra_back="".join(f'<rect x="{x}" y="{y}" width="16" height="9" rx="3" fill="{c}" transform="rotate({r} {x} {y})"/>' for x, y, c, r in
                           [(100, 120, "#e2474f", 30), (420, 90, "#3c9a5f", -20), (150, 60, "#2f6487", 60), (430, 190, "#f2c14e", 15), (80, 220, "#c98a1b", -40)])) + label("Пятница!")),
    ("kapi-nu-i-ladno", "Ну и ладно", kapi("side", "flat", tilt=4) + label("Ну и ладно", size=46)),
    ("kapi-obnimayu", "Обнимаю", kapi("closed", "smile",
        extra_back=heart(150, 130, 36, "#e2474f") + heart(220, 90, 24, "#f07a83")) + label("Обнимаю", size=50)),
    ("kapi-ogo", "Ого", kapi("wow", "o", extra_back=sparkle(110, 140, 1.1) + sparkle(420, 130, .9)) + label("Ого!")),
    ("kapi-ok", "Ок", kapi("wink", "smile", orange=True) + label("Ок")),
]

PACKS = [("mur", "Кот Мур", CAT_STICKERS), ("kapi", "Капибара Капи", KAPI_STICKERS)]


def page():
    import stickers_gen
    stickers_gen.STICKERS = [(k, n, "", svg) for _, _, items in PACKS for k, n, svg in items]
    return stickers_gen.page()


if __name__ == "__main__":
    open(sys.argv[1], "w").write(page())
    json.dump([[pk, k, n] for pk, _, items in PACKS for k, n, _ in items], open(sys.argv[2], "w"), ensure_ascii=False)
