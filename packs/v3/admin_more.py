"""Ещё разделы админ-панели владельца: посты, статистика, хранилище, выгрузка пользователей.
Переписку здесь тоже не читаем: по сообщениям видны только количества."""
import csv
import io
import os
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, quote, urlencode, urlparse

from fastapi import Depends, Request
from fastapi.responses import Response
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import config
import models
from database import engine, get_db
from deps import log_mod, redirect, render
from routers.posts import purge_post

from . import media
from . import models as m
from .admin_plus import _owner, _staff
from .common import router, s


# ---------------------------------------------------------------- посты
@router.get("/admin/posts")
def posts_page(request: Request, q: str = "", f: str = "all", ok: str = "", db: Session = Depends(get_db)):
    me = _staff(request, db)
    if not me:
        return redirect("/")
    query = db.query(models.Post).filter(models.Post.is_repost != True)  # noqa: E712
    if f == "held":
        query = query.filter(models.Post.is_published == False)  # noqa: E712
    elif f == "reported":
        query = query.filter(models.Post.id.in_(db.query(models.PostReport.post_id).filter_by(status="new")))
    elif f == "media":
        query = query.filter(models.Post.image != "")
    q = q.strip()
    if q.startswith("@"):
        u = db.query(models.User).filter(func.lower(models.User.username) == q[1:].lower()).first()
        query = query.filter(models.Post.user_id == (u.id if u else 0))
    elif q:
        query = query.filter(models.Post.content.ilike(f"%{q}%"))
    posts = query.order_by(models.Post.created_at.desc()).limit(60).all()
    ids = [p.id for p in posts] or [0]
    likes = dict(db.query(models.Like.post_id, func.count()).filter(models.Like.post_id.in_(ids)).group_by(models.Like.post_id))
    comments = dict(db.query(models.Comment.post_id, func.count()).filter(models.Comment.post_id.in_(ids)).group_by(models.Comment.post_id))
    reports = dict(db.query(models.PostReport.post_id, func.count()).filter(models.PostReport.post_id.in_(ids), models.PostReport.status == "new")
                   .group_by(models.PostReport.post_id))
    return render(request, db, "packs/v3/admin_posts.html", sidebar=False, posts=posts, q=q, f=f, ok=ok,
                  likes=likes, comments=comments, reports=reports)


@router.post("/admin/posts/{pid}/{act}")
def post_action(pid: int, act: str, request: Request, db: Session = Depends(get_db)):
    me = _staff(request, db)
    p = db.get(models.Post, pid)
    if not me or not p:
        return redirect("/admin/posts")
    if act == "delete":
        log_mod(db, me, "admin_post_delete", p.author.username if p.author else "", (p.content or "")[:150])
        purge_post(db, p)
        msg = "Пост удалён"
    elif act == "hide":
        p.is_published = False
        log_mod(db, me, "admin_post_hide", p.author.username if p.author else "", f"post {p.id}")
        msg = "Пост скрыт из ленты"
    elif act == "publish":
        p.is_published = True
        p.scheduled_at = None
        log_mod(db, me, "admin_post_publish", p.author.username if p.author else "", f"post {p.id}")
        msg = "Пост опубликован"
    else:
        return redirect("/admin/posts")
    db.commit()
    ref = urlparse(request.headers.get("referer") or "")  # вернуться к тому же поиску и фильтру
    qs = [(k, v) for k, v in parse_qsl(ref.query) if k != "ok"] if ref.path == "/admin/posts" else []
    return redirect("/admin/posts?" + urlencode(qs + [("ok", msg)]))


# ---------------------------------------------------------------- статистика
def _per_day(db, col, days, *filters):
    start = (datetime.utcnow() - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = {str(d)[:10]: n for d, n in db.query(func.date(col), func.count()).filter(col >= start, *filters).group_by(func.date(col))}
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        out.append((d.strftime("%d.%m"), rows.get(d.strftime("%Y-%m-%d"), 0)))
    return out


@router.get("/admin/stats")
def stats_page(request: Request, db: Session = Depends(get_db)):
    me = _owner(request, db)
    if not me:
        return redirect("/")
    now = datetime.utcnow()
    U = models.User
    act = {
        "dau": db.query(U).filter(U.last_seen > now - timedelta(days=1)).count(),
        "wau": db.query(U).filter(U.last_seen > now - timedelta(days=7)).count(),
        "mau": db.query(U).filter(U.last_seen > now - timedelta(days=30)).count(),
        "total": db.query(U).count(),
        "new30": db.query(U).filter(U.created_at > now - timedelta(days=30)).count(),
        "silent": db.query(U).filter(or_(U.last_seen == None, U.last_seen < now - timedelta(days=30))).count(),  # noqa: E711
    }
    act["stick"] = round(act["dau"] * 100 / act["mau"]) if act["mau"] else 0
    calls_q = db.query(m.Call).filter(m.Call.created_at > now - timedelta(days=30))
    talk = [(c.ended_at - c.answered_at).total_seconds() for c in calls_q.filter(m.Call.answered_at != None, m.Call.ended_at != None)]  # noqa: E711
    calls = {"all": calls_q.count(), "answered": len(talk), "missed": calls_q.filter(m.Call.status.in_(("missed", "declined", "busy"))).count(),
             "minutes": round(sum(talk) / 60), "avg": f"{int(sum(talk) / len(talk)) // 60}:{int(sum(talk) / len(talk)) % 60:02d}" if talk else "—"}
    week = now - timedelta(days=7)
    top_posts = (db.query(models.Post, func.count(models.Like.id).label("n")).join(models.Like, models.Like.post_id == models.Post.id)
                 .filter(models.Post.created_at > week).group_by(models.Post.id).order_by(func.count(models.Like.id).desc()).limit(8).all())
    top_authors = (db.query(U, func.count(models.Post.id)).join(models.Post, models.Post.user_id == U.id)
                   .filter(models.Post.created_at > week).group_by(U.id).order_by(func.count(models.Post.id).desc()).limit(8).all())
    series = {
        "Регистрации": _per_day(db, U.created_at, 30),
        "Посты": _per_day(db, models.Post.created_at, 30),
        "Комментарии": _per_day(db, models.Comment.created_at, 30),
        "Сообщения (только число)": _per_day(db, models.Message.created_at, 30),
    }
    trends = db.query(models.Trend).order_by(models.Trend.count.desc()).limit(12).all()
    return render(request, db, "packs/v3/admin_stats.html", sidebar=False, act=act, calls=calls, top_posts=top_posts,
                  top_authors=top_authors, series=series, trends=trends)


# ---------------------------------------------------------------- хранилище
def _dir_size(path):
    total = n = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
                n += 1
            except OSError:
                pass
    return total, n


def _mb(b):
    return f"{b / 1024 / 1024:.1f} МБ" if b < 1024 ** 3 else f"{b / 1024 ** 3:.2f} ГБ"


def _db_size(db):
    url = str(engine.url)
    try:
        if url.startswith("sqlite"):
            return os.path.getsize(engine.url.database)
        return db.execute(func.pg_database_size(func.current_database()).select()).scalar() or 0
    except Exception:  # noqa: BLE001
        return 0


@router.get("/admin/storage")
def storage_page(request: Request, ok: str = "", db: Session = Depends(get_db)):
    me = _owner(request, db)
    if not me:
        return redirect("/")
    up, up_n = _dir_size(config.UPLOAD_DIR)
    app_b, _ = _dir_size(config.APP_CACHE_DIR) if os.path.isdir(config.APP_CACHE_DIR) else (0, 0)
    cutoff = datetime.utcnow() - timedelta(days=media.KEEP_DAYS)
    chat_media = 0
    for model in (models.Message, models.GroupMessage):
        chat_media += db.query(model).filter(or_(model.image != "", model.voice != "", model.file_url != "")).count()
    old_media = sum(db.query(model).filter(model.created_at < cutoff, or_(model.image != "", model.voice != "", model.file_url != "")).count()
                    for model in (models.Message, models.GroupMessage))
    try:
        st = os.statvfs(config.UPLOAD_DIR)
        disk = {"free": st.f_bavail * st.f_frsize, "total": st.f_blocks * st.f_frsize}
    except (OSError, AttributeError):
        disk = None
    return render(request, db, "packs/v3/admin_storage.html", sidebar=False, ok=ok, up=_mb(up), up_n=up_n, app=_mb(app_b), dbs=_mb(_db_size(db)),
                  chat_media=chat_media, old_media=old_media, keep=media.KEEP_DAYS, signals=db.query(m.CallSignal).count(),
                  disk={k: _mb(v) for k, v in disk.items()} if disk else None,
                  disk_pct=round(100 - disk["free"] * 100 / disk["total"]) if disk and disk["total"] else None)


@router.post("/admin/storage/{act}")
def storage_action(act: str, request: Request, db: Session = Depends(get_db)):
    me = _owner(request, db)
    if not me:
        return redirect("/")
    if act == "chat-media":
        n = 0
        while True:  # пачками, пока есть что стирать
            k = media.expire_chat_media(db)
            n += k
            if k < media.BATCH:
                break
        msg = f"Стёрто вложений: {n}"
    elif act == "signals":
        n = db.query(m.CallSignal).filter(m.CallSignal.created_at < datetime.utcnow() - timedelta(minutes=10)).delete()
        msg = f"Удалено служебных записей звонков: {n}"
    else:
        return redirect("/admin/storage")
    log_mod(db, me, "admin_storage", act, msg)
    db.commit()
    return redirect("/admin/storage?ok=" + quote(msg))


# ---------------------------------------------------------------- выгрузка
@router.get("/admin/export/users.csv")
def export_users(request: Request, db: Session = Depends(get_db)):
    me = _owner(request, db)
    if not me:
        return redirect("/")
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["id", "логин", "имя", "email", "регистрация", "последний вход", "искры", "Nuvora+", "заблокирован"])
    from services import extras
    for u in db.query(models.User).order_by(models.User.id).yield_per(500):
        w.writerow([u.id, u.username, s(u.name), u.email, u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "",
                    u.last_seen.strftime("%Y-%m-%d %H:%M") if u.last_seen else "", extras.balance(u), "да" if u.is_plus else "", "да" if u.is_blocked else ""])
    log_mod(db, me, "export_users", "", "csv")
    db.commit()
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="nuvora-users-{datetime.utcnow():%Y-%m-%d}.csv"'})
