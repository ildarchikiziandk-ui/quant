"""Каналы и сообщества (Nuvora 3.2).

- Канал: публикуют только владелец и админы, остальные подписаны и читают.
- Сообщество: участники тоже публикуют (если владелец не закрыл стену).
- Официальное сообщество «Nuvora» (/c/nuvora): публикует только владелец сайта, на него подписаны все
  (новые — при регистрации, старые — один раз фоновой задачей); значок «официально», его нельзя удалить
  или передать, посты чаще попадают в рекомендации.
Посты сообществ — обычные посты с community_id: лайки, комментарии, репосты работают как всегда.
"""
import re
import time

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from database import SessionLocal, get_db
from deps import current_user, json_error, login_redirect, redirect, render
from services import feed as feed_svc
from services import social
from services.uploads import is_upload, save_file

from . import models as m
from . import site
from .common import router, s

OFFICIAL_SLUG = "nuvora"
SLUG_RE = re.compile(r"^[a-z0-9_]{3,32}$")
RESERVED = {"nuvora", "admin", "new", "edit", "official", "support", "help", "api", "static", "nvra", "moderator"}
KINDS = {"channel": "Канал", "community": "Сообщество"}
_info = {"t": 0.0, "v": {}}


# ---------------------------------------------------------------- данные для шаблонов (с кэшем на минуту)
def info(cid):
    """{id, slug, name, kind, avatar, official} сообщества по id — для карточек постов."""
    if not cid:
        return None
    if time.time() - _info["t"] > 60 or cid not in _info["v"]:
        db = SessionLocal()
        try:
            _info["v"] = {c.id: {"id": c.id, "slug": c.slug, "name": c.name, "kind": c.kind, "avatar": c.avatar,
                                 "official": bool(c.is_official), "letter": (c.name or "?")[:1].upper()}
                          for c in db.query(m.Community).all()}
            _info["t"] = time.time()
        finally:
            db.close()
    return _info["v"].get(cid)


def _reset():
    _info["t"] = 0


def member_ids(db, user):
    """Сообщества, на которые человек подписан (для ленты «Подписки и подписчики»)."""
    if not user:
        return set()
    return {cid for (cid,) in db.query(m.CommunityMember.community_id).filter_by(user_id=user.id)}


def role_of(db, c, user):
    if not user or not c:
        return None
    if c.owner_id == user.id:
        return "owner"
    row = db.query(m.CommunityMember).filter_by(community_id=c.id, user_id=user.id).first()
    return row.role if row else None


def can_post(db, c, user):
    if not user or not c:
        return False
    if c.is_official:
        return bool(user.is_owner)
    r = role_of(db, c, user)
    if r in ("owner", "admin"):
        return True
    return c.kind == "community" and c.open_wall and r == "member"


def can_manage(db, c, user):
    if not user or not c:
        return False
    if c.is_official:
        return bool(user.is_owner)
    return role_of(db, c, user) in ("owner", "admin")


def by_ref(db, ref):
    ref = s(ref).strip().lower()
    if not ref:
        return None
    if ref.isdigit():
        return db.get(m.Community, int(ref))
    return db.query(m.Community).filter_by(slug=ref).first()


def _count(db, cid):
    return db.query(func.count(m.CommunityMember.id)).filter_by(community_id=cid).scalar() or 0


def _join(db, c, user, role="member"):
    if not db.query(m.CommunityMember.id).filter_by(community_id=c.id, user_id=user.id).first():
        db.add(m.CommunityMember(community_id=c.id, user_id=user.id, role=role))


# ---------------------------------------------------------------- официальное сообщество Nuvora
def ensure_official(db):
    owner = db.query(models.User).filter_by(is_owner=True).first()
    if not owner:
        return None
    c = db.query(m.Community).filter_by(slug=OFFICIAL_SLUG).first()
    if not c:
        c = m.Community(slug=OFFICIAL_SLUG, name="Nuvora", kind="channel", is_official=True, owner_id=owner.id, open_wall=False,
                        description="Официальное сообщество Nuvora: новости, обновления, конкурсы и всё самое важное.",
                        avatar="/static/brand/logo-180.png")
        db.add(c)
        db.flush()
        _join(db, c, owner, "owner")
        db.commit()
        _reset()
    elif c.owner_id != owner.id or not c.is_official:
        c.owner_id, c.is_official = owner.id, True
        db.commit()
    return c


def join_official(db, user):
    """При регистрации: подписка на официальное сообщество."""
    c = ensure_official(db)
    if c and user:
        _join(db, c, user)
        db.commit()


def seed_job(db):
    """Один раз подписать всех существующих людей на официальное сообщество."""
    c = ensure_official(db)
    if not c or site.get("official_seeded"):
        return
    have = {u for (u,) in db.query(m.CommunityMember.user_id).filter_by(community_id=c.id)}
    db.bulk_save_objects([m.CommunityMember(community_id=c.id, user_id=u, role="member")
                          for (u,) in db.query(models.User.id) if u not in have])
    site.put(db, "official_seeded", True)
    db.commit()


# ---------------------------------------------------------------- страницы
def _card(db, c, user, joined):
    return {"c": c, "n": _count(db, c.id), "joined": c.id in joined, "kind": KINDS.get(c.kind, "")}


@router.get("/c")
def catalog(request: Request, q: str = "", db: Session = Depends(get_db)):
    user = current_user(request, db)
    ensure_official(db)
    joined = member_ids(db, user)
    query = db.query(m.Community)
    q = q.strip()
    if q:
        query = query.filter(func.lower(m.Community.name).contains(q.lower()) | m.Community.slug.contains(q.lower()))
    # популярные — по числу участников; официальное всегда первым
    counts = dict(db.query(m.CommunityMember.community_id, func.count(m.CommunityMember.id)).group_by(m.CommunityMember.community_id))
    allc = sorted(query.limit(300).all(), key=lambda c: (not c.is_official, -counts.get(c.id, 0), c.id))
    mine = [c for c in allc if c.id in joined]
    other = [c for c in allc if c.id not in joined][:60]
    return render(request, db, "packs/v3/communities.html", q=q, counts=counts,
                  mine=mine, other=other, kinds=KINDS)


@router.post("/c/new")
async def create(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    if social.is_active_block(user) or social.needs_email(user):
        return json_error("Сейчас нельзя создавать сообщества", 403)
    f = await request.form()
    name, slug, kind = s(f.get("name")).strip()[:80], s(f.get("slug")).strip().lower().lstrip("@"), s(f.get("kind"))
    if len(name) < 2:
        return json_error("Название — хотя бы 2 символа")
    if kind not in KINDS:
        return json_error("Выберите: канал или сообщество")
    if not SLUG_RE.match(slug) or slug in RESERVED:
        return json_error("Адрес: 3–32 символа — латиница, цифры и _")
    if db.query(m.Community.id).filter_by(slug=slug).first():
        return json_error("Такой адрес уже занят")
    from services.text import banned, BANNED_MSG
    if banned(name + " " + s(f.get("description")), social.stop_words(db)):
        return json_error(BANNED_MSG)
    if db.query(m.Community).filter_by(owner_id=user.id).count() >= 10:
        return json_error("Можно создать до 10 каналов и сообществ")
    c = m.Community(slug=slug, name=name, kind=kind, owner_id=user.id, description=s(f.get("description")).strip()[:1000])
    db.add(c)
    db.flush()
    _join(db, c, user, "owner")
    db.commit()
    _reset()
    return JSONResponse({"ok": True, "url": f"/c/{c.slug}"})


@router.get("/c/{slug}")
def page(slug: str, request: Request, pg: int = 1, db: Session = Depends(get_db)):
    user = current_user(request, db)
    c = by_ref(db, slug)
    if not c:
        return render(request, db, "error.html", status_code=404, code=404, title="Сообщество не найдено", text="Возможно, его удалили или адрес неверный.")
    q = social.visible_posts(db, user).filter(models.Post.community_id == c.id).order_by(models.Post.created_at.desc())
    per = 15
    pg = max(1, min(pg, 200))
    posts = q.offset((pg - 1) * per).limit(per + 1).all()
    has_more = len(posts) > per
    posts = posts[:per]
    admins = (db.query(models.User).join(m.CommunityMember, m.CommunityMember.user_id == models.User.id)
              .filter(m.CommunityMember.community_id == c.id, m.CommunityMember.role.in_(("owner", "admin"))).all())
    return render(request, db, "packs/v3/community.html", c=c, n=_count(db, c.id), role=role_of(db, c, user),
                  joined=bool(user and db.query(m.CommunityMember.id).filter_by(community_id=c.id, user_id=user.id).first()),
                  can_post=can_post(db, c, user), can_manage=can_manage(db, c, user), admins=admins, kinds=KINDS,
                  has_more=has_more, pg=pg, **feed_svc.feed_context(db, user, posts, {}))


@router.post("/c/{slug}/{act}")
async def act(slug: str, act: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    c = by_ref(db, slug)
    if not user:
        return json_error("auth", 401)
    if not c:
        return json_error("Сообщество не найдено", 404)
    if act == "join":
        _join(db, c, user)
        db.commit()
        return JSONResponse({"ok": True, "joined": True, "n": _count(db, c.id)})
    if act == "leave":
        if c.owner_id == user.id:
            return json_error("Владелец не может отписаться — передайте сообщество или удалите его")
        db.query(m.CommunityMember).filter_by(community_id=c.id, user_id=user.id).delete()
        db.commit()
        return JSONResponse({"ok": True, "joined": False, "n": _count(db, c.id)})
    if not can_manage(db, c, user):
        return json_error("Только для админов сообщества", 403)
    f = await request.form()
    if act == "save":
        name = s(f.get("name")).strip()[:80]
        if len(name) >= 2 and not c.is_official:
            c.name = name
        c.description = s(f.get("description")).strip()[:1000]
        c.open_wall = bool(f.get("open_wall"))
        for field in ("avatar", "cover"):
            up = f.get(field)
            if is_upload(up):
                url, _mt = save_file(up, allowed=("image",))
                if url:
                    setattr(c, field, url)
        db.commit()
        _reset()
        return redirect(f"/c/{c.slug}?ok=1")
    if act in ("admin-add", "admin-remove"):
        if c.is_official or role_of(db, c, user) != "owner":
            return json_error("Назначать админов может только владелец", 403)
        from services import handles
        t = handles.owner_of(db, s(f.get("username")).strip().lstrip("@"))
        if not t or t.id == c.owner_id:
            return json_error("Пользователь не найден")
        row = db.query(m.CommunityMember).filter_by(community_id=c.id, user_id=t.id).first()
        if act == "admin-add":
            if not row:
                row = m.CommunityMember(community_id=c.id, user_id=t.id)
                db.add(row)
            row.role = "admin"
            social.notify(db, t.id, "group_invite", user, text=f"назначил(а) вас админом «{c.name}»", url=f"/c/{c.slug}")
        elif row:
            row.role = "member"
        db.commit()
        return JSONResponse({"ok": True})
    if act == "delete":
        if c.is_official or role_of(db, c, user) != "owner":
            return json_error("Удалить может только владелец", 403)
        db.query(models.Post).filter_by(community_id=c.id).update({"community_id": None, "is_archived": True})
        db.query(m.CommunityMember).filter_by(community_id=c.id).delete()
        db.delete(c)
        db.commit()
        _reset()
        return JSONResponse({"ok": True, "url": "/c"})
    return json_error("Неизвестное действие")


@router.get("/c/{slug}/members")
def members(slug: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    c = by_ref(db, slug)
    if not c:
        return redirect("/c")
    if not user:
        return login_redirect(request)
    rows = (db.query(models.User, m.CommunityMember.role).join(m.CommunityMember, m.CommunityMember.user_id == models.User.id)
            .filter(m.CommunityMember.community_id == c.id).order_by(m.CommunityMember.role.desc(), m.CommunityMember.id.desc()).limit(200).all())
    return render(request, db, "packs/v3/community_members.html", c=c, rows=rows, can_manage=can_manage(db, c, user),
                  is_owner=role_of(db, c, user) == "owner", n=_count(db, c.id))
