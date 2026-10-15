"""Пакет функций №3: история правок и архив постов, QR и отправка поста в чат, напоминания, предпросмотр,
редактирование/скрытие/жалобы на комментарии, статус и ссылки в профиле, рамки и заморозка стрика,
«не беспокоить», пауза аккаунта, колесо фортуны, случайный пост, топ недели, люди из города, заметки,
личная статистика, инструменты админа."""
import csv
import io
import json
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

import config
import models
from database import get_db
from deps import current_user, json_error, log_mod, login_redirect, redirect, render
from routers.posts import _get_post, purge_post, read_payload, wants_json
from services import extras, feed, gamification, social, text
from services.text import censor

router = APIRouter()


def _ok(request, url):
    return JSONResponse({"ok": True}) if wants_json(request) else redirect(url)


# ======================================= Посты =======================================
@router.get("/post/{post_id}/history")
def post_history(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    post = _get_post(db, post_id)
    if not social.can_view_post(db, user, post):
        return redirect("/")
    edits = db.query(models.PostEdit).filter_by(post_id=post_id).order_by(models.PostEdit.created_at.desc()).all()
    return render(request, db, "post_history.html", post=post, edits=edits)


@router.post("/post/{post_id}/archive")
def post_archive(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    post = _get_post(db, post_id)
    if not user or not post or post.user_id != user.id:
        return json_error("not found", 404)
    post.is_archived = not post.is_archived
    db.commit()
    return JSONResponse({"ok": True, "archived": post.is_archived})


@router.get("/archive")
def archive_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    posts = (feed.with_loads(db.query(models.Post)).filter(models.Post.user_id == user.id, models.Post.is_archived == True)
             .order_by(models.Post.created_at.desc()).limit(200).all())
    return render(request, db, "archive.html", **feed.feed_context(db, user, posts))


@router.get("/post/{post_id}/qr")
def post_qr_page(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    post = _get_post(db, post_id)
    if not social.can_view_post(db, user, post):
        return redirect("/")
    return render(request, db, "post_qr.html", post=post)


@router.get("/post/{post_id}/qr.svg")
def post_qr_svg(post_id: int, db: Session = Depends(get_db)):
    import qrcode
    import qrcode.image.svg
    img = qrcode.make(f"{config.SITE_URL}/post/{post_id}", image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=1)
    buf = io.BytesIO()
    img.save(buf)
    return Response(buf.getvalue(), media_type="image/svg+xml")


@router.post("/post/{post_id}/send")
async def post_send(post_id: int, request: Request, db: Session = Depends(get_db)):
    """Отправить пост в личные сообщения."""
    from routers.messages import _deliver
    user = current_user(request, db)
    post = _get_post(db, post_id)
    if not user or not social.can_view_post(db, user, post):
        return json_error("not found", 404)
    data = await read_payload(request)
    other = db.query(models.User).filter(models.User.username == (data.get("username") or "").strip().lstrip("@")).first()
    if not other or other.id == user.id:
        return json_error("Пользователь не найден")
    allowed, reason = social.can_message(db, user, other)
    if not allowed:
        return json_error(reason or "Нельзя написать этому пользователю", 403)
    note = censor((data.get("note") or "").strip()[:300], social.stop_words(db))
    preview = (post.content or "медиа")[:80]
    msg = models.Message(sender_id=user.id, receiver_id=other.id,
                         content=(note + "\n" if note else "") + f"Пост @{post.author.username}: «{preview}» {config.SITE_URL}/post/{post.id}")
    return _deliver(db, user, other, msg)


@router.post("/post/{post_id}/remind")
async def post_remind(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    post = _get_post(db, post_id)
    if not user or not social.can_view_post(db, user, post):
        return json_error("not found", 404)
    data = await read_payload(request)
    try:
        hours = max(1, min(int(data.get("hours") or 24), 24 * 30))
    except ValueError:
        hours = 24
    db.add(models.PostReminder(user_id=user.id, post_id=post_id, remind_at=datetime.utcnow() + timedelta(hours=hours)))
    db.commit()
    return JSONResponse({"ok": True, "hours": hours})


def deliver_reminders(db, user):
    """Превращает наступившие напоминания в уведомления. Вызывается при открытии страниц."""
    due = db.query(models.PostReminder).filter(models.PostReminder.user_id == user.id, models.PostReminder.done == False,
                                               models.PostReminder.remind_at <= datetime.utcnow()).limit(10).all()
    for r in due:
        r.done = True
        if db.get(models.Post, r.post_id):
            db.add(models.Notification(user_id=user.id, type="system", post_id=r.post_id, text="Вы просили напомнить об этом посте"))
    if due:
        db.commit()


@router.post("/api/preview")
async def preview(request: Request, db: Session = Depends(get_db)):
    data = await read_payload(request)
    return JSONResponse({"ok": True, "html": str(text.richtext((data.get("content") or "")[:5000]))})


# ===================================== Комментарии =====================================
@router.post("/comment/{comment_id}/edit")
async def comment_edit(comment_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    c = db.get(models.Comment, comment_id)
    if not user or not c or c.user_id != user.id:
        return json_error("not found", 404)
    data = await read_payload(request)
    content = censor((data.get("content") or "").strip()[:2000], social.stop_words(db))
    if not content:
        return json_error("Пустой комментарий")
    c.content, c.edited_at = content, datetime.utcnow()
    from services import moderation
    moderation.review(db, "comment", c, user, content)
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/comment/{comment_id}/hide")
def comment_hide(comment_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    c = db.get(models.Comment, comment_id)
    post = _get_post(db, c.post_id) if c else None
    if not user or not c or not post or (post.user_id != user.id and not social.can_mod(user)):
        return json_error("forbidden", 403)
    c.is_hidden = not c.is_hidden
    db.commit()
    return JSONResponse({"ok": True, "hidden": c.is_hidden})


@router.post("/comment/{comment_id}/report")
def comment_report(comment_id: int, request: Request, db: Session = Depends(get_db)):
    """Жалоба на комментарий попадает в очередь «Нейромодерация» с пометкой «жалоба»."""
    user = current_user(request, db)
    c = db.get(models.Comment, comment_id)
    if not user or not c:
        return json_error("not found", 404)
    if not db.query(models.ModerationFlag).filter_by(kind="comment", object_id=c.id, status="new").first():
        db.add(models.ModerationFlag(kind="comment", object_id=c.id, post_id=c.post_id, user_id=c.user_id, label="report",
                                     score=0.5, snippet=(c.content or "")[:500]))
        db.commit()
    return JSONResponse({"ok": True})


# ======================================= Профиль =======================================
@router.post("/settings/links")
async def set_links(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    form = await request.form()
    links = []
    from services import plus
    for i in range(plus.limit(user, "links")):
        url = (form.get(f"link_url_{i}") or "").strip()[:200]
        if not url:
            continue
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        links.append({"title": (form.get(f"link_title_{i}") or "").strip()[:40] or url.split("//", 1)[1][:40], "url": url})
    user.links = json.dumps(links, ensure_ascii=False)
    db.commit()
    return redirect("/settings?section=profile&saved=1")


@router.post("/settings/pause")
async def set_pause(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    user.is_paused = not user.is_paused
    db.commit()
    return redirect("/settings?section=privacy&saved=1")


@router.post("/settings/dnd")
async def set_dnd(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    data = await read_payload(request)
    hours = str(data.get("hours") or "0")
    user.dnd_until = datetime.utcnow() + timedelta(hours=int(hours)) if hours.isdigit() and int(hours) > 0 else None
    db.commit()
    return _ok(request, "/settings?section=notifications&saved=1")


# =================================== Магазин и колесо ===================================
@router.get("/shop")
def shop_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    owned = set(filter(None, (user.frames_owned or "").split(",")))
    return render(request, db, "shop.html", frames=extras.FRAMES, owned=owned, balance=extras.balance(user),
                  freeze_price=extras.STREAK_FREEZE_PRICE)


@router.post("/shop/frame/{code}")
def shop_frame(code: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    f = extras.FRAME_BY.get(code)
    if not user:
        return login_redirect(request)
    owned = set(filter(None, (user.frames_owned or "").split(",")))
    if code == "none":
        user.avatar_frame = ""
    elif f and code in owned:
        user.avatar_frame = code
    elif f and (social.is_plus(user) or extras.balance(user) >= f[2]):
        user.spent_points = (user.spent_points or 0) + (0 if social.is_plus(user) else f[2])
        owned.add(code)
        user.frames_owned = ",".join(sorted(owned))
        user.avatar_frame = code
        gamification.check_achievement(user, db, "stylist")
    else:
        db.commit()
        return redirect("/shop?err=points")
    db.commit()
    return redirect("/shop")


@router.post("/shop/freeze")
def shop_freeze(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    if extras.balance(user) >= extras.STREAK_FREEZE_PRICE and (user.streak_freezes or 0) < 5:
        user.spent_points = (user.spent_points or 0) + extras.STREAK_FREEZE_PRICE
        user.streak_freezes = (user.streak_freezes or 0) + 1
        db.commit()
    return redirect("/shop")


@router.get("/wheel")
def wheel_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    from services import plus
    today = date.today().isoformat()
    spins_left = (0 if user.last_spin == today else 1) + (1 if plus.active(user) and user.last_spin2 != today else 0)
    return render(request, db, "wheel.html", spun=spins_left == 0, spins_left=spins_left, prizes=extras.WHEEL)


@router.post("/wheel/spin")
def wheel_spin(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    today = date.today().isoformat()
    from services import plus
    if user.last_spin == today:
        if not plus.active(user) or user.last_spin2 == today:
            return json_error("Колесо можно крутить раз в день — приходите завтра" if not plus.active(user)
                              else "Оба вращения на сегодня использованы — приходите завтра")
        prize = extras.spin_prize(user.id, today + ":2")
        user.last_spin2 = today
    else:
        prize = extras.spin_prize(user.id, today)
        user.last_spin = today
    gamification.add_points(user, db, prize)
    gamification.check_achievement(user, db, "lucky")
    db.commit()
    return JSONResponse({"ok": True, "prize": prize, "index": [i for i, p in enumerate(extras.WHEEL) if p == prize][0]})


# =================================== Поиск интересного ===================================
@router.get("/random")
def random_post(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    p = social.visible_posts(db, user).filter(models.Post.is_repost == False).order_by(func.random()).first()
    return redirect(f"/post/{p.id}" if p else "/explore")


@router.get("/top")
def top_week(request: Request, period: str = "week", db: Session = Depends(get_db)):
    user = current_user(request, db)
    days = {"day": 1, "week": 7, "month": 31}.get(period, 7)
    pool = (feed.with_loads(social.visible_posts(db, user)).filter(models.Post.created_at > datetime.utcnow() - timedelta(days=days),
                                                                    models.Post.is_repost == False).limit(500).all())
    pool.sort(key=lambda p: len(p.likes) * 3 + len(p.comments) * 4 + len(p.reactions) * 2 + len(p.whales) * 2 + (p.views or 0) * .05, reverse=True)
    return render(request, db, "top.html", period=period if period in ("day", "week", "month") else "week",
                  **feed.feed_context(db, user, pool[:30]))


@router.get("/people/city")
def city_people(request: Request, city: str = "", db: Session = Depends(get_db)):
    user = current_user(request, db)
    city = (city or (user.city if user else "") or "").strip()[:60]
    people = []
    if city:
        hidden = social.blocked_ids(db, user) | ({user.id} if user else set())
        from services import prefs
        people = (db.query(models.User).filter(func.lower(models.User.city) == city.lower(), ~models.User.id.in_(hidden or {-1}),
                                               models.User.is_blocked == False, prefs.sql_flag_off(models.User.prefs, "hide_from_search"))
                  .order_by(models.User.last_seen.desc()).limit(100).all())
    return render(request, db, "city.html", city=city, people=people, following=social.following_ids(db, user))


# ======================================= Заметки =======================================
@router.get("/notes")
def notes_page(request: Request, edit: int = 0, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    notes = (db.query(models.Note).filter_by(user_id=user.id)
             .order_by(models.Note.is_pinned.desc(), models.Note.updated_at.desc()).all())
    current = next((n for n in notes if n.id == edit), None)
    return render(request, db, "notes.html", notes=notes, current=current)


@router.post("/notes/save")
async def notes_save(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    form = await request.form()
    nid = form.get("id")
    note = db.query(models.Note).filter_by(id=int(nid), user_id=user.id).first() if nid and str(nid).isdigit() else None
    if not note:
        if db.query(models.Note).filter_by(user_id=user.id).count() >= 500:
            return redirect("/notes")
        note = models.Note(user_id=user.id)
        db.add(note)
    note.title = (form.get("title") or "").strip()[:120] or "Без названия"
    note.content = (form.get("content") or "")[:20000]
    note.updated_at = datetime.utcnow()
    db.commit()
    return redirect(f"/notes?edit={note.id}")


@router.post("/notes/{nid}/{action}")
def notes_action(nid: int, action: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    note = db.query(models.Note).filter_by(id=nid, user_id=user.id).first() if user else None
    if note and action == "delete":
        db.delete(note)
    elif note and action == "pin":
        note.is_pinned = not note.is_pinned
    db.commit()
    return redirect("/notes")


# =================================== Личная статистика ===================================
@router.get("/stats")
def my_stats(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    from services import timezones
    posts = feed.with_loads(db.query(models.Post)).filter(models.Post.user_id == user.id, models.Post.is_repost == False).all()
    now = datetime.utcnow()
    # активность за 26 недель (тепловая карта)
    start = (now - timedelta(days=7 * 26)).date()
    start -= timedelta(days=start.weekday())
    days = {}
    for p in posts:
        d = timezones.to_local(p.created_at, user).date()
        if d >= start:
            days[d] = days.get(d, 0) + 1
    for c in db.query(models.Comment.created_at).filter(models.Comment.user_id == user.id, models.Comment.created_at >= datetime.combine(start, datetime.min.time())):
        d = timezones.to_local(c.created_at, user).date()
        days[d] = days.get(d, 0) + 1
    cells = []
    d = start
    while d <= now.date():
        n = days.get(d, 0)
        cells.append((d, n, 0 if n == 0 else 1 if n == 1 else 2 if n <= 3 else 3 if n <= 6 else 4))
        d += timedelta(days=1)
    # лучшее время для публикации: в какие часы ваши посты собирают больше всего реакций
    hours = [0.0] * 24
    counts = [0] * 24
    for p in posts:
        h = timezones.to_local(p.created_at, user).hour
        hours[h] += len(p.likes) + len(p.comments) * 2 + len(p.reactions)
        counts[h] += 1
    avg = [hours[h] / counts[h] if counts[h] else 0 for h in range(24)]
    best = max(range(24), key=lambda h: avg[h]) if any(avg) else None
    top = sorted(posts, key=lambda p: len(p.likes) * 3 + len(p.comments) * 4 + len(p.reactions) * 2, reverse=True)[:5]
    totals = {"posts": len(posts), "likes": sum(len(p.likes) for p in posts), "comments": sum(len(p.comments) for p in posts),
              "views": sum(p.views or 0 for p in posts), "followers": db.query(models.Follow).filter_by(following_id=user.id).count(),
              "following": db.query(models.Follow).filter_by(follower_id=user.id).count()}
    return render(request, db, "stats.html", cells=cells, avg=avg, avg_max=max(avg + [1]), best=best, top=top, totals=totals,
                  active_days=sum(1 for _, n, _ in cells if n), **feed.feed_context(db, user, top))


# ======================================== Админ ========================================
@router.get("/admin/export/users.csv")
def export_users(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user or not user.is_owner:
        return redirect("/")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "username", "name", "email", "created_at", "last_seen", "posts", "points", "level", "is_blocked"])
    counts = dict(db.query(models.Post.user_id, func.count(models.Post.id)).group_by(models.Post.user_id).all())
    for u in db.query(models.User).order_by(models.User.id):
        w.writerow([u.id, u.username, u.name, u.email, u.created_at, u.last_seen, counts.get(u.id, 0), u.total_points, u.level, u.is_blocked])
    log_mod(db, user, "export_users", "", "")
    db.commit()
    return StreamingResponse(iter(["﻿" + buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=nuvora-users.csv"})


@router.post("/admin/purge-posts/{username}")
def purge_user_posts(username: str, request: Request, db: Session = Depends(get_db)):
    """Удалить все посты пользователя (например, спам-аккаунта)."""
    user = current_user(request, db)
    target = db.query(models.User).filter_by(username=username).first()
    if not user or not social.can_mod(user) or not target or target.is_owner:
        return redirect("/")
    ids = [p.id for p in db.query(models.Post.id).filter_by(user_id=target.id)]
    for pid in ids:
        p = db.get(models.Post, pid)
        if p:
            purge_post(db, p)
    log_mod(db, user, "purge_posts", target.username, f"{len(ids)} постов")
    db.commit()
    return redirect(f"/profile/{target.username}")
