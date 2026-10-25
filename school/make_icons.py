"""Значок школы (синяя тетрадь-дневник с красной пятёркой) для сайта и Android-приложения.
Запуск: python3 -m school.make_icons"""
import os

from PIL import Image, ImageDraw, ImageFont

BASE = os.path.dirname(os.path.abspath(__file__))
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def draw(size, round_mask=False, pad=0.0):
    S = size * 4  # рисуем крупно и уменьшаем — края гладкие
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    bg = Image.new("RGBA", (S, S))
    g = ImageDraw.Draw(bg)
    for y in range(S):
        k = y / S
        g.line([(0, y), (S, y)], fill=(int(36 + 30 * k), int(122 - 30 * k), int(201 - 40 * k), 255))
    mask = Image.new("L", (S, S), 0)
    md = ImageDraw.Draw(mask)
    if round_mask:
        md.ellipse((0, 0, S - 1, S - 1), fill=255)
    else:
        md.rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * .22), fill=255)
    im.paste(bg, (0, 0), mask)
    p = S * pad
    # тетрадь
    x0, y0, x1, y1 = S * .25 + p, S * .19 + p, S * .77 - p, S * .81 - p
    d.rounded_rectangle((x0 + S * .025, y0 + S * .025, x1 + S * .025, y1 + S * .025), radius=int(S * .05), fill=(10, 40, 80, 70))
    d.rounded_rectangle((x0, y0, x1, y1), radius=int(S * .05), fill=(255, 255, 255, 255))
    d.rectangle((x0, y0, x0 + S * .07, y1), fill=(228, 236, 247, 255))
    for k in range(5):  # кольца переплёта
        cy = y0 + (y1 - y0) * (0.15 + k * 0.175)
        d.ellipse((x0 - S * .03, cy - S * .018, x0 + S * .03, cy + S * .018), fill=(31, 111, 184, 255))
    for k in range(4):  # линейки
        ly = y0 + (y1 - y0) * (0.62 + k * 0.09)
        d.line((x0 + S * .12, ly, x1 - S * .06, ly), fill=(200, 214, 232, 255), width=max(2, S // 90))
    f = ImageFont.truetype(FONT, int(S * .34))
    d.text(((x0 + x1) / 2 + S * .03, y0 + (y1 - y0) * .33), "5", font=f, fill=(224, 71, 90, 255), anchor="mm")
    return im.resize((size, size), Image.LANCZOS)


def main():
    st = os.path.join(BASE, "static")
    draw(192).save(os.path.join(st, "icon-192.png"))
    draw(512).save(os.path.join(st, "icon-512.png"))
    res = os.path.join(BASE, "android", "app", "src", "main", "res")
    for name, px in (("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192)):
        dd = os.path.join(res, f"mipmap-{name}")
        os.makedirs(dd, exist_ok=True)
        draw(px).save(os.path.join(dd, "ic_launcher.png"))
        draw(px, round_mask=True, pad=.02).save(os.path.join(dd, "ic_launcher_round.png"))


if __name__ == "__main__":
    main()
