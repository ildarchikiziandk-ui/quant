"""Подарочные сертификаты на Nuvora+ (админ-панель → Nuvora+).

Сертификат — это промокод плюс красивая картинка 1600×1000: логотип, срок, код, QR на страницу активации
и подпись владельца. Подпись владелец загружает один раз (фото подписи на белой бумаге) — фон убирается сам,
файл лежит в uploads/cert/, в репозиторий не попадает.
"""
import io
import os
import secrets

import qrcode
from fastapi import Depends, Request
from fastapi.responses import Response
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps
from sqlalchemy.orm import Session

import config
import models
from database import get_db
from deps import current_user, log_mod, redirect, render

from .common import router, s

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "og_fonts")
CERT_DIR = os.path.join(config.UPLOAD_DIR, "cert")
SIGNATURE = os.path.join(CERT_DIR, "signature.png")
W, H = 1600, 1000
INK, WHALE, PAPER, MUTED = (23, 32, 44), (31, 111, 184), (246, 241, 232), (117, 107, 95)
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # без похожих 0/O и 1/I


def _owner(request, db):
    user = current_user(request, db)
    return user if user and user.is_owner else None


def _font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def _days_word(n):
    n = abs(n) % 100
    if 11 <= n <= 14:
        return "дней"
    return {1: "день", 2: "дня", 3: "дня", 4: "дня"}.get(n % 10, "дней")


def new_code():
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))


def clean_signature(raw):
    """Фото подписи → PNG с прозрачным фоном: тёмные штрихи остаются, бумага и тени исчезают."""
    im = ImageOps.exif_transpose(Image.open(raw)).convert("L")
    im.thumbnail((1200, 1200))
    bg = im.filter(ImageFilter.GaussianBlur(25))  # освещение бумаги
    ink = ImageChops.subtract(bg, im)  # насколько пиксель темнее фона
    alpha = ink.point(lambda v: 0 if v < 18 else min(255, (v - 18) * 6))
    box = alpha.point(lambda v: 255 if v > 60 else 0).getbbox()
    out = Image.new("RGBA", im.size, INK + (0,))
    out.putalpha(alpha)
    return out.crop(box) if box else out


def draw(code, days, recipient="", owner_name=""):
    """Картинка сертификата (PNG, байты)."""
    im = Image.new("RGB", (W, H), PAPER)
    # мягкие синие пятна на фоне
    glow = Image.new("RGB", (W, H), PAPER)
    g = ImageDraw.Draw(glow)
    g.ellipse((-260, -320, 700, 520), fill=(214, 229, 245))
    g.ellipse((1050, 560, 1900, 1300), fill=(220, 233, 247))
    im = Image.blend(im, glow.filter(ImageFilter.GaussianBlur(120)), 0.9)
    d = ImageDraw.Draw(im)
    # двойная рамка
    d.rounded_rectangle((36, 36, W - 36, H - 36), 44, outline=WHALE, width=6)
    d.rounded_rectangle((58, 58, W - 58, H - 58), 30, outline=(184, 207, 232), width=2)
    # логотип и марка
    logo = Image.open(os.path.join(ROOT, "static", "icon-512.png")).convert("RGBA").resize((112, 112))
    mask = Image.new("L", logo.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, 111, 111), 30, fill=255)
    im.paste(logo, (110, 104), mask)
    d.text((246, 118), "Nuvora", font=_font("unbounded-700.ttf", 44), fill=INK)
    d.text((248, 176), "nvra.ru", font=_font("onest-500.ttf", 28), fill=MUTED)
    # заголовок
    d.text((110, 280), "Сертификат", font=_font("unbounded-700.ttf", 92), fill=INK)
    d.text((114, 396), "на Nuvora+", font=_font("unbounded-700.ttf", 56), fill=WHALE)
    if recipient:
        d.text((114, 486), "для " + recipient[:40], font=_font("onest-800.ttf", 40), fill=INK)
    # срок крупно
    big = _font("unbounded-700.ttf", 150)
    d.text((110, 540 if recipient else 500), str(days), font=big, fill=WHALE)
    num_w = d.textlength(str(days), font=big)
    d.text((130 + num_w, (540 if recipient else 500) + 78), _days_word(days), font=_font("unbounded-700.ttf", 56), fill=INK)
    # промокод
    y = 760
    d.text((114, y - 46), "Промокод", font=_font("onest-500.ttf", 30), fill=MUTED)
    cf = _font("unbounded-700.ttf", 54)
    cw = d.textlength(code, font=cf)
    d.rounded_rectangle((104, y, 104 + cw + 64, y + 96), 24, fill=(255, 255, 255), outline=WHALE, width=3)
    d.text((136, y + 16), code, font=cf, fill=INK)
    d.text((114, y + 116), "Активируйте на nvra.ru/plus", font=_font("onest-800.ttf", 30), fill=INK)
    # QR на страницу активации с уже вписанным кодом
    qr = qrcode.QRCode(border=1, box_size=10)
    qr.add_data(f"{config.SITE_URL}/plus?code={code}")
    qr_img = qr.make_image(fill_color=INK, back_color="white").convert("RGB").resize((230, 230), Image.NEAREST)
    d.rounded_rectangle((W - 360, 110, W - 110, 360), 24, fill=(255, 255, 255))
    im.paste(qr_img, (W - 350, 120))
    d.text((W - 352, 372), "наведите камеру", font=_font("onest-500.ttf", 24), fill=MUTED)
    # подпись владельца
    line_y = H - 170
    d.line((W - 560, line_y, W - 120, line_y), fill=(184, 207, 232), width=3)
    d.text((W - 560, line_y + 14), "Владелец Nuvora" + (f" · {owner_name}" if owner_name else ""), font=_font("onest-500.ttf", 26), fill=MUTED)
    if os.path.exists(SIGNATURE):
        sig = Image.open(SIGNATURE).convert("RGBA")
        sig.thumbnail((360, 190))
        im.paste(sig, (W - 340 - sig.width // 2, line_y - sig.height + 26), sig)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


@router.get("/admin/certificates")
def cert_page(request: Request, db: Session = Depends(get_db), made: int = 0):
    me = _owner(request, db)
    if not me:
        return redirect("/")
    promo = db.get(models.Promocode, made) if made else None
    return render(request, db, "packs/v3/admin_certs.html", sidebar=False, promo=promo, has_signature=os.path.exists(SIGNATURE),
                  recent=db.query(models.Promocode).order_by(models.Promocode.created_at.desc()).limit(30).all())


@router.post("/admin/certificates/new")
async def cert_new(request: Request, db: Session = Depends(get_db)):
    me = _owner(request, db)
    if not me:
        return redirect("/")
    f = await request.form()
    try:
        days = max(1, min(3650, int(s(f.get("days")) or 30)))
    except ValueError:
        days = 30
    code = new_code()
    while db.query(models.Promocode).filter_by(code=code).first():
        code = new_code()
    p = models.Promocode(code=code, days=days, max_uses=1, note=s(f.get("recipient")).strip()[:40])
    db.add(p)
    log_mod(db, me, "promo", code, "сертификат")
    db.commit()
    return redirect(f"/admin/certificates?made={p.id}")


@router.get("/admin/certificates/{promo_id}.png")
def cert_png(promo_id: int, request: Request, db: Session = Depends(get_db), dl: int = 0):
    me = _owner(request, db)
    p = db.get(models.Promocode, promo_id)
    if not me or not p:
        return Response(status_code=404)
    headers = {"Cache-Control": "no-store"}
    if dl:
        headers["Content-Disposition"] = f'attachment; filename="nuvora-plus-{p.code}.png"'
    return Response(draw(p.code, p.days or 30, p.note or ""), media_type="image/png", headers=headers)


@router.post("/admin/certificates/signature")
async def cert_signature(request: Request, db: Session = Depends(get_db)):
    me = _owner(request, db)
    if not me:
        return redirect("/")
    f = await request.form()
    up = f.get("file")
    if up is not None and hasattr(up, "read"):
        data = await up.read()
        if 0 < len(data) <= 15 * 1024 * 1024:
            try:
                sig = clean_signature(io.BytesIO(data))
            except Exception:
                return redirect("/admin/certificates")
            os.makedirs(CERT_DIR, exist_ok=True)
            sig.save(SIGNATURE)
    elif f.get("remove") and os.path.exists(SIGNATURE):
        os.remove(SIGNATURE)
    return redirect("/admin/certificates")
