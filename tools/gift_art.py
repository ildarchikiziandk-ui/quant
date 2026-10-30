"""Рисует все картинки подарков в static/gifts/*.svg (64×64, единый стиль: градиенты, блик, мягкая тень).

Запуск: python tools/gift_art.py — перезаписывает файлы. Чтобы поменять подарок, правьте его функцию ниже.
"""
import os

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "gifts")


def lg(id_, *stops, x2=0, y2=1):
    s = "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in stops)
    return f'<linearGradient id="{id_}" x1="0" y1="0" x2="{x2}" y2="{y2}">{s}</linearGradient>'


def rg(id_, *stops, cx=.35, cy=.3, r=.8):
    s = "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in stops)
    return f'<radialGradient id="{id_}" cx="{cx}" cy="{cy}" r="{r}">{s}</radialGradient>'


SHADOW = '<ellipse cx="32" cy="58.5" rx="20" ry="3" fill="#0b1726" opacity=".14"/>'


def svg(defs, body, shadow=True):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs>{defs}</defs>'
            f'{SHADOW if shadow else ""}{body}</svg>')


def sparkle(x, y, s=1, c="#fff"):
    return (f'<path transform="translate({x} {y}) scale({s})" d="M0-4C.4-1.2 1.2-.4 4 0 1.2.4.4 1.2 0 4-.4 1.2-1.2.4-4 0-1.2-.4-.4-1.2 0-4z" fill="{c}"/>')


ART = {}


def gift(code):
    def deco(fn):
        ART[code] = fn
        return fn
    return deco


# ============================================================ обычные
@gift("heart")
def _():
    return svg(lg("a", (0, "#ff8fa8"), (1, "#e11d48")),
               '<path d="M32 54C16 43 7 34 7 23.5 7 16 12.8 10 20 10c5 0 9 2.8 12 7 3-4.2 7-7 12-7 7.2 0 13 6 13 13.5C57 34 48 43 32 54z" fill="url(#a)"/>'
               '<path d="M15 20c1-4 4.5-6 8-5.5" stroke="#fff" stroke-width="3" stroke-linecap="round" fill="none" opacity=".7"/>' + sparkle(50, 13, .9))


@gift("rose")
def _():
    return svg(lg("p", (0, "#fb7185"), (1, "#be123c")) + lg("g", (0, "#4ade80"), (1, "#15803d")),
               '<path d="M32 30v26" stroke="url(#g)" stroke-width="3.4" stroke-linecap="round"/>'
               '<path d="M32 46c-6-1-11-5-12-10 6 0 11 4 12 10zM32 41c5-1 9-5 10-9-5 0-9 3-10 9z" fill="url(#g)"/>'
               '<path d="M18 18c0-7 6-11 14-11s14 4 14 11c0 8-6 14-14 14s-14-6-14-14z" fill="url(#p)"/>'
               '<path d="M24 16c2-4 6-5 9-3-3 1-4 4-3 7-3 0-5-1-6-4zM32 13c4-2 9 0 10 4-3-1-6 0-8 3-1-2-2-5-2-7z" fill="#fda4af" opacity=".85"/>'
               '<path d="M26 22c2 3 9 3 12 0" stroke="#9f1239" stroke-width="1.6" fill="none" stroke-linecap="round" opacity=".6"/>')


@gift("coffee")
def _():
    return svg(lg("c", (0, "#ffffff"), (1, "#dbe4ee")) + lg("k", (0, "#a16207"), (1, "#6b3f0a")),
               '<path d="M13 26h32l-3 24a6 6 0 0 1-6 5H22a6 6 0 0 1-6-5z" fill="url(#c)"/>'
               '<path d="M45 30h3a7 7 0 0 1 0 14h-4" stroke="#cfd9e5" stroke-width="4" fill="none"/>'
               '<ellipse cx="29" cy="27" rx="15.5" ry="4" fill="url(#k)"/>'
               '<path d="M27 32c-2 4 1 5 3 3s1-5 3-3" stroke="#f5deb3" stroke-width="1.6" fill="none" stroke-linecap="round" opacity=".9"/>'
               '<path d="M23 9c-3 4 3 6 0 10M30 7c-3 4 3 6 0 10M37 9c-3 4 3 6 0 10" stroke="#94a3b8" stroke-width="2" fill="none" stroke-linecap="round" opacity=".6"/>'
               '<path d="M19 33l2 15" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/>')


@gift("balloon")
def _():
    return svg(rg("b", (0, "#7dd3fc"), (.6, "#1f6fb8"), (1, "#123f6e")),
               '<path d="M32 44c0 5-4 6-2 10" stroke="#64748b" stroke-width="1.4" fill="none"/>'
               '<ellipse cx="32" cy="24" rx="15" ry="18" fill="url(#b)"/><path d="M29 42h6l-3 4z" fill="#123f6e"/>'
               '<ellipse cx="25" cy="16" rx="4" ry="6" fill="#fff" opacity=".45" transform="rotate(-25 25 16)"/>' + sparkle(50, 12, .8, "#7dd3fc"))


@gift("cake")
def _():
    return svg(lg("t", (0, "#fff1f5"), (1, "#f9a8d4")) + lg("b", (0, "#fbcfe8"), (1, "#ec4899")),
               '<rect x="10" y="36" width="44" height="18" rx="6" fill="url(#b)"/><rect x="16" y="23" width="32" height="15" rx="5" fill="url(#t)"/>'
               '<path d="M10 41c4 0 4 4 8 4s4-4 8-4 4 4 7 4 4-4 8-4 4 4 8 4 3-3 5-4" stroke="#fff" stroke-width="3" fill="none" stroke-linecap="round"/>'
               '<circle cx="22" cy="29" r="1.6" fill="#ef4444"/><circle cx="32" cy="31" r="1.6" fill="#22c55e"/><circle cx="42" cy="29" r="1.6" fill="#3b82f6"/>'
               '<rect x="30.5" y="12" width="3" height="11" rx="1.4" fill="#60a5fa"/>'
               '<path d="M32 4c3 3 3 6 0 8-3-2-3-5 0-8z" fill="#fbbf24"/><path d="M32 7c1.4 1.5 1.4 3 0 4-1.4-1-1.4-2.5 0-4z" fill="#fff7d6"/>')


@gift("bear")
def _():
    return svg(rg("f", (0, "#e7b77d"), (1, "#a8692f")),
               '<circle cx="18" cy="15" r="7" fill="url(#f)"/><circle cx="46" cy="15" r="7" fill="url(#f)"/>'
               '<circle cx="18" cy="15" r="3.4" fill="#f5d2a8"/><circle cx="46" cy="15" r="3.4" fill="#f5d2a8"/>'
               '<ellipse cx="32" cy="44" rx="16" ry="13" fill="url(#f)"/><circle cx="32" cy="26" r="15" fill="url(#f)"/>'
               '<ellipse cx="32" cy="31" rx="7" ry="5.5" fill="#f5d2a8"/><ellipse cx="32" cy="28.5" rx="2.8" ry="2" fill="#3b2412"/>'
               '<circle cx="26" cy="23" r="2" fill="#3b2412"/><circle cx="38" cy="23" r="2" fill="#3b2412"/>'
               '<path d="M29 33c2 2 4 2 6 0" stroke="#3b2412" stroke-width="1.4" fill="none" stroke-linecap="round"/>'
               '<path d="M26 44l6 3 6-3-6-3z" fill="#e11d48"/><circle cx="32" cy="44" r="2" fill="#be123c"/>'
               '<ellipse cx="32" cy="47" rx="7" ry="5" fill="#f5d2a8" opacity=".6"/>')


@gift("star")
def _():
    return svg(lg("s", (0, "#fff3a3"), (.5, "#facc15"), (1, "#ea8a0c")),
               '<path d="M32 5l7.6 16 17.4 2.2-12.8 12.1 3.3 17.3L32 44.1 16.5 52.6l3.3-17.3L7 23.2l17.4-2.2z" fill="url(#s)" stroke="#d97706" stroke-width="1.2" stroke-linejoin="round"/>'
               '<path d="M24 24l5-.6 3-6.6" stroke="#fff" stroke-width="2.6" fill="none" stroke-linecap="round" opacity=".8"/>' + sparkle(52, 9, .9, "#fde047") + sparkle(11, 46, .6, "#fde047"))


@gift("fire")
def _():
    return svg(lg("o", (0, "#fde047"), (.45, "#f97316"), (1, "#dc2626")) + lg("i", (0, "#fff7cc"), (1, "#fbbf24")),
               '<path d="M32 56c-12 0-19-8-19-18 0-9 6-14 9-21 2 5 4 7 7 8 0-8 4-16 11-21 0 9 13 16 13 31 0 13-8 21-21 21z" fill="url(#o)"/>'
               '<path d="M32 56c-6 0-10-4-10-9 0-6 5-9 7-14 2 4 5 5 6 5 3 3 7 5 7 10 0 5-4 8-10 8z" fill="url(#i)"/>')


@gift("trophy")
def _():
    return svg(lg("g", (0, "#fff0a0"), (.5, "#f6b40e"), (1, "#c26a05")),
               '<path d="M16 12h-7v5c0 7 5 12 12 12M48 12h7v5c0 7-5 12-12 12" stroke="url(#g)" stroke-width="4" fill="none"/>'
               '<path d="M16 8h32v12c0 10-7 18-16 18S16 30 16 20z" fill="url(#g)"/>'
               '<rect x="28" y="37" width="8" height="8" fill="url(#g)"/><rect x="19" y="44" width="26" height="10" rx="3" fill="#7c4a12"/>'
               '<rect x="24" y="47" width="16" height="4" rx="1" fill="#f6b40e"/>'
               '<path d="M22 13v8c0 4 2 8 5 10" stroke="#fff" stroke-width="2.6" fill="none" stroke-linecap="round" opacity=".7"/>' + sparkle(52, 40, .7, "#fde047"))


@gift("crown")
def _():
    return svg(lg("g", (0, "#fff0a0"), (.55, "#f6b40e"), (1, "#c26a05")),
               '<path d="M8 22l12 10 12-20 12 20 12-10-5 26H13z" fill="url(#g)" stroke="#a85a05" stroke-width="1.2" stroke-linejoin="round"/>'
               '<rect x="12" y="47" width="40" height="7" rx="3" fill="url(#g)" stroke="#a85a05" stroke-width="1.2"/>'
               '<circle cx="32" cy="11" r="3.4" fill="#ef4444"/><circle cx="8" cy="21" r="2.6" fill="#fde68a"/><circle cx="56" cy="21" r="2.6" fill="#fde68a"/>'
               '<circle cx="32" cy="38" r="3.6" fill="#ef4444"/><circle cx="21" cy="40" r="2.4" fill="#22c55e"/><circle cx="43" cy="40" r="2.4" fill="#3b82f6"/>'
               '<path d="M17 28l2 13" stroke="#fff" stroke-width="2.4" stroke-linecap="round" opacity=".6"/>')


@gift("diamond")
def _():
    return svg(lg("d", (0, "#e0f7ff"), (.5, "#67d0f5"), (1, "#1f6fb8")),
               '<path d="M18 10h28l12 14-26 32L6 24z" fill="url(#d)"/>'
               '<path d="M6 24h52M18 10l6 14 8 32 8-32 6-14M24 24l8-14 8 14" stroke="#fff" stroke-width="1.4" fill="none" opacity=".75" stroke-linejoin="round"/>'
               '<path d="M18 10l6 14H6z" fill="#fff" opacity=".35"/>' + sparkle(50, 8, 1.1) + sparkle(10, 44, .7, "#bae6fd"))


@gift("rocket")
def _():
    return svg(lg("r", (0, "#ffffff"), (1, "#cbd5e1"), x2=1, y2=0) + lg("f", (0, "#fde047"), (1, "#f97316")),
               '<path d="M26 44c-2 6 0 11 6 14 6-3 8-8 6-14z" fill="url(#f)"/>'
               '<path d="M32 4c10 7 13 20 9 40H23C19 24 22 11 32 4z" fill="url(#r)"/>'
               '<path d="M23 34l-9 8 2 6 8-4zM41 34l9 8-2 6-8-4z" fill="#1f6fb8"/>'
               '<circle cx="32" cy="22" r="5" fill="#1f6fb8"/><circle cx="32" cy="22" r="3" fill="#7dd3fc"/>'
               '<path d="M27 9c3-2 7-2 10 0" stroke="#ef4444" stroke-width="3" fill="none" stroke-linecap="round"/>' + sparkle(52, 14, .8, "#fde047") + sparkle(12, 20, .6, "#7dd3fc"))


@gift("whale")
def _():
    return svg(lg("w", (0, "#7cc0f2"), (1, "#1f5d9c")),
               '<path d="M6 34c0-10 10-17 24-17 12 0 20 6 23 13l5-6c2 6 1 12-4 15 0 9-11 16-25 16C15 55 6 46 6 34z" fill="url(#w)"/>'
               '<path d="M8 40c5 8 13 11 22 11 10 0 18-4 22-11-9 4-35 4-44 0z" fill="#f2ead9"/>'
               '<circle cx="17" cy="31" r="2" fill="#0b2540"/><path d="M15 36c2 1.5 4 1.5 6 0" stroke="#0b2540" stroke-width="1.4" fill="none" stroke-linecap="round"/>'
               '<path d="M26 14c-2-4 0-8 3-9M29 13c1-4 4-6 7-5" stroke="#7dd3fc" stroke-width="2.4" fill="none" stroke-linecap="round"/>' + sparkle(52, 10, .8, "#bae6fd"))


@gift("aurora")
def _():
    return svg(lg("n", (0, "#0b1d3a"), (1, "#1f3a66")) + lg("a1", (0, "#34d399"), (1, "#22d3ee"), x2=1, y2=0) + lg("a2", (0, "#a78bfa"), (1, "#34d399"), x2=1, y2=0),
               '<rect x="6" y="8" width="52" height="46" rx="12" fill="url(#n)"/>'
               '<path d="M8 30c10-12 18 4 28-8s16-6 20-10v14c-6 4-12 0-20 8S16 38 8 40z" fill="url(#a1)" opacity=".85"/>'
               '<path d="M8 38c12-6 18 2 28-4s14-2 20-6v8c-8 4-14 0-22 5S16 46 8 46z" fill="url(#a2)" opacity=".7"/>'
               '<path d="M6 46l12-8 10 6 10-9 20 11v2a6 6 0 0 1-6 6H12a6 6 0 0 1-6-6z" fill="#0a1426"/>'
               + sparkle(16, 16, .5) + sparkle(46, 14, .6) + sparkle(30, 12, .4))


# ============================================================ коллекция (всегда, дорогие)
@gift("castle")
def _():
    return svg(lg("w", (0, "#f4f8fd"), (1, "#a8bfd8")) + lg("r", (0, "#60a5fa"), (1, "#1f4f8a")),
               '<path d="M10 54V30h8v-6h6v6h4V18h8v12h4v-6h6v6h8v24z" fill="url(#w)"/>'
               '<path d="M8 30l6-10 6 10zM22 24l5-9 5 9zM26 18l6-12 6 12zM32 24l5-9 5 9zM44 30l6-10 6 10z" fill="url(#r)"/>'
               '<path d="M27 54V44a5 5 0 0 1 10 0v10z" fill="#1f3a66"/>'
               '<rect x="14" y="36" width="4" height="6" rx="2" fill="#fbbf24"/><rect x="46" y="36" width="4" height="6" rx="2" fill="#fbbf24"/><rect x="30" y="26" width="4" height="6" rx="2" fill="#fbbf24"/>'
               '<path d="M32 6V1l6 2.5-6 2.5" fill="#ef4444"/>' + sparkle(54, 12, .8, "#fde047"))


@gift("unicorn")
def _():
    return svg(lg("m", (0, "#f472b6"), (.5, "#a78bfa"), (1, "#38bdf8")) + lg("b", (0, "#ffffff"), (1, "#dfe3f3")) + lg("h", (0, "#fff3a3"), (1, "#f6b40e")),
               '<path d="M20 58c0-12 2-20 8-26l-4-6c0-9 7-15 16-15 7 0 13 5 14 12l3 9c1 4-2 7-6 7h-6l-4 4c2 5 3 9 3 15z" fill="url(#b)"/>'
               '<path d="M38 12l4-11 2 13z" fill="url(#h)"/>'
               '<path d="M30 12c-8 2-12 9-12 17 0 7-3 13-6 18 6-2 11-7 13-13 1 5-1 10-3 14 6-3 9-9 9-15 1-5 3-9 7-12z" fill="url(#m)"/>'
               '<circle cx="44" cy="25" r="2.2" fill="#1f2937"/><circle cx="44.8" cy="24.3" r=".7" fill="#fff"/>'
               '<ellipse cx="54" cy="35" rx="1.4" ry="1.1" fill="#c4b5fd"/>'
               '<ellipse cx="47" cy="31" rx="3" ry="1.8" fill="#fbcfe8"/>'
               '<path d="M28 34l3 3" stroke="#e5e7f5" stroke-width="1.2"/>' + sparkle(56, 52, .9, "#f9a8d4") + sparkle(10, 12, .7, "#a5f3fc") + sparkle(56, 10, .6, "#fde047"))


@gift("yacht")
def _():
    return svg(lg("s", (0, "#ffffff"), (1, "#dbe7f4")) + lg("h", (0, "#1f6fb8"), (1, "#0f3d6e")) + lg("sea", (0, "#7dd3fc"), (1, "#0ea5e9")),
               '<path d="M33 6v34" stroke="#94a3b8" stroke-width="2"/>'
               '<path d="M35 8c10 6 15 18 15 30H35z" fill="url(#s)"/><path d="M31 12c-8 6-13 16-13 26h13z" fill="url(#s)" opacity=".9"/>'
               '<path d="M8 42h50l-7 10H16z" fill="url(#h)"/><path d="M14 46h38" stroke="#fbbf24" stroke-width="2"/>'
               '<path d="M4 54c5-3 9 3 14 0s9-3 14 0 9 3 14 0 9-3 14 0v4H4z" fill="url(#sea)" opacity=".85"/>'
               '<path d="M33 6l8 3-8 3" fill="#ef4444"/>')


@gift("planet")
def _():
    return svg(rg("p", (0, "#fde68a"), (.5, "#f97316"), (1, "#9a3412")) + lg("r", (0, "#e0e7ff"), (1, "#818cf8"), x2=1, y2=0),
               '<ellipse cx="32" cy="32" rx="28" ry="8" fill="none" stroke="url(#r)" stroke-width="4" transform="rotate(-18 32 32)" opacity=".55"/>'
               '<circle cx="32" cy="32" r="17" fill="url(#p)"/>'
               '<path d="M17 28c8 3 22 3 30-1M16 35c9 3 23 2 31-2" stroke="#fff" stroke-width="2" fill="none" opacity=".35"/>'
               '<path d="M6.5 40.6C14 43 39 36 57.5 23.4" stroke="url(#r)" stroke-width="4" fill="none" stroke-linecap="round"/>'
               + sparkle(10, 12, .8) + sparkle(54, 50, .7, "#c7d2fe") + sparkle(52, 9, .5))


@gift("golden_whale")
def _():
    return svg(lg("g", (0, "#fff4b0"), (.5, "#f6b40e"), (1, "#a8580a")) + rg("bg", (0, "#fff7d6"), (1, "#fde68a00"), cx=.5, cy=.5, r=.5),
               '<circle cx="32" cy="32" r="30" fill="url(#bg)"/>'
               '<path d="M6 34c0-10 10-17 24-17 12 0 20 6 23 13l5-6c2 6 1 12-4 15 0 9-11 16-25 16C15 55 6 46 6 34z" fill="url(#g)" stroke="#a8580a" stroke-width="1"/>'
               '<path d="M9 40c5 8 13 11 21 11 10 0 18-4 22-11-9 4-34 4-43 0z" fill="#fff4cf"/>'
               '<circle cx="17" cy="31" r="2" fill="#5a3205"/><path d="M15 36c2 1.5 4 1.5 6 0" stroke="#5a3205" stroke-width="1.4" fill="none" stroke-linecap="round"/>'
               '<path d="M20 22c4-2 9-3 14-2" stroke="#fff" stroke-width="2.4" fill="none" stroke-linecap="round" opacity=".7"/>'
               '<path d="M26 14c-2-4 0-8 3-9M29 13c1-4 4-6 7-5" stroke="#fbbf24" stroke-width="2.4" fill="none" stroke-linecap="round"/>'
               + sparkle(52, 10, 1.1, "#fde047") + sparkle(8, 14, .7, "#fde047") + sparkle(56, 50, .6, "#fde047"))


@gift("phoenix")
def _():
    return svg(lg("f", (0, "#fde047"), (.5, "#f97316"), (1, "#b91c1c")) + lg("t", (0, "#fbbf24"), (1, "#dc2626")),
               '<path d="M32 30C22 16 10 14 4 16c8 2 12 8 14 14-6-2-10 0-12 2 8 0 14 4 18 10z" fill="url(#f)"/>'
               '<path d="M32 30c10-14 22-16 28-14-8 2-12 8-14 14 6-2 10 0 12 2-8 0-14 4-18 10z" fill="url(#f)"/>'
               '<path d="M26 42c-2 8 0 14 6 17 6-3 8-9 6-17z" fill="url(#t)"/><path d="M29 46c-1 6 1 9 3 11 2-2 4-5 3-11z" fill="#fde047"/>'
               '<ellipse cx="32" cy="34" rx="6" ry="10" fill="url(#f)"/><circle cx="32" cy="22" r="5" fill="url(#f)"/>'
               '<path d="M32 17c-1-4 1-8 4-10-1 3 0 6 1 8z" fill="#fde047"/><path d="M36 22l5 1-5 2z" fill="#f59e0b"/><circle cx="33.5" cy="21" r="1.1" fill="#3b0d0d"/>'
               + sparkle(10, 44, .7, "#fde047") + sparkle(54, 44, .7, "#fde047"))


# ============================================================ лимитированные (по месяцам)
@gift("snowglobe")
def _():
    return svg(rg("gl", (0, "#e0f2fe"), (1, "#60a5fa")) + lg("b", (0, "#a16207"), (1, "#5c3a0a")),
               '<circle cx="32" cy="27" r="20" fill="url(#gl)" opacity=".9"/>'
               '<path d="M18 38c4-3 9-3 14 0s10 3 14 0v4a14 14 0 0 1-28 0z" fill="#fff"/>'
               '<path d="M32 18l-6 12h12z M32 24l-7 12h14z" fill="#15803d"/><rect x="31" y="35" width="2" height="3" fill="#7c2d12"/>'
               '<circle cx="22" cy="16" r="1.4" fill="#fff"/><circle cx="41" cy="14" r="1.2" fill="#fff"/><circle cx="44" cy="26" r="1" fill="#fff"/><circle cx="20" cy="28" r="1" fill="#fff"/>'
               '<path d="M20 44h24l3 10H17z" fill="url(#b)"/><path d="M19 49h26" stroke="#fbbf24" stroke-width="1.6"/>'
               '<ellipse cx="25" cy="17" rx="4" ry="6" fill="#fff" opacity=".35" transform="rotate(-30 25 17)"/>')


@gift("xmas_tree")
def _():
    return svg(lg("t", (0, "#4ade80"), (1, "#166534")),
               '<rect x="28" y="48" width="8" height="8" rx="1.5" fill="#7c2d12"/>'
               '<path d="M32 8l12 14h-6l10 12h-7l11 14H12l11-14h-7l10-12h-6z" fill="url(#t)"/>'
               '<path d="M32 4l1.8 3.7 4 .5-3 2.8.8 4-3.6-2-3.6 2 .8-4-3-2.8 4-.5z" fill="#facc15"/>'
               '<circle cx="27" cy="22" r="2" fill="#ef4444"/><circle cx="38" cy="30" r="2" fill="#3b82f6"/><circle cx="24" cy="36" r="2" fill="#facc15"/>'
               '<circle cx="40" cy="42" r="2" fill="#ef4444"/><circle cx="30" cy="44" r="2" fill="#a855f7"/>'
               '<path d="M22 32c6 3 14 3 20-1M18 45c9 3 20 3 28-1" stroke="#fde68a" stroke-width="1.4" fill="none" opacity=".8"/>')


@gift("snowman")
def _():
    return svg(rg("s", (0, "#ffffff"), (1, "#c7d7ea")),
               '<circle cx="32" cy="44" r="13" fill="url(#s)"/><circle cx="32" cy="23" r="10" fill="url(#s)"/>'
               '<rect x="23" y="8" width="18" height="4" rx="1" fill="#1f2937"/><rect x="26" y="1" width="12" height="9" rx="2" fill="#1f2937"/><rect x="26" y="6" width="12" height="2" fill="#ef4444"/>'
               '<circle cx="28.5" cy="21" r="1.4" fill="#1f2937"/><circle cx="35.5" cy="21" r="1.4" fill="#1f2937"/>'
               '<path d="M32 24l9 2-9 1.4z" fill="#f97316"/>'
               '<path d="M22 31c6 3 14 3 20 0l2 4c-4 2-6 2-8 2l1 7-4-1-1-6c-3 0-6-1-10-3z" fill="#1f6fb8"/>'
               '<circle cx="32" cy="40" r="1.4" fill="#1f2937"/><circle cx="32" cy="46" r="1.4" fill="#1f2937"/>'
               '<path d="M19 40l-9-6M45 40l9-6" stroke="#7c4a12" stroke-width="2" stroke-linecap="round"/>')


@gift("valentine")
def _():
    return svg(lg("e", (0, "#fff1f2"), (1, "#fecdd3")) + lg("h", (0, "#fb7185"), (1, "#be123c")),
               '<rect x="8" y="18" width="48" height="34" rx="5" fill="url(#e)"/>'
               '<path d="M8 22l24 17 24-17" stroke="#fda4af" stroke-width="2" fill="none"/>'
               '<path d="M32 42c-9-6-14-11-14-17 0-4 3-7 7-7 3 0 5 1.6 7 4 2-2.4 4-4 7-4 4 0 7 3 7 7 0 6-5 11-14 17z" fill="url(#h)"/>'
               '<path d="M24 23c1-2 3-3 5-2.6" stroke="#fff" stroke-width="2" stroke-linecap="round" opacity=".7"/>'
               '<path d="M46 8l-10 10M44 6l4 4-3 1z" stroke="#a16207" stroke-width="1.6" fill="#f6b40e"/>')


@gift("mimosa")
def _():
    dots = "".join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="url(#y)"/>' for x, y, r in
                   [(22, 14, 4), (30, 10, 4.4), (38, 14, 4), (18, 22, 3.6), (26, 20, 4.2), (34, 19, 4), (42, 22, 3.6), (22, 29, 3.4), (30, 27, 3.8), (38, 28, 3.4), (46, 16, 3)])
    return svg(rg("y", (0, "#fff7a8"), (1, "#eab308")) + lg("g", (0, "#4ade80"), (1, "#15803d")),
               '<path d="M30 30v26M30 40l-10 6M30 44l10 6" stroke="url(#g)" stroke-width="2.6" stroke-linecap="round"/>'
               '<path d="M18 46c-4-2-6-6-6-9 4 1 7 4 6 9zM42 50c4-2 6-6 6-9-4 1-7 4-6 9z" fill="url(#g)"/>' + dots)


@gift("cosmonaut")
def _():
    return svg(rg("h", (0, "#ffffff"), (1, "#cbd5e1")) + lg("v", (0, "#7dd3fc"), (1, "#1f3a66")),
               '<rect x="18" y="38" width="28" height="18" rx="7" fill="url(#h)"/><rect x="26" y="42" width="12" height="7" rx="2" fill="#1f6fb8"/>'
               '<circle cx="32" cy="24" r="17" fill="url(#h)"/><rect x="20" y="15" width="24" height="18" rx="9" fill="url(#v)"/>'
               '<path d="M25 19c3-2 7-2 9 0" stroke="#fff" stroke-width="2.4" fill="none" stroke-linecap="round" opacity=".7"/>'
               '<path d="M27 46h2M31 46h2" stroke="#fff" stroke-width="1.4"/><circle cx="35.5" cy="45.5" r="1.3" fill="#ef4444"/>'
               '<rect x="12" y="8" width="5" height="3" rx="1" fill="#ef4444"/>'
               + sparkle(54, 10, .9, "#fde047") + sparkle(8, 30, .6, "#bae6fd") + sparkle(56, 34, .5))


@gift("lilac")
def _():
    dots = "".join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{c}"/>' for x, y, r, c in
                   [(32, 8, 3.4, "#c4b5fd"), (27, 13, 3.6, "#a78bfa"), (37, 13, 3.6, "#c4b5fd"), (24, 19, 3.8, "#c4b5fd"), (32, 18, 4, "#a78bfa"),
                    (40, 19, 3.8, "#8b5cf6"), (26, 25, 3.8, "#8b5cf6"), (34, 25, 4, "#c4b5fd"), (42, 25, 3.2, "#a78bfa"), (29, 31, 3.6, "#a78bfa"), (37, 31, 3.4, "#8b5cf6"), (32, 36, 3, "#c4b5fd")])
    return svg(lg("g", (0, "#4ade80"), (1, "#15803d")),
               '<path d="M32 36v20" stroke="url(#g)" stroke-width="3" stroke-linecap="round"/>'
               '<path d="M32 46c-8 0-14-5-14-11 8 0 14 5 14 11zM32 50c7 0 12-5 13-10-7 0-12 4-13 10z" fill="url(#g)"/>' + dots
               + '<circle cx="26" cy="18" r="1" fill="#fff" opacity=".8"/><circle cx="33" cy="24" r="1" fill="#fff" opacity=".8"/>')


@gift("icecream")
def _():
    return svg(lg("w", (0, "#fcd9a0"), (1, "#c2853a")) + rg("p", (0, "#ffe4ef"), (1, "#f472b6")) + rg("m", (0, "#d9f99d"), (1, "#65a30d")),
               '<path d="M20 30h24L32 58z" fill="url(#w)"/><path d="M22 34l18 12M42 34L26 48M24 30l12 22M40 30l-10 22" stroke="#a16207" stroke-width="1" opacity=".5"/>'
               '<circle cx="25" cy="27" r="9" fill="url(#m)"/><circle cx="39" cy="27" r="9" fill="url(#p)"/><circle cx="32" cy="17" r="10" fill="#fff8ec"/>'
               '<path d="M27 13c2-2 5-3 7-2" stroke="#fff" stroke-width="2" stroke-linecap="round"/>'
               '<circle cx="32" cy="6" r="3.4" fill="#e11d48"/><path d="M32 3c1-3 4-3 5-2" stroke="#15803d" stroke-width="1.4" fill="none"/>'
               '<rect x="27" y="20" width="2" height="1" rx=".5" fill="#ef4444"/><rect x="35" y="16" width="2" height="1" rx=".5" fill="#3b82f6" transform="rotate(30 36 16)"/><rect x="33" y="22" width="2" height="1" rx=".5" fill="#facc15"/>')


@gift("watermelon")
def _():
    seeds = "".join(f'<ellipse cx="{x}" cy="{y}" rx="1.2" ry="2" fill="#1f2937" transform="rotate({a} {x} {y})"/>' for x, y, a in
                    [(22, 30, -30), (32, 34, 0), (42, 30, 30), (27, 40, -15), (37, 40, 15)])
    return svg(lg("r", (0, "#fda4af"), (1, "#e11d48")),
               '<path d="M6 22h52a26 26 0 0 1-52 0z" fill="#15803d"/><path d="M9 22h46a23 23 0 0 1-46 0z" fill="#bbf7d0"/>'
               '<path d="M12 22h40a20 20 0 0 1-40 0z" fill="url(#r)"/>' + seeds
               + '<path d="M16 24c2 6 6 10 12 12" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round" opacity=".5"/>')


@gift("shooting_star")
def _():
    return svg(lg("tail", (0, "#ffffff00"), (1, "#c4b5fd"), x2=1, y2=-1) + lg("s", (0, "#fff3a3"), (1, "#f59e0b")),
               '<rect x="4" y="6" width="56" height="48" rx="14" fill="#14213d"/>'
               '<path d="M8 48L36 22" stroke="url(#tail)" stroke-width="7" stroke-linecap="round"/>'
               '<path d="M42 10l3.4 7 7.6 1-5.6 5.3 1.4 7.6L42 27.2l-6.8 3.7 1.4-7.6-5.6-5.3 7.6-1z" fill="url(#s)"/>'
               + sparkle(14, 16, .6) + sparkle(52, 40, .5) + sparkle(24, 40, .4) + sparkle(54, 12, .35))


@gift("maple")
def _():
    return svg(lg("m", (0, "#fdba74"), (.5, "#ea580c"), (1, "#b91c1c")),
               '<path d="M32 4l4 10 6-3-1 9 9-4-3 9 7 2-11 7 2 5-9-2v12h-4V45l-9 2 2-5-11-7 7-2-3-9 9 4-1-9 6 3z" fill="url(#m)" stroke="#9a3412" stroke-width=".8" stroke-linejoin="round"/>'
               '<path d="M32 16v40M32 30l-9-6M32 30l9-6M32 38l-8 2M32 38l8 2" stroke="#9a3412" stroke-width="1.2" fill="none" opacity=".6"/>')


@gift("pumpkin")
def _():
    return svg(lg("p", (0, "#fdba74"), (1, "#c2410c")),
               '<path d="M32 14c2-5 6-7 9-6" stroke="#15803d" stroke-width="3.4" fill="none" stroke-linecap="round"/>'
               '<ellipse cx="20" cy="36" rx="12" ry="18" fill="url(#p)"/><ellipse cx="44" cy="36" rx="12" ry="18" fill="url(#p)"/><ellipse cx="32" cy="36" rx="12" ry="20" fill="url(#p)"/>'
               '<path d="M22 32l5-4 3 5zM34 33l3-5 5 4z" fill="#431407"/><path d="M22 42c3 4 6 5 10 5s7-1 10-5l-3 1-2-2-2 2-3-2-3 2-2-2-2 2z" fill="#431407"/>'
               '<path d="M16 26c-2 4-2 10 0 14" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round" opacity=".45"/>')


# ============================================================ от создателя
@gift("founder")
def _():
    return svg(lg("g", (0, "#fff4b0"), (.5, "#f6b40e"), (1, "#a8580a")) + lg("w", (0, "#7cc0f2"), (1, "#1f5d9c")) + rg("glow", (0, "#fff7d6"), (1, "#ffffff00"), cx=.5, cy=.5, r=.5),
               '<circle cx="32" cy="30" r="30" fill="url(#glow)"/>'
               '<path d="M22 44l-6 16 8-4 5 6 3-16zM42 44l6 16-8-4-5 6-3-16z" fill="#1f6fb8"/>'
               '<circle cx="32" cy="30" r="21" fill="url(#g)" stroke="#a8580a" stroke-width="1.2"/>'
               '<circle cx="32" cy="30" r="16" fill="#fff8e1" stroke="#d99a1c" stroke-width="1.2" stroke-dasharray="2 2"/>'
               '<path d="M19 32c0-5 5-8 11-8 5 0 9 2.5 10.5 5.5l2.5-2.5c1 2.8.5 5.4-1.8 6.8-.3 4-5 7-11 7-6.5 0-11-3.6-11-8.8z" fill="url(#w)"/>'
               '<path d="M20.5 35c2.5 3.4 6 4.6 10 4.6 4.4 0 8-1.8 10-4.8-4 1.8-16 1.8-20 .2z" fill="#f2ead9"/><circle cx="25" cy="31" r="1.1" fill="#0b2540"/>'
               '<path d="M24 12l4 3 4-6 4 6 4-3-1.6 6h-12.8z" fill="url(#g)" stroke="#a8580a" stroke-width=".8"/>'
               + sparkle(54, 10, 1, "#fde047") + sparkle(10, 12, .8, "#fde047") + sparkle(56, 40, .6, "#fde047"))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for code, fn in ART.items():
        with open(os.path.join(OUT, code + ".svg"), "w", encoding="utf-8") as f:
            f.write(fn())
    print(f"нарисовано подарков: {len(ART)}")
