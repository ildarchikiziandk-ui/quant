"""Расширенная админ-панель владельца: карточка пользователя со всеми действиями, настройки сайта, группы,
рассылка уведомлений. Переписку читать нельзя — ни личные сообщения, ни группы, ни секретные чаты:
в карточке видно только количество сообщений."""
import ipaddress
import re
from datetime import datetime
from urllib.parse import quote

from fastapi import Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

import config
import models
from database import get_db
from deps import current_user, log_mod, redirect, render
from routers.posts import purge_post
from services import extras, handles, social

from . import models as m
from . import site, stickers
from .common import router, s


def _owner(request, db):
    u = current_user(request, db)
    return u if u and u.is_owner else None


def _staff(request, db):
    u = current_user(request, db)
    return u if u and (u.is_owner or social.can_mod(u)) else None


def _target(db, username):
    return handles.owner_of(db, username)


def _back(username, msg="", err=False):
    q = f"?{'err' if err else 'ok'}={quote(msg)}" if msg else ""
    return redirect(f"/admin/u/{username}{q}")


# ---------------------------------------------------------------- карточка пользователя
@router.get("/admin/u/{username}")
def user_card(username: str, request: Request, ok: str = "", err: str = "", db: Session = Depends(get_db)):
    me = _staff(request, db)
    if not me:
        return redirect("/")
    t = _target(db, username)
    if not t:
        return render(request, db, "error.html", status_code=404, code=404, title="Нет такого пользователя", text=f"@{username} не найден.")
    if t.username.lower() != username.lower():
        return redirect(f"/admin/u/{t.username}")
    uid = t.id
    counts = {
        "posts": db.query(models.Post).filter_by(user_id=uid).count(),
        "comments": db.query(models.Comment).filter_by(user_id=uid).count(),
        "stories": db.query(models.Story).filter_by(user_id=uid).count(),
        "followers": db.query(models.Follow).filter_by(following_id=uid).count(),
        "following": db.query(models.Follow).filter_by(follower_id=uid).count(),
        "messages": db.query(models.Message).filter_by(sender_id=uid).count(),  # только число — переписку не читаем
        "groups": db.query(models.GroupMember).filter_by(user_id=uid).count(),
        "reports": db.query(models.Report).filter_by(target_id=uid).count(),
    }
    ctx = dict(t=t, counts=counts, ok=ok, err=err, is_owner=me.is_owner, balance=extras.balance(t),
               aliases=[a.handle for a in db.query(m.UserAlias).filter_by(user_id=uid).order_by(m.UserAlias.id)],
               posts=db.query(models.Post).filter_by(user_id=uid).order_by(models.Post.created_at.desc()).limit(10).all(),
               comments=db.query(models.Comment).filter_by(user_id=uid).order_by(models.Comment.created_at.desc()).limit(10).all(),
               logs=db.query(models.ModLog).filter(func.lower(models.ModLog.target) == t.username.lower())
               .order_by(models.ModLog.created_at.desc()).limit(20).all(),
               purchases=db.query(m.HandlePurchase).filter_by(user_id=uid).order_by(m.HandlePurchase.id.desc()).all())
    if me.is_owner:  # личные данные — только владельцу
        ctx["sessions"] = db.query(models.UserSession).filter_by(user_id=uid).order_by(models.UserSession.last_active.desc()).limit(20).all()
    return render(request, db, "packs/v3/admin_user.html", sidebar=False, **ctx)


ACTIONS = {}


def action(name):
    def deco(fn):
        ACTIONS[name] = fn
        return fn
    return deco


@router.post("/admin/u/{username}/{name}")
async def user_action(username: str, name: str, request: Request, db: Session = Depends(get_db)):
    me = _owner(request, db)
    t = _target(db, username)
    if not me or not t or name not in ACTIONS:
        return redirect("/")
    if t.is_owner and t.id != me.id and name not in ("notify", "coowner"):
        return _back(t.username, "С другим владельцем так нельзя", True)
    form = await request.form()
    msg, is_err = ACTIONS[name](db, me, t, form)
    if not is_err:
        log_mod(db, me, f"admin_{name}", t.username, msg[:200])
    db.commit()
    return _back(t.username, msg, is_err)


@action("coowner")
def _coowner(db, me, t, f):
    if me.co_owner or t.id == me.id:
        return "Назначать совладельцев может только основатель", True
    on = not t.co_owner
    t.is_owner = t.co_owner = on
    t.is_moderator = t.is_moderator or on
    return ("@%s теперь совладелец — полный доступ, как у вас" if on else "@%s больше не совладелец") % t.username, False


@action("save")
def _save(db, me, t, f):
    name, uname, email = s(f.get("name")).strip()[:60], s(f.get("username")).strip().lstrip("@"), s(f.get("email")).strip().lower()
    if not re.fullmatch(r"[A-Za-z0-9_]{3,30}", uname):
        return "Логин: 3–30 символов, латиница, цифры и _", True
    other = handles.owner_of(db, uname)
    if other and other.id != t.id:
        return f"@{uname} уже занят", True
    if uname.lower() in {a.handle for a in db.query(m.UserAlias).filter_by(user_id=t.id)}:
        db.query(m.UserAlias).filter_by(user_id=t.id, handle=uname.lower()).delete()
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return "Неверный email", True
    if email and db.query(models.User).filter(func.lower(models.User.email) == email, models.User.id != t.id).first():
        return "Этот email уже у другого аккаунта", True
    t.name, t.username = name or t.name, uname
    if email:
        t.email = email
    t.bio, t.city = s(f.get("bio"))[:600], s(f.get("city")).strip()[:60]
    return "Профиль сохранён", False


@action("alias-add")
def _alias_add(db, me, t, f):
    h = s(f.get("handle")).strip().lstrip("@").lower()
    if not re.fullmatch(r"[a-z0-9_]{3,30}", h):
        return "Логин: 3–30 символов, латиница, цифры и _", True
    if handles.owner_of(db, h):
        return f"@{h} уже занят", True
    if db.query(m.UserAlias).filter_by(user_id=t.id).count() >= handles.MAX_ALIASES:
        return "У пользователя уже 2 дополнительных логина", True
    db.add(m.UserAlias(user_id=t.id, handle=h))
    return f"Добавлен логин @{h}", False


@action("alias-del")
def _alias_del(db, me, t, f):
    h = s(f.get("handle")).lower()
    db.query(m.UserAlias).filter_by(user_id=t.id, handle=h).delete()
    return f"Логин @{h} освобождён", False


@action("balance")
def _balance(db, me, t, f):
    try:
        want = max(0, min(int(s(f.get("balance"))), 10_000_000))
    except ValueError:
        return "Введите число", True
    total, spent = t.total_points or 0, t.spent_points or 0
    if want > total - spent:
        t.total_points = spent + want
    else:
        t.spent_points = total - want
    return f"Баланс: {want} искр", False


@action("plus-off")
def _plus_off(db, me, t, f):
    t.is_plus, t.plus_until = False, None
    return "Nuvora+ снят", False


@action("logout-all")
def _logout_all(db, me, t, f):
    n = db.query(models.UserSession).filter_by(user_id=t.id, is_active=True).update({"is_active": False})
    return f"Завершено сеансов: {n}", False


@action("session-end")
def _session_end(db, me, t, f):
    sid = s(f.get("sid"))
    if sid.isdigit():
        db.query(models.UserSession).filter_by(user_id=t.id, id=int(sid)).update({"is_active": False})
    return "Сеанс завершён", False


@action("disable-2fa")
def _no2fa(db, me, t, f):
    t.two_factor_enabled, t.two_factor_secret = False, None
    db.query(m.BackupCode).filter_by(user_id=t.id).delete()
    db.add(models.Notification(user_id=t.id, type="security", text="Администратор отключил двухфакторную защиту в вашем аккаунте"))
    return "Двухфакторная защита отключена", False


@action("verify-email")
def _verify_email(db, me, t, f):
    t.email_verified = True
    return "Email отмечен подтверждённым", False


@action("posts-lock")
def _posts_lock(db, me, t, f):
    from .accounts import posts_locked, set_locked
    on = not posts_locked(t)
    set_locked(db, t, on)
    site.put(db, "locks_applied", sorted(set(site.get("locks_applied") or ()) | {t.id}))  # дальше — только отсюда
    return ("Включён режим «только чаты и профиль»: посты не публикует и чужие не видит" if on else "Режим «только чаты» выключен"), False


@action("private")
def _private(db, me, t, f):
    t.is_private = not t.is_private
    return "Профиль закрыт" if t.is_private else "Профиль открыт", False


@action("notify")
def _notify(db, me, t, f):
    text = s(f.get("text")).strip()[:500]
    if not text:
        return "Напишите текст", True
    db.add(models.Notification(user_id=t.id, type="system", text=text))
    return "Уведомление отправлено", False


@action("delete-posts")
def _del_posts(db, me, t, f):
    posts = db.query(models.Post).filter_by(user_id=t.id).all()
    for p in posts:
        purge_post(db, p)
    return f"Удалено постов: {len(posts)}", False


@action("delete-comments")
def _del_comments(db, me, t, f):
    ids = [c.id for c in db.query(models.Comment.id).filter_by(user_id=t.id)]
    if ids:
        db.query(models.CommentLike).filter(models.CommentLike.comment_id.in_(ids)).delete(synchronize_session=False)
        db.query(models.Comment).filter(models.Comment.parent_id.in_(ids)).update({"parent_id": None}, synchronize_session=False)
        db.query(models.Comment).filter(models.Comment.id.in_(ids)).delete(synchronize_session=False)
    return f"Удалено комментариев: {len(ids)}", False


@action("delete-stories")
def _del_stories(db, me, t, f):
    n = 0
    for st in db.query(models.Story).filter_by(user_id=t.id).all():
        db.query(models.StoryView).filter_by(story_id=st.id).delete()
        db.query(models.StoryReaction).filter_by(story_id=st.id).delete()
        db.query(models.StoryHighlightItem).filter_by(story_id=st.id).delete()
        db.delete(st)
        n += 1
    return f"Удалено историй: {n}", False


@action("block")
def _block(db, me, t, f):
    from datetime import timedelta
    try:
        days = max(1, min(int(s(f.get("days")) or 7), 3650))
    except ValueError:
        days = 7
    t.is_blocked, t.blocked_until = True, datetime.utcnow() + timedelta(days=days)
    db.query(models.UserSession).filter_by(user_id=t.id).update({"is_active": False})
    reason = s(f.get("reason")).strip()[:200] or "нарушение правил"
    db.add(models.Notification(user_id=t.id, type="moderation", text=f"Аккаунт заблокирован на {days} дн. Причина: {reason}"))
    return f"Заблокирован на {days} дн.: {reason}", False


@action("unblock")
def _unblock(db, me, t, f):
    t.is_blocked, t.blocked_until = False, None
    return "Разблокирован", False


# ---------------------------------------------------------------- настройки сайта
@router.get("/admin/site")
def site_page(request: Request, ok: str = "", db: Session = Depends(get_db)):
    me = _owner(request, db)
    if not me:
        return redirect("/")
    groups = (db.query(models.GroupChat, func.count(models.GroupMember.id)).outerjoin(models.GroupMember, models.GroupMember.group_id == models.GroupChat.id)
              .group_by(models.GroupChat.id).order_by(models.GroupChat.created_at.desc()).limit(100).all())
    owners = {u.id: u for u in db.query(models.User).filter(models.User.id.in_([g.owner_id for g, _ in groups] or [0]))}
    return render(request, db, "packs/v3/admin_site.html", sidebar=False, ok=ok, sections=site.SECTIONS, disabled=set(site.disabled()),
                  registration=site.get("registration"), maintenance=site.get("maintenance"), maintenance_text=site.get("maintenance_text"),
                  calls=site.get("calls"), packs=stickers.PACKS, packs_off=set(site.get("sticker_packs_off") or []),
                  banned_ips="\n".join(site.get("banned_ips") or []), reserved="\n".join(site.get("reserved_handles") or []),
                  my_ip=request.client.host if request.client else "",
                  groups=groups, owners=owners, users_n=db.query(models.User).filter(models.User.is_blocked != True).count())


@router.post("/admin/site/save")
async def site_save(request: Request, db: Session = Depends(get_db)):
    me = _owner(request, db)
    if not me:
        return redirect("/")
    f = await request.form()
    enabled = set(f.getlist("on"))
    site.put(db, "disabled", [p for p, _ in site.SECTIONS if p not in enabled])
    site.put(db, "registration", bool(f.get("registration")))
    site.put(db, "maintenance", bool(f.get("maintenance")))
    site.put(db, "maintenance_text", s(f.get("maintenance_text")).strip()[:300] or site.DEFAULTS["maintenance_text"])
    site.put(db, "calls", bool(f.get("calls")))
    site.put(db, "read_only", bool(f.get("read_only")))
    site.put(db, "payments_on", bool(f.get("payments_on")))
    site.put(db, "read_only_text", s(f.get("read_only_text")).strip()[:300])
    on_packs = set(f.getlist("pack"))
    site.put(db, "sticker_packs_off", [pid for pid, _, _ in stickers.PACKS if pid not in on_packs])
    # блокировка по IP: адреса и подсети (1.2.3.4, 10.0.0.0/8); свой текущий адрес заблокировать нельзя
    mine = request.client.host if request.client else ""
    ips, bad = [], []
    for line in re.split(r"[\s,;]+", s(f.get("banned_ips"))):
        if not line:
            continue
        try:
            net = ipaddress.ip_network(line, strict=False)
        except ValueError:
            bad.append(line)
            continue
        if mine and _ip_in(mine, [str(net)]):
            bad.append(line + " (это ваш адрес)")
            continue
        ips.append(str(net) if net.num_addresses > 1 else line)
    site.put(db, "banned_ips", ips[:500])
    reserved = sorted({w.lower().lstrip("@") for w in re.split(r"[\s,;]+", s(f.get("reserved"))) if re.fullmatch(r"@?[a-zA-Z0-9_.]{2,30}", w)})
    site.put(db, "reserved_handles", reserved[:2000])
    log_mod(db, me, "site_settings", "", f"off={len(site.SECTIONS) - len(enabled)}; reg={bool(f.get('registration'))}; maint={bool(f.get('maintenance'))}")
    db.commit()
    note = "Настройки сайта сохранены" + (". Не приняты: " + ", ".join(bad[:5]) if bad else "")
    return redirect("/admin/site?ok=" + quote(note))


def _ip_in(ip, nets):
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for n in nets:
        try:
            if a in ipaddress.ip_network(n, strict=False):
                return True
        except ValueError:
            continue
    return False


_nets = {"key": None, "nets": []}


def ip_banned(ip):
    """Заблокирован ли адрес. Проверяется на каждом запросе: список из настроек разбирается один раз."""
    key = tuple(site.get("banned_ips") or ())
    if not key:
        return False
    if _nets["key"] != key:
        _nets.update(key=key, nets=[ipaddress.ip_network(n, strict=False) for n in key])
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(a in n for n in _nets["nets"])


@router.post("/admin/site/notify-all")
async def notify_all(request: Request, db: Session = Depends(get_db)):
    me = _owner(request, db)
    if not me:
        return redirect("/")
    f = await request.form()
    text = s(f.get("text")).strip()[:500]
    if not text:
        return redirect("/admin/site?ok=" + quote("Напишите текст уведомления"))
    ids = [u.id for u in db.query(models.User.id).filter(models.User.is_blocked != True)]
    db.bulk_save_objects([models.Notification(user_id=i, type="system", text=text) for i in ids])
    log_mod(db, me, "notify_all", "", f"{len(ids)}: {text[:150]}")
    db.commit()
    return redirect("/admin/site?ok=" + quote(f"Уведомление отправлено: {len(ids)}"))


@router.post("/admin/groups/{gid}/delete")
def group_delete(gid: int, request: Request, db: Session = Depends(get_db)):
    """Удалить группу целиком (сообщения удаляются, не читаясь)."""
    me = _owner(request, db)
    g = db.get(models.GroupChat, gid)
    if not me or not g:
        return redirect("/admin/site")
    db.query(models.GroupMessage).filter_by(group_id=g.id).delete()
    db.query(models.GroupMember).filter_by(group_id=g.id).delete()
    db.query(models.PinnedChat).filter_by(pinned_group_id=g.id).delete()
    db.query(models.MutedChat).filter_by(muted_group_id=g.id).delete()
    db.query(models.TypingStatus).filter_by(group_id=g.id).delete()
    log_mod(db, me, "delete_group", g.name)
    db.delete(g)
    db.commit()
    return redirect("/admin/site?ok=" + quote("Группа удалена") + "#groups")

