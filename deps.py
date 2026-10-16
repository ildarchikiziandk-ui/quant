"""Общие зависимости для роутеров: шаблоны, рендер с базовым контекстом, хелперы ответа."""
from datetime import datetime

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from sqlalchemy.orm import Session

import auth
import config
import models
from services import chatstyle, extras, gamification, icons, legal, plus, prefs, social, streaks, text, timezones

templates = Jinja2Templates(directory="templates")
env = templates.env


@pass_context
def _local_time(ctx, dt, fmt="%d.%m.%Y %H:%M"):
    """{{ dt|lt("%H:%M") }} — время в часовом поясе текущего пользователя."""
    if not dt:
        return ""
    return timezones.to_local(dt, ctx.get("user")).strftime(fmt)


env.filters["lt"] = _local_time
env.filters["rich"] = text.richtext
env.filters["noemoji"] = text.strip_emoji
env.filters["ago"] = text.timeago
env.filters["compact"] = text.compact_number
env.filters["filesize"] = text.filesize
env.globals.update(
    brand=config.BRAND_NAME, brand_tagline=config.BRAND_TAGLINE, brand_plus=config.BRAND_PLUS,
    brand_email=config.BRAND_EMAIL, brand_color=config.BRAND_COLOR, site_url=config.SITE_URL,
    plural=text.plural, is_online=social.is_online, user_is_plus=social.is_plus, enumerate=enumerate,
    android_apk_url=config.ANDROID_APK_URL, pref=prefs.get, pref_classes=prefs.html_classes, tz_city=timezones.city, reading_minutes=extras.reading_minutes, moods=extras.MOODS, mood_by=extras.MOOD_BY, post_bgs=extras.BGS,
    post_expires=extras.EXPIRES, zodiac=extras.zodiac, frame_by=extras.FRAME_BY, status_active=extras.status_active, pref_client=prefs.client_values,
    yandex_enabled=bool(config.YANDEX_CLIENT_ID and config.YANDEX_CLIENT_SECRET),
    push_enabled=bool(config.VAPID_PUBLIC_KEY), static_v=config.INSTANCE_ID, app_version=config.APP_VERSION, utcnow=datetime.utcnow,
    min_age=config.MIN_AGE, secret_enabled=config.SECRET_CHATS_ENABLED, operator=legal.operator(), icon_svg=icons.icon, plus_bg=plus.bg, plus_palette=plus.PALETTE, plus_bgs=plus.BGS, plus_expires=plus.EXPIRES, plus_limit=plus.limit, plus_features=plus.FEATURES, plus_accents=plus.ACCENTS, gift_price=plus.gift_price, plus_exclusive=plus.EXCLUSIVE_GIFTS, icon=icons.icon, glyph=icons.glyph, reaction=icons.reaction, dname=chatstyle.name_of, custom_name=chatstyle.custom_name, wallpapers=chatstyle.WALLPAPERS, bubbles=chatstyle.BUBBLES, chat_fonts=chatstyle.FONTS, streak_level=streaks.level, emo=text.emoji_img,
)

REACTIONS = []  # эмодзи-реакции на посты убраны: остались лайк и кит
env.globals["reactions"] = REACTIONS


def current_user(request: Request, db: Session):
    return auth.get_current_user(request, db)


def unread_counts(user, db):
    if not user:
        return 0, 0
    notif = db.query(models.Notification.id).filter(models.Notification.user_id == user.id, models.Notification.is_read == False).count()
    msgs = db.query(models.Message.id).filter(models.Message.receiver_id == user.id, models.Message.is_read == False,
                                              models.Message.is_deleted == False, models.Message.scheduled_pending != True).count()
    return notif, msgs


def base_context(request: Request, db: Session, sidebar=True):
    user = current_user(request, db)
    chatstyle.load_names(db, user)
    if user:
        now = datetime.utcnow()
        if not user.last_seen or (now - user.last_seen).total_seconds() > 20 or (user.offline_at and user.offline_at >= user.last_seen):
            user.last_seen = now
            db.commit()
        gamification.update_streak(user, db)
    unread, unread_msg = unread_counts(user, db)
    ctx = {"request": request, "user": user, "unread": unread, "unread_msg": unread_msg,
           "is_plus": social.is_plus(user), "can_mod": social.can_mod(user), "now": datetime.utcnow(),
           "needs_email": social.needs_email(user),
           "announcement": db.query(models.Announcement).filter(models.Announcement.is_active == True)
                             .order_by(models.Announcement.created_at.desc()).first()}
    if user:
        from routers.more import deliver_reminders
        deliver_reminders(db, user)
    ctx["holiday"] = extras.holiday_today()
    if sidebar:
        ctx["daily_tasks"] = gamification.get_daily_tasks(user, db)
        if user:
            from datetime import date as _d, timedelta as _td
            ctx["can_spin"] = user.last_spin != _d.today().isoformat()
            fids = social.following_ids(db, user)
            ctx["online_friends"] = (db.query(models.User).filter(models.User.id.in_(fids or {-1}),
                                                                  models.User.last_seen > datetime.utcnow() - _td(seconds=social.ONLINE_SECONDS))
                                     .limit(8).all() if fids else [])
            ctx["online_friends"] = [u for u in ctx["online_friends"] if u.show_online is not False and social.is_online(u)]
        if user:
            excl = social.following_ids(db, user) | social.blocked_ids(db, user) | {user.id}
            known = [u for u, _ in extras.people_you_may_know(db, user, 4)]  # сначала друзья друзей и люди с общими интересами
            ctx["suggested_users"] = known + (db.query(models.User).filter(~models.User.id.in_(excl | {u.id for u in known}), models.User.is_blocked == False,
                                                                           prefs.sql_flag_off(models.User.prefs, "hide_from_search"))
                                              .order_by(models.User.total_points.desc()).limit(max(0, 4 - len(known))).all())
            today = datetime.utcnow().strftime("-%m-%d")
            ctx["birthdays"] = [u for u in db.query(models.User).filter(models.User.id.in_(social.following_ids(db, user) or {-1}),
                                                                         models.User.birthday.like(f"%{today}")).limit(5).all()
                               if not prefs.get(u, "hide_birthday")]
    return ctx


def render(request: Request, db: Session, template_name: str, sidebar=True, status_code=200, **extra):
    ctx = base_context(request, db, sidebar=sidebar)
    ctx.update(extra)
    return templates.TemplateResponse(request, template_name, ctx, status_code=status_code)


def redirect(url, status=303):
    return RedirectResponse(url, status_code=status)


def login_redirect(request: Request):
    from urllib.parse import quote
    nxt = request.url.path + ("?" + request.url.query if request.url.query else "")
    return redirect(f"/login?next={quote(nxt, safe='/')}")


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
