"""Общие зависимости для роутеров: шаблоны, рендер с базовым контекстом, хелперы ответа."""
from datetime import datetime

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import auth
import config
import models
from services import gamification, social, text

templates = Jinja2Templates(directory="templates")
env = templates.env
env.filters["rich"] = text.richtext
env.filters["ago"] = text.timeago
env.filters["compact"] = text.compact_number
env.filters["filesize"] = text.filesize
env.globals.update(
    brand=config.BRAND_NAME, brand_tagline=config.BRAND_TAGLINE, brand_plus=config.BRAND_PLUS,
    brand_email=config.BRAND_EMAIL, brand_color=config.BRAND_COLOR, site_url=config.SITE_URL,
    plural=text.plural, is_online=social.is_online, user_is_plus=social.is_plus, enumerate=enumerate,
    android_apk_url=config.ANDROID_APK_URL,
    yandex_enabled=bool(config.YANDEX_CLIENT_ID and config.YANDEX_CLIENT_SECRET),
    push_enabled=bool(config.VAPID_PUBLIC_KEY), static_v=config.INSTANCE_ID, utcnow=datetime.utcnow,
)

REACTIONS = ["❤️", "😂", "😮", "😢", "🔥", "👏"]
env.globals["reactions"] = REACTIONS


def current_user(request: Request, db: Session):
    return auth.get_current_user(request, db)


def unread_counts(user, db):
    if not user:
        return 0, 0
    notif = db.query(models.Notification.id).filter(models.Notification.user_id == user.id, models.Notification.is_read == False).count()
    msgs = db.query(models.Message.id).filter(models.Message.receiver_id == user.id, models.Message.is_read == False,
                                              models.Message.is_deleted == False).count()
    return notif, msgs


def base_context(request: Request, db: Session, sidebar=True):
    user = current_user(request, db)
    if user:
        now = datetime.utcnow()
        if not user.last_seen or (now - user.last_seen).total_seconds() > 60:
            user.last_seen = now
            db.commit()
        gamification.update_streak(user, db)
    unread, unread_msg = unread_counts(user, db)
    ctx = {"request": request, "user": user, "unread": unread, "unread_msg": unread_msg,
           "is_plus": social.is_plus(user), "can_mod": social.can_mod(user), "now": datetime.utcnow(),
           "needs_email": social.needs_email(user),
           "announcement": db.query(models.Announcement).filter(models.Announcement.is_active == True)
                             .order_by(models.Announcement.created_at.desc()).first()}
    if sidebar:
        ctx["daily_tasks"] = gamification.get_daily_tasks(user, db)
        if user:
            excl = social.following_ids(db, user) | social.blocked_ids(db, user) | {user.id}
            ctx["suggested_users"] = (db.query(models.User).filter(~models.User.id.in_(excl), models.User.is_blocked == False)
                                      .order_by(models.User.total_points.desc()).limit(4).all())
            today = datetime.utcnow().strftime("-%m-%d")
            ctx["birthdays"] = [u for u in db.query(models.User).filter(models.User.id.in_(social.following_ids(db, user) or {-1}),
                                                                         models.User.birthday.like(f"%{today}")).limit(5).all()]
    return ctx


def render(request: Request, db: Session, template_name: str, sidebar=True, status_code=200, **extra):
    ctx = base_context(request, db, sidebar=sidebar)
    ctx.update(extra)
    return templates.TemplateResponse(request, template_name, ctx, status_code=status_code)


def redirect(url, status=303):
    return RedirectResponse(url, status_code=status)


def login_redirect(request: Request):
    nxt = request.url.path
    return redirect(f"/login?next={nxt}")


def json_error(msg, status=400):
    return JSONResponse({"ok": False, "error": msg}, status_code=status)


def blocked_page(request: Request, db: Session, user):
    return render(request, db, "blocked_account.html", sidebar=False, status_code=403, blocked_user=user)


def safe_next(url: str) -> str:
    if url and url.startswith("/") and not url.startswith("//"):
        return url
    return "/"


def log_mod(db, actor, action, target="", details=""):
    db.add(models.ModLog(actor_id=actor.id, action=action, target=str(target), details=details[:500]))
