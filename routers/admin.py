import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import config
import models
from database import get_db
from deps import current_user, log_mod, redirect, render
from services import gamification, legal, social

router = APIRouter()


def _owner(request, db):
    user = current_user(request, db)
    return user if user and user.is_owner else None


def _mod(request, db):
    user = current_user(request, db)
    return user if social.can_mod(user) else None


def _target(db, username):
    return db.query(models.User).filter(func.lower(models.User.username) == username.lower()).first()


def _back(request, fallback="/admin"):
    ref = request.headers.get("referer") or ""
    return redirect(ref if ref else fallback)


@router.get("/admin")
def admin_page(request: Request, tab: str = "dashboard", q: str = "", db: Session = Depends(get_db)):
    user = _mod(request, db)
    if not user:
        return redirect("/")
    now = datetime.utcnow()
    day, week = now - timedelta(days=1), now - timedelta(days=7)
    stats = {
        "users": db.query(models.User).count(), "users_day": db.query(models.User).filter(models.User.created_at > day).count(),
        "users_week": db.query(models.User).filter(models.User.created_at > week).count(),
        "online": db.query(models.User).filter(models.User.last_seen > now - timedelta(minutes=5)).count(),
        "dau": db.query(models.User).filter(models.User.last_seen > day).count(),
        "posts": db.query(models.Post).count(), "posts_day": db.query(models.Post).filter(models.Post.created_at > day).count(),
        "messages": db.query(models.Message).count(), "comments": db.query(models.Comment).count(),
        "stories": db.query(models.Story).filter(models.Story.expires_at > now).count(),
        "groups": db.query(models.GroupChat).count(), "plus": db.query(models.User).filter(models.User.is_plus == True,
                                                                                           or_(models.User.plus_until == None, models.User.plus_until > now)).count(),
        "banned": db.query(models.User).filter(models.User.is_blocked == True).count(),
    }
    chart = []
    for i in range(13, -1, -1):
        d0 = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        d1 = d0 + timedelta(days=1)
        chart.append({"label": d0.strftime("%d.%m"),
                      "users": db.query(models.User).filter(models.User.created_at >= d0, models.User.created_at < d1).count(),
                      "posts": db.query(models.Post).filter(models.Post.created_at >= d0, models.Post.created_at < d1).count()})
    users_q = db.query(models.User)
    if q:
        term = f"%{q.strip().lstrip('@')}%"
        users_q = users_q.filter(or_(models.User.username.ilike(term), models.User.name.ilike(term), models.User.email.ilike(term)))
    ctx = dict(tab=tab, q=q, stats=stats, chart=chart, chart_max=max([1] + [max(c["users"], c["posts"]) for c in chart]),
               all_users=users_q.order_by(models.User.created_at.desc()).limit(200).all(),
               post_reports=db.query(models.PostReport).filter_by(status="new").order_by(models.PostReport.created_at.desc()).all(),
               user_reports=db.query(models.Report).filter_by(status="new").order_by(models.Report.created_at.desc()).all(),
               special_requests=db.query(models.SpecialRequest).filter_by(status="new").order_by(models.SpecialRequest.created_at.desc()).all(),
               promocodes=db.query(models.Promocode).order_by(models.Promocode.created_at.desc()).limit(100).all(),
               stop_words=db.query(models.StopWord).order_by(models.StopWord.word).all(),
               announcements=db.query(models.Announcement).order_by(models.Announcement.created_at.desc()).limit(20).all(),
               challenges=db.query(models.WeeklyChallenge).order_by(models.WeeklyChallenge.created_at.desc()).limit(20).all(),
               raffle=gamification.current_raffle(db), logs=db.query(models.ModLog).order_by(models.ModLog.created_at.desc()).limit(100).all(),
               support=db.query(models.Notification).filter_by(type="support").order_by(models.Notification.created_at.desc()).limit(50).all(),
               legal=legal.checklist(db) if tab == "legal" else [],
               ai_flags=db.query(models.ModerationFlag).filter_by(status="new").order_by(models.ModerationFlag.score.desc()).limit(200).all(),
               ai_stats={k: db.query(models.ModerationFlag).filter_by(status=k).count() for k in ("new", "approved", "removed")}
               | {"all": db.query(models.ModerationFlag).count()},
               mod_cfg={"enabled": config.MODERATION_ENABLED, "flag": config.MOD_FLAG_THRESHOLD, "hold": config.MOD_HOLD_THRESHOLD},
               is_owner=user.is_owner)
    return render(request, db, "admin.html", sidebar=False, **ctx)


@router.post("/admin/block/{username}")
async def admin_block(username: str, request: Request, db: Session = Depends(get_db)):
    user = _mod(request, db)
    if not user:
        return redirect("/")
    form = await request.form()
    try:
        days = max(1, min(int(form.get("days") or 1), 3650))
    except ValueError:
        days = 1
    target = _target(db, username)
    if target and not target.is_owner and (user.is_owner or not target.is_moderator):
        target.is_blocked, target.blocked_until = True, datetime.utcnow() + timedelta(days=days)
        db.query(models.UserSession).filter_by(user_id=target.id).update({"is_active": False})
        db.add(models.Notification(user_id=target.id, type="moderation", text=f"Аккаунт заблокирован на {days} дн. Причина: {(form.get('reason') or 'нарушение правил')[:200]}"))
        log_mod(db, user, "block", target.username, f"{days} дн.; {form.get('reason') or ''}")
        db.commit()
    return _back(request)


@router.post("/admin/unblock/{username}")
def admin_unblock(username: str, request: Request, db: Session = Depends(get_db)):
    user = _mod(request, db)
    target = _target(db, username)
    if user and target:
        target.is_blocked, target.blocked_until = False, None
        log_mod(db, user, "unblock", target.username)
        db.commit()
    return _back(request)


def _owner_toggle(request, db, username, field, action):
    user = _owner(request, db)
    target = _target(db, username)
    if user and target:
        setattr(target, field, not getattr(target, field))
        log_mod(db, user, action, target.username, str(getattr(target, field)))
        db.commit()
    return _back(request)


@router.post("/admin/star/{username}")
def admin_star(username: str, request: Request, db: Session = Depends(get_db)):
    return _owner_toggle(request, db, username, "is_starred", "star")


@router.post("/admin/verify/{username}")
def admin_verify(username: str, request: Request, db: Session = Depends(get_db)):
    return _owner_toggle(request, db, username, "is_verified_badge", "verify")


@router.post("/admin/mod/{username}")
def admin_mod(username: str, request: Request, db: Session = Depends(get_db)):
    return _owner_toggle(request, db, username, "is_moderator", "moderator")


@router.post("/admin/plus/{username}")
async def admin_plus(username: str, request: Request, db: Session = Depends(get_db)):
    user = _owner(request, db)
    target = _target(db, username)
    if user and target:
        form = await request.form()
        days = int(form.get("days") or 30) if str(form.get("days") or "30").isdigit() else 30
        gamification.grant_plus(target, days)
        db.add(models.Notification(user_id=target.id, type="system", text=f"Вам подарили Plus на {days} дней ✨"))
        log_mod(db, user, "grant_plus", target.username, f"{days}")
        db.commit()
    return _back(request)


@router.post("/admin/points/{username}")
async def admin_points(username: str, request: Request, db: Session = Depends(get_db)):
    user = _owner(request, db)
    target = _target(db, username)
    if user and target:
        form = await request.form()
        try:
            pts = max(-100000, min(int(form.get("points") or 0), 100000))
        except ValueError:
            pts = 0
        gamification.add_points(target, db, pts)
        log_mod(db, user, "points", target.username, str(pts))
        db.commit()
    return _back(request)


@router.post("/admin/reset-password/{username}")
def admin_reset_password(username: str, request: Request, db: Session = Depends(get_db)):
    user = _owner(request, db)
    target = _target(db, username)
    if not user or not target:
        return redirect("/admin?tab=users")
    import auth
    temp = secrets.token_urlsafe(6).replace("-", "x").replace("_", "y") + "7"
    target.password = auth.hash_password(temp)
    db.query(models.UserSession).filter_by(user_id=target.id).update({"is_active": False})
    log_mod(db, user, "reset_password", target.username)
    db.commit()
    return render(request, db, "error.html", sidebar=False, code="🔑", title=f"Новый пароль для @{target.username}",
                  text=f"Временный пароль: {temp} — передайте его пользователю. Сменить его можно в Настройки → Аккаунт.")


@router.post("/admin/delete-user/{username}")
def admin_delete_user(username: str, request: Request, db: Session = Depends(get_db)):
    user = _owner(request, db)
    target = _target(db, username)
    if user and target and not target.is_owner:
        from routers.settings import purge_user
        log_mod(db, user, "delete_user", target.username)
        db.commit()
        purge_user(db, target)
    return redirect("/admin?tab=users")


@router.post("/admin/create_promo")
async def admin_create_promo(request: Request, db: Session = Depends(get_db)):
    user = _owner(request, db)
    if not user:
        return redirect("/")
    form = await request.form()
    code = (form.get("code") or "").upper().strip() or secrets.token_hex(4).upper()
    try:
        days, max_uses = int(form.get("days") or 30), int(form.get("max_uses") or 1)
    except ValueError:
        days, max_uses = 30, 1
    if not db.query(models.Promocode).filter_by(code=code).first():
        db.add(models.Promocode(code=code[:40], days=max(1, days), max_uses=max(1, max_uses)))
        log_mod(db, user, "promo", code)
        db.commit()
    return redirect("/admin?tab=plus")


@router.post("/admin/promo/{promo_id}/toggle")
def admin_promo_toggle(promo_id: int, request: Request, db: Session = Depends(get_db)):
    user = _owner(request, db)
    p = db.get(models.Promocode, promo_id)
    if user and p:
        p.is_active = not p.is_active
        db.commit()
    return redirect("/admin?tab=plus")


@router.post("/admin/reports/post/{report_id}/{action}")
def admin_post_report(report_id: int, action: str, request: Request, db: Session = Depends(get_db)):
    user = _mod(request, db)
    r = db.get(models.PostReport, report_id)
    if user and r:
        if action == "delete" and r.post:
            from routers.posts import purge_post
            log_mod(db, user, "delete_post", r.post_id, (r.post.content or "")[:200])
            pid = r.post_id
            db.query(models.PostReport).filter_by(post_id=pid).update({"status": "resolved", "post_id": None})
            db.flush()
            purge_post(db, db.get(models.Post, pid))
        else:
            r.status = "dismissed"
        db.commit()
    return redirect("/admin?tab=reports")


@router.post("/admin/reports/user/{report_id}/{action}")
async def admin_user_report(report_id: int, action: str, request: Request, db: Session = Depends(get_db)):
    user = _mod(request, db)
    r = db.get(models.Report, report_id)
    if user and r:
        form = await request.form()
        r.status = "resolved" if action == "resolve" else "dismissed"
        r.admin_comment = (form.get("comment") or "")[:500]
        db.add(models.Notification(user_id=r.reporter_id, type="moderation",
                                   text=f"Ваша жалоба рассмотрена: {'меры приняты' if action == 'resolve' else 'нарушений не найдено'}"))
        log_mod(db, user, f"report_{action}", r.target.username if r.target else r.target_id)
        db.commit()
    return redirect("/admin?tab=reports")


@router.post("/admin/requests/{req_id}/{action}")
async def admin_special_request(req_id: int, action: str, request: Request, db: Session = Depends(get_db)):
    user = _owner(request, db)
    r = db.get(models.SpecialRequest, req_id)
    if user and r and r.user:
        form = await request.form()
        r.admin_comment = (form.get("comment") or "")[:500]
        if action == "approve":
            r.status = "approved"
            if r.type == "verify":
                r.user.is_verified_badge = True
            elif r.type == "star":
                r.user.is_starred = True
            elif r.type == "unblock":
                r.user.is_blocked, r.user.blocked_until = False, None
        else:
            r.status = "rejected"
        db.add(models.Notification(user_id=r.user_id, type="moderation",
                                   text=f"Заявка «{r.type}» {'одобрена ✅' if action == 'approve' else 'отклонена'}. {r.admin_comment}"))
        log_mod(db, user, f"request_{action}", r.user.username, r.type)
        db.commit()
    return redirect("/admin?tab=requests")


@router.post("/admin/ai/{flag_id}/{action}")
def admin_ai_flag(flag_id: int, action: str, request: Request, db: Session = Depends(get_db)):
    """Решение модератора по пометке нейросети: approve — всё в порядке, remove — удалить."""
    user = _mod(request, db)
    f = db.get(models.ModerationFlag, flag_id)
    if not user or not f or f.status != "new":
        return redirect("/admin?tab=ai")
    if action == "approve":
        if f.kind == "post" and f.held:
            post = db.get(models.Post, f.object_id)
            if post:
                post.is_published = True
                social.notify(db, f.user_id, "moderation", None, None, text="Модератор проверил ваш пост — он опубликован ✅")
        f.status = "approved"
        log_mod(db, user, "ai_approve", f"{f.kind}:{f.object_id}", f.snippet[:200])
    elif action == "remove":
        if f.kind == "post":
            post = db.get(models.Post, f.object_id)
            if post:
                from routers.posts import purge_post
                db.query(models.PostReport).filter_by(post_id=post.id).update({"status": "resolved", "post_id": None})
                db.flush()
                purge_post(db, post)
        else:
            c = db.get(models.Comment, f.object_id)
            if c:
                ids, frontier = [c.id], [c.id]
                while frontier:
                    frontier = [k.id for k in db.query(models.Comment.id).filter(models.Comment.parent_id.in_(frontier))]
                    ids += frontier
                db.query(models.CommentLike).filter(models.CommentLike.comment_id.in_(ids)).delete(synchronize_session=False)
                db.query(models.Comment).filter(models.Comment.id.in_(ids)).update({"parent_id": None}, synchronize_session=False)
                db.query(models.Comment).filter(models.Comment.id.in_(ids)).delete(synchronize_session=False)
        db.query(models.ModerationFlag).filter_by(kind=f.kind, object_id=f.object_id, status="new").update({"status": "removed"})
        social.notify(db, f.user_id, "moderation", None, None,
                      text="Ваш " + ("пост" if f.kind == "post" else "комментарий") + " удалён модератором за нарушение правил.")
        log_mod(db, user, "ai_remove", f"{f.kind}:{f.object_id}", f.snippet[:200])
    db.commit()
    return redirect("/admin?tab=ai")


@router.post("/admin/stopwords")
async def admin_stopwords(request: Request, db: Session = Depends(get_db)):
    user = _mod(request, db)
    if not user:
        return redirect("/")
    form = await request.form()
    word = (form.get("word") or "").strip().lower()[:50]
    if word and not db.query(models.StopWord).filter_by(word=word).first():
        db.add(models.StopWord(word=word))
        db.commit()
    return redirect("/admin?tab=moderation")


@router.post("/admin/stopwords/{word_id}/delete")
def admin_stopword_delete(word_id: int, request: Request, db: Session = Depends(get_db)):
    if _mod(request, db):
        db.query(models.StopWord).filter_by(id=word_id).delete()
        db.commit()
    return redirect("/admin?tab=moderation")


@router.post("/admin/announce")
async def admin_announce(request: Request, db: Session = Depends(get_db)):
    user = _owner(request, db)
    if not user:
        return redirect("/")
    form = await request.form()
    text = (form.get("text") or "").strip()[:500]
    if text:
        db.query(models.Announcement).update({"is_active": False})
        db.add(models.Announcement(text=text, level=form.get("level") if form.get("level") in ("info", "warning", "success") else "info"))
        if form.get("notify_all"):
            for (uid,) in db.query(models.User.id).all():
                db.add(models.Notification(user_id=uid, type="system", text=text))
        log_mod(db, user, "announce", "", text)
        db.commit()
    return redirect("/admin?tab=content")


@router.post("/admin/announce/off")
def admin_announce_off(request: Request, db: Session = Depends(get_db)):
    if _owner(request, db):
        db.query(models.Announcement).update({"is_active": False})
        db.commit()
    return redirect("/admin?tab=content")


@router.post("/admin/challenge")
async def admin_challenge(request: Request, db: Session = Depends(get_db)):
    user = _owner(request, db)
    if not user:
        return redirect("/")
    form = await request.form()
    ttype = form.get("task_type") if form.get("task_type") in ("post", "like", "comment", "follow", "story", "message", "login") else "post"
    now = datetime.utcnow()
    try:
        target, points = max(1, int(form.get("target_count") or 5)), max(1, int(form.get("points") or 100))
    except ValueError:
        target, points = 5, 100
    db.query(models.WeeklyChallenge).filter_by(is_active=True).update({"is_active": False})
    db.add(models.WeeklyChallenge(title=(form.get("title") or "Челлендж недели")[:80], description=(form.get("description") or "")[:200],
                                  emoji=(form.get("emoji") or "🏆")[:4], points=points, task_type=ttype, target_count=target,
                                  week_start=now, week_end=now + timedelta(days=7)))
    log_mod(db, user, "challenge", ttype)
    db.commit()
    return redirect("/admin?tab=content")


@router.post("/admin/raffle/draw")
def admin_raffle_draw(request: Request, db: Session = Depends(get_db)):
    user = _owner(request, db)
    if not user:
        return redirect("/")
    raffle = gamification.current_raffle(db)
    gamification.draw_raffle(db, raffle)
    db.query(models.User).update({"weekly_points": 0})
    log_mod(db, user, "raffle_draw", raffle.winner.username if raffle.winner else "-")
    db.commit()
    return redirect("/admin?tab=content")


@router.get("/api/admin/stats")
def admin_stats_api(request: Request, db: Session = Depends(get_db)):
    if not _mod(request, db):
        return JSONResponse({"ok": False}, status_code=403)
    now = datetime.utcnow()
    return JSONResponse({"ok": True, "online": db.query(models.User).filter(models.User.last_seen > now - timedelta(minutes=5)).count(),
                         "users": db.query(models.User).count(), "posts": db.query(models.Post).count()})
