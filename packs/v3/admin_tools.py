"""Ещё инструменты админ-панели: журнал действий, комментарии, входы и мультиаккаунты,
предупреждения, запрет публикаций на срок, режим «только чтение» для всего сайта.
Переписку не читаем и здесь — по сообщениям видны только количества."""
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import Depends, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import log_mod, redirect, render

from . import site
from .admin_plus import _owner, _staff, action
from .common import router, s


# ---------------------------------------------------------------- запрет публикаций и «только чтение»
def mute_until(user):
    """До какого времени человеку нельзя публиковать посты и комментарии (или None)."""
    if not user:
        return None
    raw = (site.get("muted") or {}).get(str(user.id))
    if not raw:
        return None
    try:
        until = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return until if until > datetime.utcnow() else None


def publish_blocked(user):
    """Причина, по которой нельзя публиковать (посты, комментарии), или пустая строка."""
    if user and user.is_owner:
        return ""
    if site.get("read_only"):
        return site.get("read_only_text") or "Публикации временно отключены. Чаты работают как обычно."
    until = mute_until(user)
    if until:
        return f"Вам временно запрещено публиковать посты и комментарии — до {until.strftime('%d.%m %H:%M')} UTC"
    return ""


def warnings_of(user):
    return int((site.get("warnings") or {}).get(str(user.id), 0)) if user else 0


@action("warn")
def _warn(db, me, t, f):
    reason = s(f.get("reason")).strip()[:200] or "нарушение правил"
    w = dict(site.get("warnings") or {})
    n = int(w.get(str(t.id), 0)) + 1
    w[str(t.id)] = n
    site.put(db, "warnings", w)
    db.add(models.Notification(user_id=t.id, type="moderation",
                               text=f"Предупреждение от администрации ({n}-е): {reason}. Повторные нарушения приведут к блокировке."))
    return f"Предупреждение №{n}: {reason}", False


@action("warn-reset")
def _warn_reset(db, me, t, f):
    w = dict(site.get("warnings") or {})
    w.pop(str(t.id), None)
    site.put(db, "warnings", w)
    return "Предупреждения сняты", False


@action("mute")
def _mute(db, me, t, f):
    try:
        hours = max(1, min(int(s(f.get("hours")) or 24), 24 * 365))
    except ValueError:
        hours = 24
    until = datetime.utcnow() + timedelta(hours=hours)
    muted = dict(site.get("muted") or {})
    muted[str(t.id)] = until.isoformat(timespec="seconds")
    site.put(db, "muted", muted)
    reason = s(f.get("reason")).strip()[:200] or "нарушение правил"
    db.add(models.Notification(user_id=t.id, type="moderation",
                               text=f"Вам запрещено публиковать посты и комментарии до {until.strftime('%d.%m %H:%M')} UTC. Причина: {reason}. Чаты работают."))
    return f"Публикации запрещены на {hours} ч.: {reason}", False


@action("unmute")
def _unmute(db, me, t, f):
    muted = dict(site.get("muted") or {})
    muted.pop(str(t.id), None)
    site.put(db, "muted", muted)
    return "Запрет публикаций снят", False


@action("login-approve")
def _login_approve(db, me, t, f):
    from . import login_approve
    on = s(f.get("on")) == "1"
    login_approve.set_enabled(db, t, on)
    return ("Подтверждение входа на телефоне включено" if on else "Подтверждение входа выключено"), False


# ---------------------------------------------------------------- журнал действий
@router.get("/admin/log")
def log_page(request: Request, q: str = "", db: Session = Depends(get_db)):
    me = _staff(request, db)
    if not me:
        return redirect("/")
    query = db.query(models.ModLog)
    q = q.strip().lstrip("@")
    if q:
        actor_ids = [u for (u,) in db.query(models.User.id).filter(func.lower(models.User.username) == q.lower())]
        query = query.filter(or_(func.lower(models.ModLog.target) == q.lower(), models.ModLog.actor_id.in_(actor_ids or [0]),
                                 models.ModLog.action.ilike(f"%{q}%")))
    rows = query.order_by(models.ModLog.created_at.desc()).limit(200).all()
    return render(request, db, "packs/v3/admin_log.html", sidebar=False, rows=rows, q=q)


# ---------------------------------------------------------------- комментарии
@router.get("/admin/comments")
def comments_page(request: Request, q: str = "", ok: str = "", db: Session = Depends(get_db)):
    me = _staff(request, db)
    if not me:
        return redirect("/")
    query = db.query(models.Comment)
    q = q.strip()
    if q.startswith("@"):
        u = db.query(models.User).filter(func.lower(models.User.username) == q[1:].lower()).first()
        query = query.filter(models.Comment.user_id == (u.id if u else 0))
    elif q:
        query = query.filter(models.Comment.content.ilike(f"%{q}%"))
    rows = query.order_by(models.Comment.created_at.desc()).limit(80).all()
    return render(request, db, "packs/v3/admin_comments.html", sidebar=False, rows=rows, q=q, ok=ok)


@router.post("/admin/comments/{cid}/{act}")
def comment_action(cid: int, act: str, request: Request, db: Session = Depends(get_db)):
    me = _staff(request, db)
    c = db.get(models.Comment, cid)
    back = request.headers.get("referer") or "/admin/comments"
    if not me or not c or act not in ("delete", "hide", "show"):
        return redirect("/admin/comments")
    if act == "delete":
        ids, frontier = [c.id], [c.id]
        while frontier:
            frontier = [k for (k,) in db.query(models.Comment.id).filter(models.Comment.parent_id.in_(frontier))]
            ids += frontier
        post = db.get(models.Post, c.post_id)
        if post and post.pinned_comment_id in ids:
            post.pinned_comment_id = None
        db.query(models.CommentLike).filter(models.CommentLike.comment_id.in_(ids)).delete(synchronize_session=False)
        db.query(models.Comment).filter(models.Comment.id.in_(ids)).update({"parent_id": None}, synchronize_session=False)
        db.query(models.Comment).filter(models.Comment.id.in_(ids)).delete(synchronize_session=False)
    else:
        c.is_hidden = act == "hide"
    log_mod(db, me, f"comment_{act}", c.author.username if c.author else "", (c.content or "")[:120])
    db.commit()
    return redirect(back.split("#")[0])


# ---------------------------------------------------------------- входы и мультиаккаунты
@router.get("/admin/logins")
def logins_page(request: Request, days: int = 7, db: Session = Depends(get_db)):
    me = _owner(request, db)
    if not me:
        return redirect("/")
    days = max(1, min(days, 90))
    since = datetime.utcnow() - timedelta(days=days)
    recent = (db.query(models.UserSession).filter(models.UserSession.created_at >= since)
              .order_by(models.UserSession.created_at.desc()).limit(150).all())
    # один адрес — несколько аккаунтов (за 30 дней): часто это мультиаккаунты или накрутка
    by_ip = defaultdict(set)
    for ip, uid in (db.query(models.UserSession.ip, models.UserSession.user_id)
                    .filter(models.UserSession.created_at >= datetime.utcnow() - timedelta(days=30), models.UserSession.ip != "")):
        by_ip[ip].add(uid)
    shared = sorted(((ip, uids) for ip, uids in by_ip.items() if len(uids) >= 2), key=lambda x: -len(x[1]))[:40]
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_({i for _, us in shared for i in us} | {r.user_id for r in recent} or {0}))}
    banned = set(site.get("banned_ips") or ())
    fresh = db.query(models.User).filter(models.User.created_at >= since).count() if hasattr(models.User, "created_at") else 0
    return render(request, db, "packs/v3/admin_logins.html", sidebar=False, recent=recent, shared=shared, users=users,
                  banned=banned, days=days, fresh=fresh)


@router.post("/admin/logins/ban-ip")
async def ban_ip(request: Request, db: Session = Depends(get_db)):
    me = _owner(request, db)
    if not me:
        return redirect("/")
    ip = s((await request.form()).get("ip")).strip()[:64]
    mine = request.client.host if request.client else ""
    if ip and ip not in ("127.0.0.1", "::1", mine):  # свой адрес не баним — иначе админка закроется
        ips = list(site.get("banned_ips") or [])
        if ip not in ips:
            ips.append(ip)
            site.put(db, "banned_ips", ips)
            log_mod(db, me, "ban_ip", ip)
            db.commit()
    return redirect("/admin/logins")
