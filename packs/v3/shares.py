"""Ссылки с «следом» (Nuvora 3.2): когда человек делится постом, в ссылку добавляется ?from=его_логин.

- Открыл вошедший человек: «@логин поделился(ась) с вами этим постом — добавить в друзья?», а посты того,
  кто поделился, чаще попадают ему в рекомендации.
- Открыл тот, у кого ещё нет аккаунта: предложение присоединиться; после регистрации тот, кто поделился,
  считается пригласившим (награда как за приглашение), а новичку сразу предлагается его добавить.
"""
from datetime import datetime, timedelta

import config
import models
from services import handles, social

from . import models as m

COOKIE = "ref"  # та же cookie, что у ссылок-приглашений /invite/<логин>


def visit(db, request, response_cookies, post, viewer):
    """Разобрать ?from=… на странице поста. Возвращает того, кто поделился (или None)."""
    ref = (request.query_params.get("from") or "").strip().lstrip("@")[:40]
    if not ref:
        return None
    sharer = handles.owner_of(db, ref)
    if not sharer or (viewer and viewer.id == sharer.id) or sharer.is_blocked:
        return None
    if viewer:
        if social.is_blocked_between(db, viewer, sharer):
            return None
        if not db.query(m.ShareVisit.id).filter_by(sharer_id=sharer.id, viewer_id=viewer.id, post_id=post.id).first():
            db.add(m.ShareVisit(sharer_id=sharer.id, viewer_id=viewer.id, post_id=post.id))
            db.commit()
    elif not request.cookies.get(COOKIE):
        response_cookies.append((COOKIE, sharer.username))
    return sharer


def sharers_for(db, viewer, days=60):
    """{sharer_id: сколько раз делился с этим человеком} — для рекомендаций."""
    out = {}
    since = datetime.utcnow() - timedelta(days=days)
    for (sid,) in db.query(m.ShareVisit.sharer_id).filter(m.ShareVisit.viewer_id == viewer.id, m.ShareVisit.created_at >= since):
        out[sid] = out.get(sid, 0) + 1
    return out


def after_register(db, user, ref):
    """Новичок пришёл по ссылке: предложить добавить того, кто поделился."""
    from services import prefs as P
    inviter = handles.owner_of(db, ref) if ref else None
    if inviter and inviter.id != user.id:
        P_raw = P._raw(user)
        P_raw["suggest_follow"] = inviter.username
        import json
        user.prefs = json.dumps(P_raw, ensure_ascii=False)
        user._prefs_cache = P_raw


def cookie_kwargs():
    return {"max_age": 7 * 86400, "httponly": True, "samesite": "lax", "secure": config.COOKIE_SECURE}


def suggestion(user):
    """Для главной: кого предложить добавить после регистрации по ссылке (или None)."""
    from services import prefs as P
    name = P._raw(user).get("suggest_follow") if user else None
    if not name:
        return None
    from database import SessionLocal
    db = SessionLocal()
    try:
        u = handles.owner_of(db, name)
        if not u or u.id == user.id or social.is_following(db, user, u):
            return None
        return {"username": u.username, "name": u.name or u.username, "letter": (u.name or u.username)[:1].upper()}
    finally:
        db.close()


from fastapi import Depends, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from database import get_db  # noqa: E402
from deps import current_user, json_error  # noqa: E402

from .common import router  # noqa: E402


@router.post("/v3/suggest-follow/dismiss")
def dismiss(request: Request, db: Session = Depends(get_db)):
    import json
    from services import prefs as P
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    raw = dict(P._raw(user))
    raw.pop("suggest_follow", None)
    user.prefs = json.dumps(raw, ensure_ascii=False)
    db.commit()
    return JSONResponse({"ok": True})
