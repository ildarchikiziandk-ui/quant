"""Привлечение людей (Nuvora 3.2).

1. Приглашения с наградой. Друг зарегистрировался по ссылке — пригласившему +20 Искр, новичку +25 в подарок.
   Когда друг начал пользоваться Nuvora (прошли сутки и есть пост, 2 комментария или 3 сообщения), пригласившему
   ещё +80 Искр, другу +25, а за каждых 5 засчитанных друзей — 7 дней Nuvora+. Так ботами не накрутить.
2. Публичные страницы: карта сайта для поисковиков (/sitemap.xml) и плашка «Присоединиться» для гостей.
3. Красивые превью ссылок для Telegram, ВК и WhatsApp: картинка 1200×630 с текстом поста или профилем.
"""
import hashlib
import os
import re
from datetime import datetime, timedelta
from xml.sax.saxutils import escape

from fastapi import Depends, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

import config
import models
from database import get_db
from services import gamification, handles, social

from . import models as m
from .common import router

INVITE_NOW, INVITE_LATER, FRIEND_GIFT = 20, 80, 25
PLUS_EVERY, PLUS_DAYS = 5, 7
FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "og_fonts")
OG_DIR = os.path.join(config.UPLOAD_DIR, "og")
OG_VERSION = "2:"  # меняется вместе с видом карточки — старые картинки перерисуются


# ---------------------------------------------------------------- приглашения
def on_register(db, new_user, inviter):
    """Сразу после регистрации по ссылке (вызывает routers.extras.reward_inviter)."""
    gamification.add_points(inviter, db, INVITE_NOW)
    gamification.add_points(new_user, db, FRIEND_GIFT)
    social.notify(db, inviter.id, "invite", new_user,
                  text=f"зарегистрировался(лась) по вашему приглашению · +{INVITE_NOW} Искр. Ещё +{INVITE_LATER}, когда друг освоится")
    db.add(models.Notification(user_id=new_user.id, type="system",
                               text=f"Вас пригласил(а) {inviter.name or inviter.username} — держите {FRIEND_GIFT} Искр в подарок!"))


def _active(db, u):
    since = u.created_at or datetime.utcnow()
    if datetime.utcnow() - since < timedelta(hours=24) or u.is_blocked:
        return False
    if db.query(models.Post.id).filter(models.Post.user_id == u.id, models.Post.is_draft == False).first():  # noqa: E712
        return True
    if db.query(func.count(models.Comment.id)).filter(models.Comment.user_id == u.id).scalar() >= 2:
        return True
    return db.query(func.count(models.Message.id)).filter(models.Message.sender_id == u.id).scalar() >= 3


def referral_job(db):
    """Раз в минуту: засчитать приглашения тех, кто начал пользоваться Nuvora."""
    rows = (db.query(models.User).filter(models.User.referred_by != None, models.User.referral_done != True,  # noqa: E711,E712
                                         models.User.created_at >= datetime.utcnow() - timedelta(days=60))
            .order_by(models.User.id).limit(50).all())
    for u in rows:
        if not _active(db, u):
            continue
        inviter = db.get(models.User, u.referred_by)
        u.referral_done = True
        if not inviter:
            continue
        gamification.add_points(inviter, db, INVITE_LATER)
        gamification.add_points(u, db, FRIEND_GIFT)
        done = db.query(func.count(models.User.id)).filter(models.User.referred_by == inviter.id, models.User.referral_done == True).scalar()  # noqa: E712
        text = f"освоился(лась) в Nuvora — приглашение засчитано · +{INVITE_LATER} Искр"
        if done and done % PLUS_EVERY == 0:
            gamification.grant_plus(inviter, PLUS_DAYS)
            text += f". И ещё {PLUS_DAYS} дней Nuvora+ за {done} друзей!"
        social.notify(db, inviter.id, "invite", u, text=text)
    db.commit()


def invite_stats(db, user):
    invited = db.query(models.User).filter_by(referred_by=user.id).order_by(models.User.created_at.desc()).all()
    done = sum(1 for u in invited if u.referral_done)
    return {"invited": invited, "done": done, "to_plus": PLUS_EVERY - done % PLUS_EVERY, "every": PLUS_EVERY, "days": PLUS_DAYS,
            "now": INVITE_NOW, "later": INVITE_LATER, "gift": FRIEND_GIFT}


# ---------------------------------------------------------------- карта сайта для поисковиков
@router.get("/sitemap.xml")
def sitemap(db: Session = Depends(get_db)):
    base = config.SITE_URL
    urls = [f"{base}/", f"{base}/c", f"{base}/about"]
    for (slug,) in db.query(m.Community.slug).limit(2000):
        urls.append(f"{base}/c/{slug}")
    public = (db.query(models.User.username).filter(models.User.is_private != True, models.User.is_blocked != True)  # noqa: E712
              .filter(~models.User.prefs.like('%"guests_hidden": true%')).order_by(models.User.total_points.desc()).limit(5000))
    names = [u for (u,) in public]
    urls += [f"{base}/profile/{u}" for u in names]
    posts = (social.visible_posts(db, None).filter(models.Post.is_repost != True)  # noqa: E712
             .order_by(models.Post.created_at.desc()).with_entities(models.Post.id, models.Post.created_at).limit(10000))
    items = [f"<url><loc>{escape(u)}</loc></url>" for u in urls]
    items += [f"<url><loc>{base}/post/{pid}</loc><lastmod>{(dt or datetime.utcnow()).strftime('%Y-%m-%d')}</lastmod></url>" for pid, dt in posts]
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(items) + "</urlset>"
    return Response(xml, media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})


# ---------------------------------------------------------------- картинки-превью для соцсетей
def _font(name, size):
    from PIL import ImageFont
    return ImageFont.truetype(os.path.join(FONTS, name), size)


_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D\u2B00-\u2BFF]+")


def _clean(text):
    """Для картинки: без эмодзи (в шрифте их нет — были бы квадратики) и без пустых строк."""
    text = _EMOJI.sub("", text or "")
    lines = [" ".join(x.split()) for x in text.split("\n")]
    return "\n".join(x for x in lines if x)


def _wrap(draw, text, font, width, lines):
    out, words_left = [], False
    paras = _clean(text).split("\n")
    for pi, para in enumerate(paras):
        cur = ""
        words = para.split(" ")
        for wi, w in enumerate(words):
            t = (cur + " " + w).strip()
            if draw.textlength(t, font=font) <= width:
                cur = t
                continue
            out.append(cur)
            cur = w
            if len(out) >= lines:
                words_left = True
                break
        if len(out) >= lines:
            words_left = words_left or pi < len(paras) - 1
            break
        out.append(cur)
        if len(out) >= lines:
            words_left = pi < len(paras) - 1
            break
    out = out[:lines]
    if words_left and out:
        out[-1] = out[-1].rstrip(" .,:;—") + "…"
    return out


def _card(path, title, subtitle, body, badge="Nuvora"):
    """Карточка 1200×630: синий фон бренда, крупный текст, логотип."""
    from PIL import Image, ImageDraw
    W, H = 1200, 630
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    for y in range(H):  # мягкий градиент синего кита
        k = y / H
        d.line([(0, y), (W, y)], fill=(int(24 + 10 * k), int(104 - 40 * k), int(176 - 60 * k)))
    d.rounded_rectangle((48, 48, W - 48, H - 48), radius=40, fill=(255, 253, 249))
    try:
        logo = Image.open(os.path.join(config.BASE_DIR, "static", "brand", "logo-180.png")).convert("RGBA").resize((88, 88))
        im.paste(logo, (W - 48 - 40 - 88, H - 48 - 40 - 88), logo)
    except OSError:
        pass
    d.text((96, 92), _clean(title)[:40], font=_font("unbounded-700.ttf", 46), fill=(23, 32, 44))
    if subtitle:
        d.text((96, 158), subtitle[:60], font=_font("onest-500.ttf", 30), fill=(31, 111, 184))
    # текст не должен наезжать на подпись nvra.ru внизу (она на y≈498)
    y = 226 if subtitle else 176
    f = _font("onest-500.ttf", 38)
    for line in _wrap(d, body, f, W - 96 * 2 - 140, 5 if subtitle else 6):
        d.text((96, y), line, font=f, fill=(40, 46, 56))
        y += 52
    d.text((96, H - 48 - 40 - 44), "nvra.ru", font=_font("onest-800.ttf", 34), fill=(31, 111, 184))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp.png"
    im.save(tmp, "PNG", optimize=True)
    os.replace(tmp, path)


def _cached(key, render):
    os.makedirs(OG_DIR, exist_ok=True)
    path = os.path.join(OG_DIR, hashlib.sha1((OG_VERSION + key).encode()).hexdigest()[:20] + ".png")
    if not os.path.isfile(path):
        render(path)
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/og/post/{pid}.png")
def og_post(pid: int, db: Session = Depends(get_db)):
    p = db.get(models.Post, pid)
    if not p or not social.can_view_post(db, None, p):
        return Response(status_code=404)
    a = p.author
    from .communities import info
    c = info(p.community_id) if p.community_id else None
    title = c["name"] if c and c["kind"] == "channel" else (a.name or a.username if a else "Nuvora")
    sub = f"@{a.username}" if a and not (c and c["kind"] == "channel") else ("канал в Nuvora" if c else "")
    body = (p.content or "").replace("**", "").replace("__", "").strip() or "Фото и видео — смотрите в Nuvora"
    key = f"post:{p.id}:{p.edited_at or p.created_at}:{title}"
    return _cached(key, lambda path: _card(path, title, sub, body))


@router.get("/og/profile/{username}.png")
def og_profile(username: str, db: Session = Depends(get_db)):
    u = handles.owner_of(db, username)
    if not u:
        return Response(status_code=404)
    followers = db.query(func.count(models.Follow.id)).filter(models.Follow.following_id == u.id).scalar() or 0
    body = (u.bio or "").strip() or f"Подписывайтесь на {u.name or u.username} в Nuvora"
    body += f"\n\n{followers} подписчиков"
    key = f"profile:{u.id}:{u.name}:{u.bio}:{followers // 10}"
    return _cached(key, lambda path: _card(path, u.name or u.username, f"@{u.username}", body))


@router.get("/og/c/{slug}.png")
def og_community(slug: str, db: Session = Depends(get_db)):
    c = db.query(m.Community).filter_by(slug=slug).first()
    if not c:
        return Response(status_code=404)
    n = db.query(func.count(m.CommunityMember.id)).filter_by(community_id=c.id).scalar() or 0
    body = (c.description or "").strip() or "Присоединяйтесь в Nuvora"
    key = f"c:{c.id}:{c.name}:{c.description}:{n // 10}"
    return _cached(key, lambda path: _card(path, c.name, ("Канал" if c.kind == "channel" else "Сообщество") + f" · {n} подписчиков", body))
