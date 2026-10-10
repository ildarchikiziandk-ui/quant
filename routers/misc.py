from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

import config
import models
from database import get_db
from deps import current_user, login_redirect, redirect, render, templates
from services import mailer, ratelimit, social

router = APIRouter()

SPECIAL_TYPES = {"verify": "Галочка верификации", "star": "Звезда автора", "unblock": "Разблокировка аккаунта", "other": "Другое"}


@router.get("/support")
def support_page(request: Request, db: Session = Depends(get_db)):
    return render(request, db, "support.html")


@router.post("/support")
async def support_submit(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    form = await request.form()
    subject = (form.get("subject") or "").strip()[:120]
    message = (form.get("message") or "").strip()[:3000]
    email = user.email if user else (form.get("email") or "").strip()[:120]
    if not subject or not message:
        return render(request, db, "support.html", error="Заполните тему и сообщение")
    if not email:
        return render(request, db, "support.html", error="Укажите email для ответа")
    ip = request.client.host if request.client else "?"
    if not ratelimit.hit(f"support:{user.id if user else ip}", 5, 3600):
        return render(request, db, "support.html", error="Слишком много обращений, попробуйте позже")
    text = f"📧 {user.username if user else email}\n📌 {subject}\n💬 {message}"
    owners = db.query(models.User).filter((models.User.is_owner == True) | (models.User.is_moderator == True)).all()
    for o in owners:
        db.add(models.Notification(user_id=o.id, from_user_id=user.id if user else None, type="support", text=text,
                                   reply_email="" if user else email))
    db.commit()
    mailer.send_support_confirmation(email, subject)
    return render(request, db, "support.html", success=True)


@router.post("/support/reply/{notif_id}")
async def support_reply(notif_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not social.can_mod(user):
        return redirect("/")
    form = await request.form()
    reply = (form.get("reply") or "").strip()[:3000]
    n = db.get(models.Notification, notif_id)
    if n and reply:
        if n.from_user_id:
            db.add(models.Notification(user_id=n.from_user_id, from_user_id=user.id, type="support_reply", text=reply))
        elif n.reply_email:
            mailer.send_support_reply(n.reply_email, reply)
        n.is_read = True
        db.commit()
    return redirect(request.headers.get("referer") or "/notifications")


@router.get("/terms")
def terms_page(request: Request, db: Session = Depends(get_db)):
    return render(request, db, "terms.html")


@router.get("/about")
def about_page(request: Request, db: Session = Depends(get_db)):
    stats = {"users": db.query(models.User).count(), "posts": db.query(models.Post).count()}
    return render(request, db, "about.html", stats=stats)


@router.get("/plus")
def plus_page(request: Request, db: Session = Depends(get_db)):
    return render(request, db, "plus.html")


@router.get("/special_request")
@router.get("/special-request")
def special_request_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    mine = db.query(models.SpecialRequest).filter_by(user_id=user.id).order_by(models.SpecialRequest.created_at.desc()).all()
    return render(request, db, "special_request.html", types=SPECIAL_TYPES, mine=mine)


@router.post("/special_request")
@router.post("/special-request")
async def special_request_submit(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    form = await request.form()
    rtype = form.get("type") if form.get("type") in SPECIAL_TYPES else "other"
    mine = db.query(models.SpecialRequest).filter_by(user_id=user.id).order_by(models.SpecialRequest.created_at.desc()).all()
    if any(r.status == "new" and r.type == rtype for r in mine):
        return render(request, db, "special_request.html", types=SPECIAL_TYPES, mine=mine, error="Такая заявка уже на рассмотрении")
    db.add(models.SpecialRequest(user_id=user.id, type=rtype, reason=(form.get("reason") or "").strip()[:2000],
                                 links=(form.get("links") or "").strip()[:500]))
    db.commit()
    mine = db.query(models.SpecialRequest).filter_by(user_id=user.id).order_by(models.SpecialRequest.created_at.desc()).all()
    return render(request, db, "special_request.html", types=SPECIAL_TYPES, mine=mine, success=True)


@router.get("/offline")
def offline_page(request: Request):
    return templates.TemplateResponse(request, "offline.html", {})


@router.get("/manifest.webmanifest")
def manifest():
    return JSONResponse({
        "name": config.BRAND_NAME, "short_name": config.BRAND_NAME, "description": config.BRAND_TAGLINE,
        "start_url": "/", "display": "standalone", "background_color": "#09090b", "theme_color": "#18181b",
        "orientation": "portrait", "lang": "ru", "categories": ["social"],
        "icons": [{"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
                  {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}],
        "shortcuts": [{"name": "Сообщения", "url": "/messages"}, {"name": "Уведомления", "url": "/notifications"}],
    }, media_type="application/manifest+json")


@router.get("/sw.js")
def service_worker():
    with open("static/sw.js", encoding="utf-8") as f:
        body = f.read().replace("__BRAND__", config.BRAND_NAME).replace("__VERSION__", config.INSTANCE_ID)
    return PlainTextResponse(body, media_type="application/javascript", headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})


@router.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    return "User-agent: *\nDisallow: /settings\nDisallow: /messages\nDisallow: /admin\nDisallow: /api/\n"
