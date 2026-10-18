"""Люди 3.0: «Мои ссылки», ежедневный сундук, «Похожие на вас»."""
from datetime import datetime, timedelta
from urllib.parse import urlparse

from fastapi import Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from database import SessionLocal, get_db
from deps import current_user, json_error, login_redirect, render
from routers.posts import read_payload
from services import extras, gamification, prefs, social
from services.text import censor

from . import models as m
from .common import router, s, today


# ---------------------------------------------------------------- «Мои ссылки»
def _clean_url(u):
    u = s(u).strip()[:300]
    if u and "://" not in u:
        u = "https://" + u
    p = urlparse(u)
    return u if p.scheme in ("http", "https") and p.netloc and "." in p.netloc else ""


@router.get("/links")
def links_manage(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    rows = db.query(m.ProfileLink).filter_by(user_id=user.id).order_by(m.ProfileLink.pos, m.ProfileLink.id).all()
    return render(request, db, "packs/v3/links_manage.html", links=rows)


@router.post("/links")
async def links_save(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    data = await read_payload(request)
    title = censor(s(data.get("title")).strip()[:40], social.stop_words(db))
    url = _clean_url(data.get("url"))
    if not title or not url:
        return json_error("Нужны название и правильная ссылка (https://…)")
    if db.query(m.ProfileLink).filter_by(user_id=user.id).count() >= 20:
        return json_error("Можно добавить до 20 ссылок")
    pos = (db.query(func.max(m.ProfileLink.pos)).filter_by(user_id=user.id).scalar() or 0) + 1
    db.add(m.ProfileLink(user_id=user.id, title=title, url=url, pos=pos))
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/links/{link_id}/{action}")
def links_action(link_id: int, action: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    row = db.query(m.ProfileLink).filter_by(id=link_id, user_id=user.id if user else -1).first()
    if not row:
        return json_error("Ссылка не найдена", 404)
    if action == "delete":
        db.delete(row)
    elif action in ("up", "down"):
        rows = db.query(m.ProfileLink).filter_by(user_id=user.id).order_by(m.ProfileLink.pos, m.ProfileLink.id).all()
        i = rows.index(row)
        j = i - 1 if action == "up" else i + 1
        if 0 <= j < len(rows):
            rows[i], rows[j] = rows[j], rows[i]
            for k, r in enumerate(rows):
                r.pos = k
    else:
        return json_error("Неизвестное действие")
    db.commit()
    return JSONResponse({"ok": True})


@router.get("/l/{username}")
def links_public(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    owner = db.query(models.User).filter(func.lower(models.User.username) == username.lower()).first()
    if not owner or owner.is_blocked or not social.can_see_content(db, user, owner):
        return render(request, db, "error.html", status_code=404, code=404, title="Страница не найдена", text="Ссылки недоступны.")
    rows = db.query(m.ProfileLink).filter_by(user_id=owner.id).order_by(m.ProfileLink.pos, m.ProfileLink.id).all()
    return render(request, db, "packs/v3/links_public.html", owner=owner, links=rows, sidebar=False)


@router.get("/l/go/{link_id}")
def links_go(link_id: int, db: Session = Depends(get_db)):
    """Переход по ссылке со счётчиком (адрес проверен при сохранении: только http/https)."""
    row = db.get(m.ProfileLink, link_id)
    if not row or not _clean_url(row.url):
        return RedirectResponse("/", status_code=303)
    row.clicks = (row.clicks or 0) + 1
    db.commit()
    return RedirectResponse(row.url, status_code=303)


def links_count(user):
    if not user:
        return 0
    db = SessionLocal()
    try:
        return db.query(m.ProfileLink).filter_by(user_id=user.id).count()
    finally:
        db.close()


# ---------------------------------------------------------------- ежедневный сундук
REWARDS = [5, 10, 15, 20, 25, 30, 50]  # 7-й день подряд — большой приз, дальше цикл


def chest_state(user):
    """Можно ли сегодня открыть сундук, и какая награда ждёт."""
    if not user:
        return None
    db = SessionLocal()
    try:
        row = db.get(m.DailyChest, user.id)
        t = today(user)
        yest = (datetime.strptime(t, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        streak = (row.streak if row and row.last_day == yest else 0) if not (row and row.last_day == t) else row.streak
        return {"open": bool(row and row.last_day == t), "streak": streak, "reward": REWARDS[streak % len(REWARDS)],
                "day": streak % len(REWARDS) + 1}
    finally:
        db.close()


@router.post("/v3/chest")
def chest_open(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    t = today(user)
    yest = (datetime.strptime(t, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    row = db.get(m.DailyChest, user.id)
    if row and row.last_day == t:
        return json_error("Сундук уже открыт — приходите завтра")
    if not row:
        row = m.DailyChest(user_id=user.id, streak=0, total=0)
        db.add(row)
    streak = row.streak if row.last_day == yest else 0
    reward = REWARDS[streak % len(REWARDS)]
    row.streak, row.last_day, row.total = streak + 1, t, (row.total or 0) + reward
    gamification.add_points(user, db, reward)
    db.commit()
    return JSONResponse({"ok": True, "reward": reward, "streak": row.streak})


# ---------------------------------------------------------------- похожие на вас
def similar_people(user, limit=6):
    """Люди с общими интересами, на которых вы ещё не подписаны."""
    if not user:
        return []
    mine = set(extras.interests(user))
    if not mine:
        return []
    db = SessionLocal()
    try:
        skip = social.following_ids(db, user) | social.blocked_ids(db, user) | {user.id}
        cands = (db.query(models.User).filter(models.User.interests != "", models.User.interests != None, ~models.User.id.in_(skip),
                                              models.User.is_blocked != True,
                                              prefs.sql_flag_off(models.User.prefs, "hide_from_search"))
                 .order_by(models.User.last_seen.desc()).limit(300).all())
        scored = []
        for u in cands:
            common = mine & set(extras.interests(u))
            if common:
                scored.append((len(common), u, sorted(common)[:3]))
        scored.sort(key=lambda x: -x[0])
        out = [{"user": u, "common": c} for _, u, c in scored[:limit]]
        for o in out:  # отвязываем от сессии, чтобы шаблон мог читать поля
            db.expunge(o["user"])
        return out
    finally:
        db.close()
