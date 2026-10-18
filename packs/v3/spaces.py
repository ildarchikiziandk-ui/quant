"""Новые разделы 3.0: барахолка, привычки, дневник настроения, капсула времени."""
import json
from datetime import datetime, timedelta

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

import models
from deps import current_user, json_error, login_redirect, redirect, render
from database import get_db
from routers.messages import _deliver, _precheck
from routers.posts import read_payload
from services import social, timezones
from services.text import censor
from services.uploads import is_upload, save_file

from . import models as m
from .common import router, s, today

# ======================================================================== барахолка
CATEGORIES = [("clothes", "Одежда и обувь", "bag"), ("tech", "Техника", "smartphone"), ("books", "Книги и учёба", "book"),
              ("hobby", "Хобби и спорт", "target"), ("home", "Для дома", "home"), ("beauty", "Красота", "sparkle"),
              ("kids", "Детское", "gift"), ("free", "Отдам даром", "handshake"), ("other", "Другое", "package")]
CAT = {k: (t, i) for k, t, i in CATEGORIES}
CONDITIONS = [("new", "Новое"), ("used", "Б/у, хорошее"), ("worn", "Б/у, заметны следы")]


def json_list(raw):
    try:
        v = json.loads(raw or "[]")
        return v if isinstance(v, list) else []
    except ValueError:
        return []


def _variants(text, n):
    """Шаблоны LIKE без учёта регистра: SQLite сам не приводит кириллицу к нижнему регистру."""
    t = text.strip()[:n].replace("%", "").replace("_", "")
    return [f"%{v}%" for v in dict.fromkeys([t, t.lower(), t.capitalize(), t.upper()])]


def _photos(item):
    try:
        return json.loads(item.photos or "[]")
    except ValueError:
        return []


def _visible_item(db, user, item):
    if not item:
        return False
    owner = db.get(models.User, item.user_id)
    return bool(owner and not owner.is_blocked and not social.is_blocked_between(db, user, owner))


@router.get("/market")
def market(request: Request, q: str = "", cat: str = "", city: str = "", max_price: str = "", sort: str = "new",
           photo: str = "", mine: str = "", fav: str = "", db: Session = Depends(get_db)):
    user = current_user(request, db)
    qs = db.query(m.MarketItem)
    if mine and user:
        qs = qs.filter(m.MarketItem.user_id == user.id)
    else:
        qs = qs.filter(m.MarketItem.sold == False)
        hidden = social.blocked_ids(db, user)
        if hidden:
            qs = qs.filter(~m.MarketItem.user_id.in_(hidden))
    if fav and user:
        qs = qs.filter(m.MarketItem.id.in_(db.query(m.MarketFav.item_id).filter_by(user_id=user.id)))
    if cat in CAT:
        qs = qs.filter(m.MarketItem.category == cat)
    if city.strip():
        qs = qs.filter(or_(*[m.MarketItem.city.like(v) for v in _variants(city, 40)]))
    if q.strip():
        qs = qs.filter(or_(*[col.like(v) for v in _variants(q, 60) for col in (m.MarketItem.title, m.MarketItem.description)]))
    if max_price.isdigit() and len(max_price) < 10:
        qs = qs.filter(m.MarketItem.price <= int(max_price))
    if photo:
        qs = qs.filter(m.MarketItem.photos != "[]")
    order = {"cheap": m.MarketItem.price.asc(), "dear": m.MarketItem.price.desc()}.get(sort, m.MarketItem.created_at.desc())
    items = qs.order_by(order).limit(60).all()
    favs = {f.item_id for f in db.query(m.MarketFav.item_id).filter_by(user_id=user.id)} if user else set()
    return render(request, db, "packs/v3/market.html", items=items, cats=CATEGORIES, cat_by=CAT, photos=_photos, favs=favs,
                  f={"q": q, "cat": cat, "city": city, "max_price": max_price, "sort": sort, "photo": photo, "mine": mine, "fav": fav})


@router.get("/market/new")
def market_new(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    return render(request, db, "packs/v3/market_form.html", item=None, cats=CATEGORIES, conditions=CONDITIONS)


@router.get("/market/{item_id}/edit")
def market_edit(item_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    item = db.get(m.MarketItem, item_id)
    if not user or not item or item.user_id != user.id:
        return redirect("/market")
    return render(request, db, "packs/v3/market_form.html", item=item, cats=CATEGORIES, conditions=CONDITIONS)


@router.post("/market/save")
async def market_save(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    if social.is_active_block(user):
        return json_error("Аккаунт заблокирован", 403)
    form = await request.form()
    stop = social.stop_words(db)
    iid = s(form.get("id"))
    item = db.query(m.MarketItem).filter_by(id=int(iid), user_id=user.id).first() if iid.isdigit() and len(iid) < 10 else None
    if iid and not item:
        return json_error("Объявление не найдено", 404)
    if not item:
        if db.query(m.MarketItem).filter(m.MarketItem.user_id == user.id, m.MarketItem.sold == False).count() >= 30:
            return json_error("Можно держать до 30 активных объявлений")
        item = m.MarketItem(user_id=user.id)
    title = censor(s(form.get("title")).strip()[:80], stop)
    if len(title) < 3:
        return json_error("Название — хотя бы 3 символа")
    price = s(form.get("price")).replace(" ", "")
    item.title = title
    item.description = censor(s(form.get("description")).strip()[:3000], stop)
    item.category = s(form.get("category")) if s(form.get("category")) in CAT else "other"
    item.price = 0 if item.category == "free" else (int(price) if price.isdigit() and len(price) < 9 else 0)
    item.city = s(form.get("city")).strip()[:60] or (user.city or "")
    item.condition = s(form.get("condition")) if s(form.get("condition")) in dict(CONDITIONS) else "used"
    photos = [p for p in _photos(item) if p not in form.getlist("remove_photo")]
    for f in form.getlist("photos"):
        if not is_upload(f) or len(photos) >= 6:
            continue
        url, err = save_file(f, allowed=("image",))
        if not url:
            return json_error(err)
        photos.append(url)
    item.photos = json.dumps(photos)
    if not item.id:
        db.add(item)
    db.commit()
    return JSONResponse({"ok": True, "id": item.id, "url": f"/market/{item.id}"})


@router.get("/market/{item_id}")
def market_item(item_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    item = db.get(m.MarketItem, item_id)
    if not _visible_item(db, user, item):
        return render(request, db, "error.html", status_code=404, code=404, title="Объявление не найдено", text="Возможно, его удалили.")
    if not user or user.id != item.user_id:
        item.views = (item.views or 0) + 1
        db.commit()
    seller = db.get(models.User, item.user_id)
    more = (db.query(m.MarketItem).filter(m.MarketItem.user_id == item.user_id, m.MarketItem.id != item.id, m.MarketItem.sold == False)
            .order_by(m.MarketItem.created_at.desc()).limit(4).all())
    fav = bool(user and db.query(m.MarketFav).filter_by(user_id=user.id, item_id=item.id).first())
    return render(request, db, "packs/v3/market_item.html", item=item, seller=seller, photos=_photos(item), cat_by=CAT,
                  conditions=dict(CONDITIONS), more=more, photos_of=_photos, fav=fav)


@router.post("/market/{item_id}/{action}")
def market_action(item_id: int, action: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    item = db.get(m.MarketItem, item_id)
    if not user or not _visible_item(db, user, item):
        return json_error("Объявление не найдено", 404)
    if action == "fav":
        row = db.query(m.MarketFav).filter_by(user_id=user.id, item_id=item.id).first()
        if row:
            db.delete(row)
        else:
            db.add(m.MarketFav(user_id=user.id, item_id=item.id))
        db.commit()
        return JSONResponse({"ok": True, "fav": not row})
    if action == "contact":
        seller = db.get(models.User, item.user_id)
        if seller.id == user.id:
            return json_error("Это ваше объявление")
        err = _precheck(db, user, seller)
        if err:
            return err
        msg = models.Message(sender_id=user.id, receiver_id=seller.id, is_delivered=social.is_online(seller),
                             content=f"Здравствуйте! Интересует ваше объявление «{item.title}» — /market/{item.id}")
        _deliver(db, user, seller, msg)
        return JSONResponse({"ok": True, "url": f"/messages/{seller.username}"})
    if item.user_id != user.id and not (action == "delete" and social.can_mod(user)):
        return json_error("Нет доступа", 403)
    if action == "sold":
        item.sold = not item.sold
    elif action == "up":  # поднять наверх — раз в сутки
        if item.created_at and datetime.utcnow() - item.created_at < timedelta(hours=24):
            return json_error("Поднимать объявление можно раз в сутки")
        item.created_at = datetime.utcnow()
    elif action == "delete":
        from services.uploads import delete_file
        for p in _photos(item):
            delete_file(p)
        db.query(m.MarketFav).filter_by(item_id=item.id).delete()
        db.delete(item)
    else:
        return json_error("Неизвестное действие")
    db.commit()
    return JSONResponse({"ok": True})


# ======================================================================== привычки
COLORS = ["#6d5dfc", "#ec4899", "#f59e0b", "#10b981", "#06b6d4", "#ef4444", "#8b5cf6", "#64748b"]


def _streak(days, t):
    """Серия дней подряд, заканчивающаяся сегодня или вчера."""
    d = datetime.strptime(t, "%Y-%m-%d")
    if t not in days:
        d -= timedelta(days=1)
    n = 0
    while d.strftime("%Y-%m-%d") in days:
        n += 1
        d -= timedelta(days=1)
    return n


@router.get("/habits")
def habits(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    t = today(user)
    rows = db.query(m.Habit).filter_by(user_id=user.id).order_by(m.Habit.id).all()
    checks = {}
    if rows:
        for c in db.query(m.HabitCheck).filter(m.HabitCheck.habit_id.in_([h.id for h in rows])):
            checks.setdefault(c.habit_id, set()).add(c.day)
    base = datetime.strptime(t, "%Y-%m-%d")
    last30 = [(base - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(29, -1, -1)]
    data = [{"h": h, "done": t in checks.get(h.id, set()), "streak": _streak(checks.get(h.id, set()), t),
             "days": [(d, d in checks.get(h.id, set())) for d in last30], "total": len(checks.get(h.id, set()))} for h in rows]
    return render(request, db, "packs/v3/habits.html", items=data, colors=COLORS, today=t)


@router.post("/habits")
async def habit_create(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    data = await read_payload(request)
    name = censor(s(data.get("name")).strip()[:50], social.stop_words(db))
    if not name:
        return json_error("Назовите привычку")
    if db.query(m.Habit).filter_by(user_id=user.id).count() >= 20:
        return json_error("Можно вести до 20 привычек")
    color = s(data.get("color")) if s(data.get("color")) in COLORS else COLORS[0]
    db.add(m.Habit(user_id=user.id, name=name, color=color))
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/habits/{habit_id}/{action}")
def habit_action(habit_id: int, action: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    h = db.query(m.Habit).filter_by(id=habit_id, user_id=user.id if user else -1).first()
    if not h:
        return json_error("Привычка не найдена", 404)
    if action == "check":
        t = today(user)
        row = db.query(m.HabitCheck).filter_by(habit_id=h.id, day=t).first()
        if row:
            db.delete(row)
        else:
            db.add(m.HabitCheck(habit_id=h.id, day=t))
        db.commit()
        days = {c.day for c in db.query(m.HabitCheck.day).filter_by(habit_id=h.id)}
        return JSONResponse({"ok": True, "done": not row, "streak": _streak(days, t)})
    if action == "delete":
        db.query(m.HabitCheck).filter_by(habit_id=h.id).delete()
        db.delete(h)
        db.commit()
        return JSONResponse({"ok": True})
    return json_error("Неизвестное действие")


# ======================================================================== дневник настроения
MOODS = [(1, "Плохо", "#ef4444"), (2, "Так себе", "#f59e0b"), (3, "Нормально", "#a1a1aa"), (4, "Хорошо", "#22c55e"), (5, "Отлично", "#6d5dfc")]


@router.get("/mood")
def mood(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    t = today(user)
    base = datetime.strptime(t, "%Y-%m-%d")
    days = [(base - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(29, -1, -1)]
    rows = {r.day: r for r in db.query(m.MoodEntry).filter(m.MoodEntry.user_id == user.id, m.MoodEntry.day >= days[0])}
    lv = [r.level for r in rows.values()]
    avg = round(sum(lv) / len(lv), 1) if lv else None
    notes = (db.query(m.MoodEntry).filter(m.MoodEntry.user_id == user.id, m.MoodEntry.note != "")
             .order_by(m.MoodEntry.day.desc()).limit(10).all())
    return render(request, db, "packs/v3/mood.html", moods=MOODS, mood_by={k: (t2, c) for k, t2, c in MOODS}, today=t,
                  current=rows.get(t), days=[(d, rows.get(d)) for d in days], avg=avg, notes=notes)


@router.post("/mood")
async def mood_save(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    data = await read_payload(request)
    try:
        level = int(s(data.get("level"))[:1])
    except ValueError:
        return json_error("Выберите настроение")
    if not 1 <= level <= 5:
        return json_error("Выберите настроение")
    t = today(user)
    row = db.query(m.MoodEntry).filter_by(user_id=user.id, day=t).first()
    if not row:
        row = m.MoodEntry(user_id=user.id, day=t)
        db.add(row)
    row.level, row.note = level, s(data.get("note")).strip()[:300]
    db.commit()
    return JSONResponse({"ok": True})


# ======================================================================== капсула времени
@router.get("/capsule")
def capsule(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    now = datetime.utcnow()
    rows = db.query(m.Capsule).filter_by(user_id=user.id).order_by(m.Capsule.open_at.asc()).all()
    return render(request, db, "packs/v3/capsule.html", now=now, sealed=[c for c in rows if c.open_at > now],
                  opened=sorted([c for c in rows if c.open_at <= now], key=lambda c: c.open_at, reverse=True))


@router.post("/capsule")
async def capsule_create(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    data = await read_payload(request)
    text = s(data.get("text")).strip()[:5000]
    if len(text) < 3:
        return json_error("Напишите письмо себе")
    period = s(data.get("period"))
    now = datetime.utcnow()
    if period in ("1m", "6m", "1y"):
        at = now + timedelta(days={"1m": 30, "6m": 182, "1y": 365}[period])
    else:
        try:
            at = timezones.from_local(datetime.strptime(s(data.get("date"))[:10], "%Y-%m-%d").replace(hour=9), user)
        except ValueError:
            return json_error("Выберите, когда открыть письмо")
    if at <= now + timedelta(hours=1) or at > now + timedelta(days=365 * 10):
        return json_error("Дата — от завтра и не дальше чем через 10 лет")
    if db.query(m.Capsule).filter(m.Capsule.user_id == user.id, m.Capsule.open_at > now).count() >= 50:
        return json_error("Слишком много запечатанных писем")
    db.add(m.Capsule(user_id=user.id, text=text, open_at=at))
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/capsule/{cid}/delete")
def capsule_delete(cid: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    db.query(m.Capsule).filter_by(id=cid, user_id=user.id).delete()
    db.commit()
    return JSONResponse({"ok": True})


def capsules_due(db):
    """Фоновая задача: письмо из прошлого открылось — уведомление."""
    now = datetime.utcnow()
    for c in db.query(m.Capsule).filter(m.Capsule.open_at <= now, m.Capsule.notified == False).limit(100).all():
        c.notified = True
        days = max(1, (now - c.created_at).days) if c.created_at else 1
        db.add(models.Notification(user_id=c.user_id, type="capsule", text=f"Открылось письмо, которое вы написали себе {days} дн. назад"))
    db.commit()

