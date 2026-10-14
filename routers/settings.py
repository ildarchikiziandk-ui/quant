import io
import json
import re
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import auth
import config
import models
from database import get_db
from deps import current_user, json_error, login_redirect, redirect, render
from routers.auth_routes import validate_password, validate_username
from routers.posts import purge_post, read_payload, wants_json
from services import extras, gamification, prefs, recommend, social, timezones
from services.uploads import delete_file, save_file

router = APIRouter()

SECTIONS = ("profile", "account", "feed", "privacy", "notifications", "messages", "appearance", "accessibility", "security", "plus", "data")
THEMES = ("light", "dark", "auto")
ACCENTS = ["#2563eb", "#0d9488", "#16a34a", "#ca8a04", "#dc2626", "#9333ea", "#475569"]


def _settings(request, db, user, section="profile", **extra):
    sessions = (db.query(models.UserSession).filter_by(user_id=user.id, is_active=True)
                .order_by(models.UserSession.last_active.desc()).all())
    blocked = [b.blocked for b in db.query(models.UserBlock).filter_by(blocker_id=user.id).all() if b.blocked]
    muted = [m.muted for m in db.query(models.UserMute).filter_by(user_id=user.id).all() if m.muted]
    ctx = dict(section=section if section in SECTIONS else "profile", sessions=sessions, blocked_users=blocked, muted_users=muted,
               current_session_id=getattr(request.state, "session_id", None), accents=ACCENTS,
               pending_requests=db.query(models.FollowRequest).filter_by(target_id=user.id).count(),
               pref_groups=prefs.section_prefs(section), pref_values=prefs.values(user), tz_map=timezones.iana_map(),
               profile_links=extras.parse_links(user.links))
    ctx.update(extra)
    return render(request, db, "settings.html", **ctx)


@router.get("/settings")
def settings_page(request: Request, section: str = "profile", saved: int = 0, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    extra = {"success": "Настройки сохранены ✓"} if saved else {}
    if section == "security" and not user.two_factor_enabled:
        secret = request.cookies.get("totp_setup") or auth.totp_new_secret()
        extra = {"totp_secret": secret, "totp_uri": auth.totp_uri(secret, user.username)}
        resp = _settings(request, db, user, section, **extra)
        resp.set_cookie("totp_setup", secret, max_age=900, httponly=True, samesite="lax", secure=config.COOKIE_SECURE)
        return resp
    return _settings(request, db, user, section, **extra)


@router.post("/settings/prefs/{section}")
async def save_prefs(section: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    if section not in prefs.SECTIONS:
        return redirect("/settings")
    prefs.update(user, section, await request.form())
    db.commit()
    recommend.invalidate(user.id)
    return redirect(f"/settings?section={section}&saved=1")


@router.get("/settings/{section}")
def settings_section(section: str, request: Request, db: Session = Depends(get_db)):
    if section not in SECTIONS:
        return redirect("/settings")
    return redirect(f"/settings?section={section}")


def _clean(form, key, n):
    return (form.get(key) or "").strip()[:n]


def _clean_url(value):
    if value and not re.match(r"^https?://", value):
        value = "https://" + value
    return value


@router.post("/settings/profile")
async def settings_profile(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    form = await request.form()
    user.name = _clean(form, "name", 60) or user.username
    user.bio = _clean(form, "bio", 300)
    user.website = _clean_url(_clean(form, "website", 100))
    user.city = _clean(form, "city", 60)
    bday = _clean(form, "birthday", 10)
    user.birthday = bday if re.match(r"^\d{4}-\d{2}-\d{2}$", bday) else ""
    user.emoji_status = _clean(form, "emoji_status", 8)
    user.telegram_link = _clean(form, "telegram_link", 100)
    user.youtube_link = _clean(form, "youtube_link", 100)
    user.tiktok_link = _clean(form, "tiktok_link", 100)
    user.interests = ", ".join(extras.parse_interests(form.get("interests") or ""))
    db.commit()
    recommend.invalidate(user.id)
    return _settings(request, db, user, "profile", success="Профиль сохранён")


@router.post("/settings/username")
async def settings_username(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    form = await request.form()
    new = _clean(form, "username", 30).lstrip("@")
    err = validate_username(new)
    if not err and new.lower() != user.username.lower() and db.query(models.User).filter(func.lower(models.User.username) == new.lower()).first():
        err = "Этот логин уже занят"
    if not err and not auth.verify_password(form.get("password") or "", user.password):
        err = "Неверный пароль"
    if err:
        return _settings(request, db, user, "account", error=err)
    user.username = new
    db.commit()
    return _settings(request, db, user, "account", success=f"Логин изменён на @{new}")


@router.post("/settings/email")
async def settings_email(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    form = await request.form()
    email = _clean(form, "email", 120).lower()
    from routers.auth_routes import _send_code, validate_email
    if not validate_email(email):
        return _settings(request, db, user, "account", error="Некорректный email")
    if not auth.verify_password(form.get("password") or "", user.password):
        return _settings(request, db, user, "account", error="Неверный пароль")
    if db.query(models.User).filter(func.lower(models.User.email) == email, models.User.id != user.id).first():
        return _settings(request, db, user, "account", error="Email уже используется")
    user.email = email
    user.email_verified = not config.EMAIL_ENABLED
    db.commit()
    if config.EMAIL_ENABLED:
        _send_code(db, email, "register")
        return redirect("/verify")
    return _settings(request, db, user, "account", success="Email изменён")


@router.post("/settings/avatar")
async def settings_avatar(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    form = await request.form()
    url, err = save_file(form.get("avatar"), allowed=("image",))
    if not url:
        return _settings(request, db, user, "profile", error=err)
    delete_file(user.avatar)
    user.avatar = url
    db.commit()
    return redirect(f"/profile/{user.username}")


@router.post("/settings/cover")
async def settings_cover(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    form = await request.form()
    url, err = save_file(form.get("cover"), allowed=("image",))
    if not url:
        return _settings(request, db, user, "profile", error=err)
    delete_file(user.cover)
    user.cover = url
    db.commit()
    return redirect(f"/profile/{user.username}")


@router.post("/settings/remove-media/{kind}")
def remove_media(kind: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user or kind not in ("avatar", "cover"):
        return redirect("/settings")
    delete_file(getattr(user, kind))
    setattr(user, kind, "")
    db.commit()
    return redirect("/settings?section=profile")


@router.post("/settings/password")
async def settings_password(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    form = await request.form()
    old, new, confirm = form.get("old_password", ""), form.get("new_password", ""), form.get("confirm_password", "")
    if not auth.verify_password(old, user.password):
        return _settings(request, db, user, "account", error="Текущий пароль неверный")
    err = validate_password(new) or (None if new == confirm else "Пароли не совпадают")
    if err:
        return _settings(request, db, user, "account", error=err)
    user.password = auth.hash_password(new)
    current = getattr(request.state, "session_id", None)
    db.query(models.UserSession).filter(models.UserSession.user_id == user.id, models.UserSession.id != (current or -1)).update(
        {"is_active": False}, synchronize_session=False)
    db.commit()
    return _settings(request, db, user, "account", success="Пароль изменён, другие сеансы завершены")


@router.post("/settings/privacy")
async def settings_privacy(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    form = await request.form()
    user.who_can_message = form.get("who_can_message") if form.get("who_can_message") in ("all", "followers", "nobody") else "all"
    user.who_can_see_stories = form.get("who_can_see_stories") if form.get("who_can_see_stories") in ("all", "followers", "close") else "all"
    was_private = user.is_private
    user.is_private = "is_private" in form
    user.hide_likes = "hide_likes" in form
    user.show_online = "show_online" in form
    if was_private and not user.is_private:
        from routers.profile import _accept_follow
        for req in db.query(models.FollowRequest).filter_by(target_id=user.id).all():
            if req.requester:
                _accept_follow(db, req.requester, user)
            db.delete(req)
    db.commit()
    return _settings(request, db, user, "privacy", success="Настройки приватности сохранены")


@router.post("/settings/notifications")
async def settings_notifications(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    form = await request.form()
    for key in ("notify_likes", "notify_comments", "notify_follows", "notify_mentions", "notify_messages"):
        setattr(user, key, key in form)
    db.commit()
    return _settings(request, db, user, "notifications", success="Сохранено")


@router.post("/settings/appearance")
async def settings_appearance(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    form = await request.form()
    if form.get("theme") in THEMES:
        user.theme = form.get("theme")
    if form.get("font_size") in ("small", "medium", "large"):
        user.font_size = form.get("font_size")
    accent = form.get("accent_color") or ""
    user.accent_color = accent if re.match(r"^#[0-9a-fA-F]{6}$", accent) else ""
    db.commit()
    return _settings(request, db, user, "appearance", success="Оформление сохранено")


@router.post("/settings/theme")
@router.post("/api/settings/theme")
async def settings_theme(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return JSONResponse({"ok": False})
    data = await read_payload(request)
    if data.get("theme") in THEMES:
        user.theme = data.get("theme")
        db.commit()
    return JSONResponse({"ok": True})


@router.post("/settings/plus-color")
async def plus_color(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user or not social.is_plus(user):
        return redirect("/settings?section=plus")
    form = await request.form()
    color = form.get("color") or ""
    if re.match(r"^#[0-9a-fA-F]{6}$", color):
        user.plus_color = color
        db.commit()
    return redirect("/settings?section=plus")


@router.post("/settings/promocode")
@router.post("/activate_plus")
async def activate_promo(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    form = await request.form()
    code = (form.get("code") or form.get("promocode") or "").upper().strip()
    promo = db.query(models.Promocode).filter_by(code=code, is_active=True).first()
    if not promo or (promo.uses or 0) >= (promo.max_uses or 1):
        return _settings(request, db, user, "plus", error="Промокод не найден или исчерпан")
    used_key = f"promo:{promo.id}"
    if db.query(models.Notification).filter_by(user_id=user.id, type="promo", text=used_key).first():
        return _settings(request, db, user, "plus", error="Вы уже активировали этот промокод")
    promo.uses = (promo.uses or 0) + 1
    if promo.uses >= promo.max_uses:
        promo.is_active = False
    gamification.grant_plus(user, promo.days or 30)
    db.add(models.Notification(user_id=user.id, type="promo", text=used_key, is_read=True))
    db.commit()
    return _settings(request, db, user, "plus", success=f"{config.BRAND_PLUS} активирован на {promo.days} дней!")


@router.post("/settings/sessions/{session_id}/revoke")
def revoke_session(session_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    s = db.query(models.UserSession).filter_by(id=session_id, user_id=user.id).first()
    if s:
        s.is_active = False
        db.commit()
    return redirect("/settings?section=security")


@router.post("/settings/sessions/revoke-others")
def revoke_others(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    current = getattr(request.state, "session_id", None)
    db.query(models.UserSession).filter(models.UserSession.user_id == user.id, models.UserSession.id != (current or -1)).update(
        {"is_active": False}, synchronize_session=False)
    db.commit()
    return redirect("/settings?section=security")


@router.get("/settings/2fa/qr.svg")
def totp_qr(request: Request, db: Session = Depends(get_db)):
    """QR-код для приложения-аутентификатора генерируется локально — секрет не уходит третьим лицам."""
    import qrcode
    import qrcode.image.svg
    from fastapi.responses import Response
    user = current_user(request, db)
    secret = request.cookies.get("totp_setup", "")
    if not user or not secret:
        return Response(status_code=404)
    img = qrcode.make(auth.totp_uri(secret, user.username), image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=1)
    buf = io.BytesIO()
    img.save(buf)
    return Response(buf.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@router.post("/settings/2fa/enable")
async def enable_2fa(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    form = await request.form()
    secret = request.cookies.get("totp_setup", "")
    if not secret or not auth.totp_verify(secret, form.get("code") or ""):
        return _settings(request, db, user, "security", error="Неверный код — проверьте время на телефоне и попробуйте ещё раз",
                         totp_secret=secret, totp_uri=auth.totp_uri(secret, user.username) if secret else "")
    user.two_factor_secret = secret
    user.two_factor_enabled = True
    gamification.check_achievement(user, db, "secure")
    db.commit()
    resp = _settings(request, db, user, "security", success="Двухфакторная защита включена 🔐")
    resp.delete_cookie("totp_setup")
    return resp


@router.post("/settings/2fa/disable")
async def disable_2fa(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    form = await request.form()
    if not auth.verify_password(form.get("password") or "", user.password):
        return _settings(request, db, user, "security", error="Неверный пароль")
    user.two_factor_enabled = False
    user.two_factor_secret = ""
    db.commit()
    return redirect("/settings?section=security")


@router.get("/export-data")
def export_data(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)

    def dt(v):
        return v.isoformat() if v else None

    posts = db.query(models.Post).filter_by(user_id=user.id).all()
    data = {
        "exported_at": dt(datetime.utcnow()), "service": config.BRAND_NAME,
        "profile": {k: getattr(user, k) for k in ("username", "name", "email", "bio", "website", "city", "birthday",
                                                   "telegram_link", "youtube_link", "tiktok_link", "total_points", "level", "streak_days")},
        "created_at": dt(user.created_at),
        "posts": [{"id": p.id, "content": p.content, "media": p.image, "created_at": dt(p.created_at), "views": p.views,
                   "likes": len(p.likes), "comments": len(p.comments)} for p in posts],
        "comments": [{"post_id": c.post_id, "content": c.content, "created_at": dt(c.created_at)}
                     for c in db.query(models.Comment).filter_by(user_id=user.id)],
        "following": [f.following.username for f in db.query(models.Follow).filter_by(follower_id=user.id) if f.following],
        "followers": [f.follower.username for f in db.query(models.Follow).filter_by(following_id=user.id) if f.follower],
        "bookmarks": [b.post_id for b in db.query(models.Bookmark).filter_by(user_id=user.id)],
        "messages_sent": [{"to": m.receiver.username if m.receiver else None, "content": m.content, "created_at": dt(m.created_at)}
                          for m in db.query(models.Message).filter_by(sender_id=user.id, is_deleted=False)],
        "achievements": [ua.achievement.name for ua in db.query(models.UserAchievement).filter_by(user_id=user.id) if ua.achievement],
    }
    content = json.dumps(data, ensure_ascii=False, indent=2)
    fname = f"{config.BRAND_NAME.lower()}_{user.username}.json"
    return StreamingResponse(io.BytesIO(content.encode()), media_type="application/json",
                             headers={"Content-Disposition": f"attachment; filename={fname}"})


def purge_user(db, user):
    """Полное удаление пользователя и всех связанных данных."""
    uid = user.id
    for p in db.query(models.Post).filter_by(user_id=uid).all():
        purge_post(db, p)
    db.flush()
    my_comments = [c.id for c in db.query(models.Comment.id).filter_by(user_id=uid)]
    if my_comments:
        db.query(models.CommentLike).filter(models.CommentLike.comment_id.in_(my_comments)).delete(synchronize_session=False)
        db.query(models.Comment).filter(models.Comment.parent_id.in_(my_comments)).update({"parent_id": None}, synchronize_session=False)
        db.query(models.Comment).filter(models.Comment.id.in_(my_comments)).delete(synchronize_session=False)
    for s in db.query(models.Story).filter_by(user_id=uid).all():
        delete_file(s.media_url)
        db.query(models.StoryView).filter_by(story_id=s.id).delete()
        db.query(models.StoryReaction).filter_by(story_id=s.id).delete()
        db.query(models.StoryHighlightItem).filter_by(story_id=s.id).delete()
        db.delete(s)
    for h in db.query(models.StoryHighlight).filter_by(user_id=uid).all():
        db.query(models.StoryHighlightItem).filter_by(highlight_id=h.id).delete()
        db.delete(h)
    for r in db.query(models.Reel).filter_by(user_id=uid).all():
        delete_file(r.video_url)
        db.query(models.ReelLike).filter_by(reel_id=r.id).delete()
        db.query(models.ReelComment).filter_by(reel_id=r.id).delete()
        db.delete(r)
    msg_ids = [m.id for m in db.query(models.Message.id).filter(or_(models.Message.sender_id == uid, models.Message.receiver_id == uid))]
    if msg_ids:
        db.query(models.MessageReaction).filter(models.MessageReaction.message_id.in_(msg_ids)).delete(synchronize_session=False)
        db.query(models.Message).filter(models.Message.reply_to_id.in_(msg_ids)).update({"reply_to_id": None}, synchronize_session=False)
        db.query(models.Message).filter(models.Message.id.in_(msg_ids)).delete(synchronize_session=False)
    db.query(models.Message).filter(models.Message.forwarded_from_id == uid).update({"forwarded_from_id": None}, synchronize_session=False)
    gm_ids = [m.id for m in db.query(models.GroupMessage.id).filter_by(sender_id=uid)]
    if gm_ids:
        db.query(models.GroupMessage).filter(models.GroupMessage.reply_to_id.in_(gm_ids)).update({"reply_to_id": None}, synchronize_session=False)
        db.query(models.GroupMessage).filter(models.GroupMessage.id.in_(gm_ids)).delete(synchronize_session=False)
    for g in db.query(models.GroupChat).filter_by(owner_id=uid).all():
        other = db.query(models.GroupMember).filter(models.GroupMember.group_id == g.id, models.GroupMember.user_id != uid).first()
        if other:
            g.owner_id = other.user_id
            other.is_admin = True
        else:
            db.query(models.GroupMessage).filter_by(group_id=g.id).delete()
            db.query(models.GroupMember).filter_by(group_id=g.id).delete()
            db.query(models.PinnedChat).filter_by(pinned_group_id=g.id).delete()
            db.query(models.MutedChat).filter_by(muted_group_id=g.id).delete()
            db.query(models.TypingStatus).filter_by(group_id=g.id).delete()
            db.delete(g)
    simple = [
        (models.Like, "user_id"), (models.Whale, "user_id"), (models.Reaction, "user_id"), (models.Bookmark, "user_id"),
        (models.CommentLike, "user_id"), (models.ReelLike, "user_id"), (models.ReelComment, "user_id"), (models.StoryView, "user_id"),
        (models.StoryReaction, "user_id"), (models.PollVote, "user_id"), (models.GroupMember, "user_id"), (models.UserSession, "user_id"),
        (models.PushSubscription, "user_id"), (models.UserAchievement, "user_id"), (models.UserDailyTask, "user_id"),
        (models.UserWeeklyChallenge, "user_id"), (models.RaffleEntry, "user_id"), (models.UserSticker, "user_id"), (models.Draft, "user_id"),
        (models.PinnedChat, "user_id"), (models.PinnedChat, "pinned_user_id"), (models.MutedChat, "user_id"), (models.MutedChat, "muted_user_id"),
        (models.TypingStatus, "user_id"), (models.TypingStatus, "target_id"), (models.Follow, "follower_id"), (models.Follow, "following_id"),
        (models.FollowRequest, "requester_id"), (models.FollowRequest, "target_id"), (models.UserBlock, "blocker_id"), (models.UserBlock, "blocked_id"),
        (models.UserMute, "user_id"), (models.UserMute, "muted_id"), (models.CloseFriend, "user_id"), (models.CloseFriend, "friend_id"),
        (models.Notification, "user_id"), (models.Report, "reporter_id"), (models.Report, "target_id"), (models.PostReport, "reporter_id"),
        (models.SpecialRequest, "user_id"), (models.CallLog, "caller_id"), (models.CallLog, "receiver_id"),
    ]
    for model, col in simple:
        db.query(model).filter(getattr(model, col) == uid).delete(synchronize_session=False)
    db.query(models.Notification).filter(models.Notification.from_user_id == uid).update({"from_user_id": None}, synchronize_session=False)
    db.query(models.WeeklyRaffle).filter(models.WeeklyRaffle.winner_id == uid).update({"winner_id": None}, synchronize_session=False)
    db.query(models.ModLog).filter(models.ModLog.actor_id == uid).update({"actor_id": None}, synchronize_session=False)
    delete_file(user.avatar)
    delete_file(user.cover)
    db.flush()
    db.delete(user)
    db.commit()


@router.post("/delete-account")
@router.post("/settings/delete_account")
async def delete_account(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    data = await read_payload(request)
    if not auth.verify_password(data.get("password") or "", user.password):
        if wants_json(request):
            return json_error("Неверный пароль", 403)
        return _settings(request, db, user, "data", error="Для удаления аккаунта введите верный пароль")
    if user.is_owner:
        return _settings(request, db, user, "data", error="Владелец сервиса не может удалить аккаунт")
    purge_user(db, user)
    resp = JSONResponse({"ok": True}) if wants_json(request) else redirect("/")
    resp.delete_cookie(auth.COOKIE_NAME)
    return resp
