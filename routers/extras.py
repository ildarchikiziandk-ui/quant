"""Новые функции: вопросы, подписка на хэштеги, мероприятия, подарки, коллекции закладок, приглашения,
воспоминания и люди по интересам."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import config
import models
from database import get_db
from deps import current_user, json_error, login_redirect, redirect, render
from routers.posts import _parse_dt, read_payload, wants_json
from services import extras, feed, gamification, moderation, prefs, ratelimit, recommend, social, timezones
from services.text import BANNED_MSG, banned

router = APIRouter()


def _user(db, username):
    return db.query(models.User).filter(models.User.username == username.lstrip("@")).first()


def _moderate_text(text):
    """Вопросы и подписи к подаркам проверяются собственной моделью до доставки."""
    r = moderation.check(text)
    return r["score"] < config.MOD_FLAG_THRESHOLD


# ===================================== Вопросы =====================================
@router.get("/ask/{username}")
def ask_page(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    pu = _user(db, username)
    if not pu:
        return redirect("/")
    answered = (db.query(models.Question).filter(models.Question.to_user_id == pu.id, models.Question.answer != "",
                                                 models.Question.answer != None)
                .order_by(models.Question.answered_at.desc()).limit(100).all())
    can_ask = bool(user and user.id != pu.id and prefs.audience_allows(db, pu, user, "who_can_ask")
                   and not social.is_blocked_between(db, user, pu))
    return render(request, db, "ask.html", profile_user=pu, answered=answered, can_ask=can_ask,
                  allow_anon=prefs.get(pu, "allow_anonymous_questions"))


@router.post("/ask/{username}")
async def ask_send(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    pu = _user(db, username)
    if not user or not pu:
        return json_error("not found", 404)
    if user.id == pu.id or not prefs.audience_allows(db, pu, user, "who_can_ask") or social.is_blocked_between(db, user, pu):
        return json_error("Этот пользователь не принимает вопросы от вас", 403)
    if social.needs_email(user):
        return json_error(social.VERIFY_MSG, 403)
    if not ratelimit.hit(f"ask:{user.id}", 10, 3600):
        return json_error("Слишком много вопросов, попробуйте позже", 429)
    data = await read_payload(request)
    text = str(data.get("text") or "").strip()[:500]
    if banned(text, social.stop_words(db)):
        return json_error(BANNED_MSG)
    if len(text) < 2:
        return json_error("Вопрос пустой")
    if not _moderate_text(text):
        return json_error("Вопрос похож на оскорбление или спам — переформулируйте, пожалуйста")
    anon = bool(data.get("anonymous")) and prefs.get(pu, "allow_anonymous_questions")
    q = models.Question(to_user_id=pu.id, from_user_id=user.id, is_anonymous=anon, text=text)
    db.add(q)
    db.flush()
    social.notify(db, pu.id, "question", None if anon else user, text=("Анонимный вопрос: " if anon else "Вопрос: ") + text[:120],
                  url="/questions")
    db.commit()
    if wants_json(request):
        return JSONResponse({"ok": True})
    return redirect(f"/ask/{pu.username}")


@router.get("/questions")
def questions_inbox(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    inbox = (db.query(models.Question).filter(models.Question.to_user_id == user.id,
                                              (models.Question.answer == "") | (models.Question.answer == None))
             .order_by(models.Question.created_at.desc()).limit(200).all())
    return render(request, db, "questions.html", inbox=inbox)


@router.post("/questions/{qid}/answer")
async def question_answer(qid: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    q = db.get(models.Question, qid)
    if not user or not q or q.to_user_id != user.id:
        return json_error("not found", 404)
    data = await read_payload(request)
    answer = str(data.get("answer") or "").strip()[:2000]
    if banned(answer, social.stop_words(db)):
        return json_error(BANNED_MSG)
    if not answer:
        return json_error("Ответ пустой")
    q.answer, q.answered_at = answer, datetime.utcnow()
    if data.get("to_feed"):
        content = f"Вопрос: {q.text}\n\n{answer}\n\n#вопросответ"
        post = models.Post(content=content, user_id=user.id, is_long=len(content) > 500)
        db.add(post)
        db.flush()
        moderation.review(db, "post", post, user, content)
    if q.from_user_id and q.from_user_id != user.id:
        social.notify(db, q.from_user_id, "answer", user, text="ответил(а) на ваш вопрос", url=f"/ask/{user.username}#q-{q.id}")
    if db.query(models.Question).filter(models.Question.to_user_id == user.id, models.Question.answer != "").count() >= 4:
        gamification.check_achievement(user, db, "answerer")
    gamification.add_points(user, db, 2)
    db.commit()
    return JSONResponse({"ok": True}) if wants_json(request) else redirect("/questions")


@router.post("/questions/{qid}/delete")
def question_delete(qid: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    q = db.get(models.Question, qid)
    if user and q and (q.to_user_id == user.id or social.can_mod(user)):
        db.delete(q)
        db.commit()
    return JSONResponse({"ok": True}) if wants_json(request) else redirect("/questions")


# ================================ Подписка на хэштеги ================================
@router.post("/hashtag/{tag}/follow")
def hashtag_follow(tag: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    tag = tag.lstrip("#").lower()[:64]
    ex = db.query(models.HashtagFollow).filter_by(user_id=user.id, tag=tag).first()
    if ex:
        db.delete(ex)
    elif db.query(models.HashtagFollow).filter_by(user_id=user.id).count() < 100:
        db.add(models.HashtagFollow(user_id=user.id, tag=tag))
    db.commit()
    recommend.invalidate(user.id)
    return JSONResponse({"ok": True, "following": not ex})


# ===================================== Мероприятия =====================================
@router.get("/events")
def events_page(request: Request, tab: str = "upcoming", db: Session = Depends(get_db)):
    user = current_user(request, db)
    now = datetime.utcnow()
    q = db.query(models.Event)
    if tab == "mine" and user:
        ids = {r.event_id for r in db.query(models.EventRSVP.event_id).filter_by(user_id=user.id)}
        q = q.filter((models.Event.user_id == user.id) | (models.Event.id.in_(ids or {-1})))
        events = q.order_by(models.Event.starts_at.desc()).limit(100).all()
    elif tab == "past":
        events = q.filter(models.Event.starts_at < now).order_by(models.Event.starts_at.desc()).limit(60).all()
    else:
        tab = "upcoming"
        events = q.filter(models.Event.starts_at >= now - timedelta(hours=3)).order_by(models.Event.starts_at.asc()).limit(100).all()
    hidden = social.blocked_ids(db, user)
    events = [e for e in events if e.user_id not in hidden]
    return render(request, db, "events.html", events=events, tab=tab)


@router.get("/events/new")
def event_new(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    return render(request, db, "event_new.html")


@router.post("/events/create")
async def event_create(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    if social.needs_email(user) or social.is_active_block(user):
        return render(request, db, "event_new.html", error="Создавать мероприятия могут только подтверждённые аккаунты")
    form = await request.form()
    title = (form.get("title") or "").strip()[:120]
    description = (form.get("description") or "").strip()[:3000]
    if banned(title, social.stop_words(db)) or banned(description, social.stop_words(db)):
        return render(request, db, "event_new.html", error=BANNED_MSG, form=form)
    starts = timezones.from_local(_parse_dt(form.get("starts_at")), user)
    if not title or not starts:
        return render(request, db, "event_new.html", error="Укажите название и дату", form=form)
    if not ratelimit.hit(f"event:{user.id}", 10, 86400):
        return render(request, db, "event_new.html", error="Слишком много мероприятий за сутки", form=form)
    ev = models.Event(user_id=user.id, title=title, starts_at=starts,
                      description=description,
                      place=(form.get("place") or "").strip()[:200])
    db.add(ev)
    db.flush()
    db.add(models.EventRSVP(event_id=ev.id, user_id=user.id, status="going"))
    gamification.check_achievement(user, db, "event_host")
    db.commit()
    return redirect(f"/events/{ev.id}")


@router.get("/events/{eid}")
def event_page(eid: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    ev = db.get(models.Event, eid)
    if not ev:
        return render(request, db, "error.html", status_code=404, code=404, title="Мероприятие не найдено", text="Возможно, его удалили.")
    my = None
    if user:
        r = db.query(models.EventRSVP).filter_by(event_id=eid, user_id=user.id).first()
        my = r.status if r else None
    going = [r.user for r in ev.rsvps if r.status == "going" and r.user]
    maybe = [r.user for r in ev.rsvps if r.status == "maybe" and r.user]
    return render(request, db, "event.html", ev=ev, my=my, going=going, maybe=maybe, past=ev.starts_at < datetime.utcnow())


@router.post("/events/{eid}/rsvp/{status}")
def event_rsvp(eid: int, status: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    ev = db.get(models.Event, eid)
    if not user or not ev:
        return json_error("not found", 404)
    r = db.query(models.EventRSVP).filter_by(event_id=eid, user_id=user.id).first()
    if status not in ("going", "maybe") or (r and r.status == status):
        if r and ev.user_id != user.id:
            db.delete(r)
    elif r:
        r.status = status
    else:
        db.add(models.EventRSVP(event_id=eid, user_id=user.id, status=status))
        if status == "going":
            social.notify(db, ev.user_id, "event", user, text=f"пойдёт на «{ev.title[:60]}»", url=f"/events/{eid}")
    db.commit()
    return JSONResponse({"ok": True}) if wants_json(request) else redirect(f"/events/{eid}")


@router.post("/events/{eid}/delete")
def event_delete(eid: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    ev = db.get(models.Event, eid)
    if user and ev and (ev.user_id == user.id or social.can_mod(user)):
        db.query(models.EventRSVP).filter_by(event_id=eid).delete()
        db.delete(ev)
        db.commit()
    return redirect("/events")


# ======================================= Подарки =======================================
@router.get("/gifts/{username}")
def gifts_page(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    pu = _user(db, username)
    if not pu:
        return redirect("/")
    received = db.query(models.UserGift).filter_by(to_user_id=pu.id).order_by(models.UserGift.created_at.desc()).limit(100).all()
    return render(request, db, "gifts.html", profile_user=pu, received=received, gifts=extras.GIFTS, gift_by=extras.GIFT_BY_CODE,
                  balance=extras.balance(user) if user else 0)


@router.post("/gifts/{username}/send")
async def gift_send(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    pu = _user(db, username)
    if not user or not pu:
        return json_error("not found", 404)
    if user.id == pu.id or social.is_blocked_between(db, user, pu):
        return json_error("Нельзя отправить подарок этому пользователю", 403)
    data = await read_payload(request)
    g = extras.GIFT_BY_CODE.get(data.get("gift") or "")
    if not g:
        return json_error("Такого подарка нет")
    from services import plus
    if g[0] in plus.EXCLUSIVE_GIFTS and not plus.active(user):
        return json_error("Этот подарок доступен только с Nuvora+")
    price = plus.gift_price(user, g[3])
    if extras.balance(user) < price:
        return json_error(f"Не хватает искр: нужно {price}, у вас {extras.balance(user)}")
    msg = str(data.get("message") or "").strip()[:140]
    if banned(msg, social.stop_words(db)):
        return json_error(BANNED_MSG)
    if msg and not _moderate_text(msg):
        return json_error("Подпись похожа на оскорбление — измените её")
    anon = bool(data.get("anonymous"))
    user.spent_points = (user.spent_points or 0) + price
    gift = models.UserGift(gift_code=g[0], from_user_id=user.id, to_user_id=pu.id, message=msg, is_anonymous=anon)
    db.add(gift)
    db.flush()
    if not anon and social.can_message(db, user, pu)[0]:
        # подарок виден и в переписке — карточкой (без отдельного push: уведомление о подарке уже приходит)
        db.add(models.Message(sender_id=user.id, receiver_id=pu.id, content=f"[[v3:gift:{gift.id}]]",
                              is_delivered=social.is_online(pu), silent=True))
    social.notify(db, pu.id, "gift", None if anon else user, text=f"Вам подарили подарок «{g[2]}»" + (f": «{msg}»" if msg else ""),
                  url=f"/gifts/{pu.username}")
    gamification.check_achievement(user, db, "generous")
    db.commit()
    if wants_json(request):
        return JSONResponse({"ok": True, "balance": extras.balance(user)})
    return redirect(f"/gifts/{pu.username}")


# ================================= Коллекции закладок =================================
@router.post("/collections/create")
async def collection_create(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    data = await read_payload(request)
    name = str(data.get("name") or "").strip()[:40]
    if name and db.query(models.BookmarkCollection).filter_by(user_id=user.id).count() < 50:
        c = models.BookmarkCollection(user_id=user.id, name=name, emoji=(data.get("emoji") or "📁").strip()[:4] or "📁")
        db.add(c)
        db.commit()
        return redirect(f"/bookmarks?c={c.id}")
    return redirect("/bookmarks")


@router.post("/collections/{cid}/delete")
def collection_delete(cid: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    c = db.get(models.BookmarkCollection, cid)
    if user and c and c.user_id == user.id:
        db.query(models.Bookmark).filter_by(user_id=user.id, collection_id=cid).update({"collection_id": None})
        db.delete(c)
        db.commit()
    return redirect("/bookmarks")


@router.post("/bookmarks/{post_id}/move")
async def bookmark_move(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    data = await read_payload(request)
    cid = data.get("collection_id")
    cid = int(cid) if cid and str(cid).isdigit() else None
    if cid and not db.query(models.BookmarkCollection).filter_by(id=cid, user_id=user.id).first():
        return json_error("not found", 404)
    bm = db.query(models.Bookmark).filter_by(user_id=user.id, post_id=post_id).first()
    if not bm and not db.get(models.Post, post_id):
        return json_error("not found", 404)
    if not bm:
        bm = models.Bookmark(user_id=user.id, post_id=post_id)
        db.add(bm)
    bm.collection_id = cid
    db.commit()
    return JSONResponse({"ok": True}) if wants_json(request) else redirect(f"/bookmarks{'?c=' + str(cid) if cid else ''}")


# ===================================== Приглашения =====================================
@router.get("/invite")
def invite_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    from packs.v3 import growth
    return render(request, db, "invite.html", link=f"{config.SITE_URL}/invite/{user.username}", **growth.invite_stats(db, user))


@router.get("/invite/{username}")
def invite_link(username: str, request: Request, db: Session = Depends(get_db)):
    inviter = _user(db, username)
    if current_user(request, db) or not inviter:
        return redirect("/")
    resp = redirect(f"/register?ref={inviter.username}")
    resp.set_cookie("ref", inviter.username, max_age=7 * 86400, httponly=True, samesite="lax", secure=config.COOKIE_SECURE)
    return resp


def reward_inviter(db, new_user, ref):
    """Вызывается после регистрации: +100 искр пригласившему и достижение."""
    inviter = _user(db, ref) if ref else None
    if not inviter or inviter.id == new_user.id:
        return
    new_user.referred_by = inviter.id
    from packs.v3 import growth  # награда частями: сразу немного, остальное — когда друг освоится
    growth.on_register(db, new_user, inviter)
    gamification.check_achievement(inviter, db, "inviter")


# ===================================== Воспоминания =====================================
@router.get("/memories")
def memories_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    posts = extras.memories(db, user)
    return render(request, db, "memories.html", **feed.feed_context(db, user, posts))


# ================================== Люди по интересам ==================================
@router.get("/interests/{tag}")
def interest_people(tag: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    tag = extras.parse_interests(tag)[0] if extras.parse_interests(tag) else ""
    people = []
    if tag:
        hidden = social.blocked_ids(db, user)
        for u in (db.query(models.User).filter(models.User.interests.ilike(f"%{tag}%"), models.User.is_blocked == False,
                                               prefs.sql_flag_off(models.User.prefs, "hide_from_search"))
                  .order_by(models.User.total_points.desc()).limit(200)):
            if tag in extras.interests(u) and u.id not in hidden:
                people.append(u)
    return render(request, db, "interest.html", tag=tag, people=people, following=social.following_ids(db, user))
