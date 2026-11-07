import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import current_user, json_error, login_redirect, redirect, render
from routers.posts import read_payload, wants_json
from services import gamification, plus, prefs, social
from services.uploads import delete_file, is_upload, save_file

router = APIRouter()
STORY_REACTIONS = ["❤️", "🐋"]
STORY_BG = ["#18181b", "#334155", "#1e3a8a", "#14532d", "#7f1d1d", "#78350f"]


# ---------------------------------------------------------------- оформление, ссылка, опрос (7.11.2026)
import json as _json

TEXT_COLORS = ["#ffffff", "#1f1d1a", "#f0c24a", "#e8813a", "#7fb3e0", "#f39ab4"]
FONTS = {"onest": "Обычный", "unb": "Заголовок", "serif": "Книжный", "mono": "Печатная машинка"}
DURATIONS = {"6": 6, "12": 12, "24": 24, "48": 48}


def story_extra(s):
    try:
        return _json.loads(s.extra or "{}") or {}
    except ValueError:
        return {}


def _clean_link(url):
    url = (url or "").strip()[:300]
    if not url:
        return ""
    from deps import safe_next
    if url.startswith("/"):
        return url if safe_next(url) == url else ""
    if not re.match(r"^https?://", url):
        url = "https://" + url
    return url if re.match(r"^https?://[^\s/]+\.[^\s]{2,}$", url) else ""


def media_in_use(db, url, story_id=None):
    """Файл нужен ещё кому-то (пост, другая история — «поделиться снова», пост в истории)? Тогда не удаляем."""
    if not url:
        return False
    q = db.query(models.Story.id).filter(models.Story.media_url == url)
    if story_id:
        q = q.filter(models.Story.id != story_id)
    return bool(q.first() or db.query(models.Post.id).filter(models.Post.image == url).first()
                or db.query(models.PostMedia.id).filter(models.PostMedia.media_url == url).first())


def _notify_mentions(db, user, story):
    names = list(dict.fromkeys(m.lower() for m in re.findall(r"@([A-Za-z0-9_.]{3,30})", story.text_overlay or "")))[:5]
    for n in names:
        u = db.query(models.User).filter(func.lower(models.User.username) == n).first()
        if u and u.id != user.id and not social.is_blocked_between(db, u, user):
            db.add(models.Notification(user_id=u.id, from_user_id=user.id, type="story_mention", text="отметил(а) вас в истории"))


def can_see_story(db, viewer, story, close_cache=None):
    owner = story.author
    if not owner:
        return False
    if viewer and viewer.id == owner.id:
        return True
    from packs.v3.accounts import posts_locked
    if posts_locked(viewer):  # «только чаты и профиль»: чужие истории не видны
        return False
    if not social.can_see_content(db, viewer, owner) or owner.is_paused:
        return False
    if not viewer and prefs.get(owner, "guests_hidden"):
        return False
    mode = owner.who_can_see_stories or "all"
    is_close = viewer and db.query(models.CloseFriend.id).filter_by(user_id=owner.id, friend_id=viewer.id).first() is not None
    if story.audience == "close" or mode == "close":
        return bool(is_close)
    if mode == "followers":
        return social.is_following(db, viewer, owner)
    return True


def story_groups(db, user):
    now = datetime.utcnow()
    from sqlalchemy.orm import selectinload
    stories = (db.query(models.Story).options(selectinload(models.Story.author)).filter(models.Story.expires_at > now)
               .order_by(models.Story.created_at.asc()).all())
    hidden = social.blocked_ids(db, user) | social.muted_ids(db, user)
    seen = set()
    if user and stories:
        seen = {v.story_id for v in db.query(models.StoryView.story_id).filter(
            models.StoryView.user_id == user.id, models.StoryView.story_id.in_([s.id for s in stories]))}
    # права проверяем один раз на автора, а не на каждую историю (главная открывается часто)
    from packs.v3.accounts import posts_locked
    locked = posts_locked(user)
    fids = social.following_ids(db, user)
    close_of = {c.user_id for c in db.query(models.CloseFriend.user_id).filter(models.CloseFriend.friend_id == user.id)} if user else set()
    memo = {}

    def visible(s):
        owner = s.author
        if not owner:
            return False
        if user and owner.id == user.id:
            return True
        if locked:
            return False
        if owner.id not in memo:
            base = not owner.is_paused and not (not user and prefs.get(owner, "guests_hidden"))
            if base and owner.is_private and not (user and social.can_mod(user)):
                base = owner.id in fids
            memo[owner.id] = base
        if not memo[owner.id]:
            return False
        mode = owner.who_can_see_stories or "all"
        if s.audience == "close" or mode == "close":
            return owner.id in close_of
        if mode == "followers":
            return owner.id in fids
        return True

    groups = {}
    for s in stories:
        if s.user_id in hidden or not visible(s):
            continue
        g = groups.setdefault(s.user_id, {"user": s.author, "stories": [], "seen": True, "last": s.created_at})
        g["stories"].append(s)
        g["last"] = s.created_at
        if s.id not in seen:
            g["seen"] = False
    result = list(groups.values())
    result.sort(key=lambda g: (not (user and g["user"].id == user.id), g["seen"], -g["last"].timestamp()))
    return result


@router.get("/stories/create")
def stories_create_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    from packs.v3.accounts import posts_locked
    if posts_locked(user):
        return render(request, db, "error.html", status_code=403, code=403, title="Истории недоступны",
                      text="Для вашего аккаунта публикация историй отключена. Переписка и профиль работают как обычно.")
    return render(request, db, "stories_create.html", bg_colors=STORY_BG, text_colors=TEXT_COLORS, fonts=FONTS)


@router.post("/stories/create")
async def create_story(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    if social.is_active_block(user) or social.needs_email(user):
        return redirect("/verify" if social.needs_email(user) else "/")
    from packs.v3.accounts import posts_locked
    if posts_locked(user):
        return json_error("Для вашего аккаунта публикация историй отключена", 403) if wants_json(request) else redirect("/stories/create")
    from packs.v3.admin_tools import publish_blocked
    if publish_blocked(user):
        return json_error(publish_blocked(user), 403) if wants_json(request) else redirect("/stories/create")
    form = await request.form()
    text = (form.get("text_overlay") or "").strip()[:300]
    bg = form.get("bg_color") if re.match(r"^#[0-9a-fA-F]{6}$", form.get("bg_color") or "") else ""
    url, mtype = "", "text"
    if is_upload(form.get("media")):
        url, mtype = save_file(form.get("media"), allowed=("image", "video"))
        if not url:
            return render(request, db, "stories_create.html", bg_colors=STORY_BG, text_colors=TEXT_COLORS, fonts=FONTS, error=mtype)
    elif not text:
        return render(request, db, "stories_create.html", bg_colors=STORY_BG, text_colors=TEXT_COLORS, fonts=FONTS, error="Добавьте фото, видео или текст")
    hours = DURATIONS.get(form.get("duration") or "24", 24)
    if hours == 48 and not plus.active(user):
        hours = 24
    extra = {}
    style = {"c": form.get("tcolor") if form.get("tcolor") in TEXT_COLORS else "#ffffff",
             "f": form.get("font") if form.get("font") in FONTS else "onest",
             "s": form.get("tsize") if form.get("tsize") in ("s", "m", "l") else "m",
             "p": form.get("tpos") if form.get("tpos") in ("top", "center", "bottom") else "center",
             "b": bool(form.get("plate"))}
    if style != {"c": "#ffffff", "f": "onest", "s": "m", "p": "center", "b": False}:
        extra["style"] = style
    link = _clean_link(form.get("link_url"))
    if link:
        extra["link"] = {"url": link, "label": (form.get("link_label") or "").strip()[:30] or "Открыть ссылку"}
    pq, pa, pb = ((form.get(k) or "").strip() for k in ("poll_q", "poll_a", "poll_b"))
    if pq and pa and pb:
        extra["poll"] = {"q": pq[:80], "a": pa[:30], "b": pb[:30]}
    from services.text import banned
    if banned(" ".join([text, extra.get("link", {}).get("label", ""), pq, pa, pb]), social.stop_words(db)):
        return render(request, db, "stories_create.html", bg_colors=STORY_BG, text_colors=TEXT_COLORS, fonts=FONTS, error="В тексте есть запрещённые слова")
    story = models.Story(user_id=user.id, media_url=url, media_type=mtype, text_overlay=text, bg_color=bg or "#18181b",
                         audience="close" if form.get("audience") == "close" else "all", extra=_json.dumps(extra, ensure_ascii=False) if extra else "",
                         expires_at=datetime.utcnow() + timedelta(hours=hours))
    db.add(story)
    db.flush()
    _notify_mentions(db, user, story)
    gamification.add_points(user, db, 3)
    db.commit()
    gamification.complete_task(user, db, "story")
    if db.query(models.Story).filter_by(user_id=user.id).count() >= 10:
        gamification.check_achievement(user, db, "storyteller")
        db.commit()
    return redirect(f"/stories/{user.username}")


@router.get("/stories/archive")
def story_archive(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    items = db.query(models.Story).filter_by(user_id=user.id).order_by(models.Story.created_at.desc()).limit(300).all()
    return render(request, db, "stories_archive.html", items=items, now=datetime.utcnow(), extras={s.id: story_extra(s) for s in items})


@router.get("/stories/{username}")
def view_stories(username: str, request: Request, start: int = 0, db: Session = Depends(get_db)):
    user = current_user(request, db)
    su = db.query(models.User).filter(func.lower(models.User.username) == username.lower()).first()
    if not su:
        return redirect("/")
    stories = [s for s in db.query(models.Story).filter(models.Story.user_id == su.id, models.Story.expires_at > datetime.utcnow())
               .order_by(models.Story.created_at.asc()).all() if can_see_story(db, user, s)]
    if not stories:
        return redirect(f"/profile/{su.username}")
    if user and user.id != su.id and not prefs.get(user, "anonymous_stories"):
        seen = {v.story_id for v in db.query(models.StoryView).filter(models.StoryView.user_id == user.id,
                                                                      models.StoryView.story_id.in_([s.id for s in stories]))}
        for s in stories:
            if s.id not in seen:
                db.add(models.StoryView(story_id=s.id, user_id=user.id))
        db.commit()
    groups = story_groups(db, user)
    order = [g["user"].username for g in groups]
    nxt = None
    if su.username in order:
        i = order.index(su.username)
        nxt = order[i + 1] if i + 1 < len(order) else None
    my_reactions = {}
    if user:
        my_reactions = {r.story_id: r.emoji for r in db.query(models.StoryReaction).filter(
            models.StoryReaction.user_id == user.id, models.StoryReaction.story_id.in_([s.id for s in stories]))}
    highlights = db.query(models.StoryHighlight).filter_by(user_id=user.id).all() if user and user.id == su.id else []
    return render(request, db, "stories_view.html", sidebar=False, story_user=su, stories=stories, next_user=nxt,
                  start=max(0, min(start, len(stories) - 1)), story_reactions=STORY_REACTIONS, my_reactions=my_reactions,
                  highlights=highlights, extras={s.id: story_extra(s) for s in stories}, polls=poll_state(db, stories, user))


def poll_state(db, stories, user):
    ids = [s.id for s in stories if '"poll"' in (s.extra or "")]
    out = {i: {"a": 0, "b": 0, "mine": None} for i in ids}
    if ids:
        for v in db.query(models.StoryVote).filter(models.StoryVote.story_id.in_(ids)).all():
            out[v.story_id]["a" if v.choice == 0 else "b"] += 1
            if user and v.user_id == user.id:
                out[v.story_id]["mine"] = v.choice
    return out


@router.post("/stories/{story_id}/vote")
async def story_vote(story_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    s = _story(db, story_id)
    if not user or not s or not can_see_story(db, user, s) or "poll" not in story_extra(s):
        return json_error("Опрос не найден", 404)
    data = await read_payload(request)
    choice = 1 if str(data.get("choice")) == "1" else 0
    if not db.query(models.StoryVote).filter_by(story_id=s.id, user_id=user.id).first():
        db.add(models.StoryVote(story_id=s.id, user_id=user.id, choice=choice))
        try:
            db.commit()
        except Exception:  # noqa: BLE001 — два нажатия разом
            db.rollback()
    st = poll_state(db, [s], user)[s.id]
    return JSONResponse({"ok": True, **st})


@router.post("/stories/{story_id}/again")
def story_again(story_id: int, request: Request, db: Session = Depends(get_db)):
    """Поделиться своей историей снова — копия на 24 часа (из архива)."""
    user = current_user(request, db)
    s = _story(db, story_id)
    if not user or not s or s.user_id != user.id:
        return json_error("forbidden", 403)
    from packs.v3.accounts import posts_locked
    if posts_locked(user):
        return json_error("Публикация историй отключена", 403)
    db.add(models.Story(user_id=user.id, media_url=s.media_url, media_type=s.media_type, text_overlay=s.text_overlay, bg_color=s.bg_color,
                        audience=s.audience, extra=s.extra or "", expires_at=datetime.utcnow() + timedelta(hours=24)))
    db.commit()
    return JSONResponse({"ok": True, "url": f"/stories/{user.username}"})


def _story(db, story_id):
    return db.get(models.Story, story_id)


@router.post("/stories/{story_id}/react")
@router.post("/stories/react/{story_id}")
async def react_story(story_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    s = _story(db, story_id)
    if not user or not s or not can_see_story(db, user, s):
        return json_error("not found", 404)
    data = await read_payload(request)
    emoji = data.get("emoji")
    if emoji not in STORY_REACTIONS:
        return json_error("bad emoji")
    ex = db.query(models.StoryReaction).filter_by(story_id=story_id, user_id=user.id).first()
    if ex and ex.emoji == emoji:
        db.delete(ex)
    elif ex:
        ex.emoji = emoji
    else:
        db.add(models.StoryReaction(story_id=story_id, user_id=user.id, emoji=emoji))
        social.notify(db, s.user_id, "story_reaction", user, text=f"отреагировал(а) {emoji} на вашу историю", url=f"/stories/{s.author.username}")
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/stories/{story_id}/reply")
async def reply_story(story_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    s = _story(db, story_id)
    if not user or not s or not can_see_story(db, user, s) or s.user_id == user.id:
        return json_error("not found", 404)
    data = await read_payload(request)
    text = str(data.get("text") or "").strip()[:1000]
    if not text:
        return json_error("Пустой ответ")
    ok, reason = social.can_message(db, user, s.author)
    if not ok:
        return json_error(reason, 403)
    db.add(models.Message(sender_id=user.id, receiver_id=s.user_id, content=f"Ответ на историю: {text}"))
    db.commit()
    return JSONResponse({"ok": True})


@router.get("/stories/{story_id}/viewers")
def story_viewers(story_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    s = _story(db, story_id)
    if not user or not s or s.user_id != user.id:
        return json_error("forbidden", 403)
    reactions = {r.user_id: r.emoji for r in db.query(models.StoryReaction).filter_by(story_id=story_id)}
    views = db.query(models.StoryView).filter_by(story_id=story_id).order_by(models.StoryView.viewed_at.desc()).all()
    users = [db.get(models.User, v.user_id) for v in views]
    return JSONResponse({"ok": True, "count": len(views), "users": [
        {"username": u.username, "name": u.name or u.username, "avatar": u.avatar or "", "reaction": reactions.get(u.id, "")}
        for u in users if u]})


@router.post("/stories/{story_id}/delete")
@router.post("/story/delete/{story_id}")
def delete_story(story_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    s = _story(db, story_id)
    if not user or not s or (s.user_id != user.id and not social.can_mod_user(user, s.author)):
        return json_error("forbidden", 403)
    if not media_in_use(db, s.media_url, s.id):
        delete_file(s.media_url)
    for model in (models.StoryView, models.StoryReaction, models.StoryHighlightItem, models.StoryVote):
        db.query(model).filter(model.story_id == story_id).delete(synchronize_session=False)
    db.delete(s)
    db.commit()
    if wants_json(request):
        return JSONResponse({"ok": True})
    return redirect("/")


@router.post("/stories/{story_id}/highlight")
async def add_highlight(story_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    s = _story(db, story_id)
    if not user or not s or s.user_id != user.id:
        return json_error("forbidden", 403)
    data = await read_payload(request)
    hid = data.get("highlight_id")
    h = db.query(models.StoryHighlight).filter_by(id=int(hid), user_id=user.id).first() if hid and str(hid).isdigit() else None
    if not h:
        title = (data.get("title") or "Актуальное").strip()[:30]
        h = models.StoryHighlight(user_id=user.id, title=title)
        db.add(h)
        db.flush()
    if not db.query(models.StoryHighlightItem).filter_by(highlight_id=h.id, story_id=s.id).first():
        db.add(models.StoryHighlightItem(highlight_id=h.id, story_id=s.id))
    db.commit()
    return JSONResponse({"ok": True, "highlight_id": h.id})


@router.get("/highlights/{highlight_id}")
def view_highlight(highlight_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    h = db.get(models.StoryHighlight, highlight_id)
    if not h:
        return redirect("/")
    owner = db.get(models.User, h.user_id)
    if not owner or not social.can_see_content(db, user, owner):
        return redirect("/")
    stories = [i.story for i in h.items if i.story and can_see_story(db, user, i.story)]
    if not stories:
        return redirect(f"/profile/{owner.username}")
    return render(request, db, "stories_view.html", sidebar=False, story_user=owner, stories=stories, next_user=None, start=0,
                  story_reactions=STORY_REACTIONS, my_reactions={}, highlight=h, highlights=[],
                  extras={s.id: story_extra(s) for s in stories}, polls=poll_state(db, stories, current_user(request, db)))


@router.post("/highlights/{highlight_id}/delete")
def delete_highlight(highlight_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    h = db.get(models.StoryHighlight, highlight_id)
    if not user or not h or h.user_id != user.id:
        return json_error("forbidden", 403)
    db.query(models.StoryHighlightItem).filter_by(highlight_id=h.id).delete()
    db.delete(h)
    db.commit()
    return redirect(f"/profile/{user.username}")


@router.post("/post/{post_id}/to-story")
def post_to_story(post_id: int, request: Request, db: Session = Depends(get_db)):
    """Поделиться постом в своей истории (7.11.2026): картинка поста, начало текста и кнопка «Открыть пост»."""
    user = current_user(request, db)
    from routers.posts import _check_access
    post, err = _check_access(db, user, post_id)
    if err:
        return err
    from packs.v3.accounts import posts_locked
    if posts_locked(user) or social.is_active_block(user):
        return json_error("Публикация историй отключена", 403)
    if getattr(post, "visibility", "all") not in ("all", "", None) and post.user_id != user.id:
        return json_error("Этот пост видят не все — в историю его не поделиться", 403)
    author = post.author
    url, mtype = "", "text"
    if post.image and (post.media_type or "image") in ("image", "video"):
        url, mtype = post.image, post.media_type or "image"
    text = (post.content or "").strip()
    text = (text[:140] + "…") if len(text) > 140 else text
    if author and author.id != user.id:
        text = (f"@{author.username}: " + text) if text else f"Пост @{author.username}"
    extra = {"link": {"url": f"/post/{post.id}", "label": "Открыть пост"}, "post": post.id,
             "style": {"c": "#ffffff", "f": "onest", "s": "s" if len(text) > 80 else "m", "p": "bottom" if url else "center", "b": bool(url)}}
    db.add(models.Story(user_id=user.id, media_url=url, media_type=mtype, text_overlay=text[:300], bg_color=STORY_BG[2],
                        extra=_json.dumps(extra, ensure_ascii=False), expires_at=datetime.utcnow() + timedelta(hours=24)))
    db.commit()
    return JSONResponse({"ok": True, "url": f"/stories/{user.username}"})
