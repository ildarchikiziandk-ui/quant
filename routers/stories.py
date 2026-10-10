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
from services import gamification, social
from services.uploads import delete_file, is_upload, save_file

router = APIRouter()
STORY_REACTIONS = ["❤️", "🔥", "😂", "😮", "😢", "👏"]
STORY_BG = ["#18181b", "#334155", "#1e3a8a", "#14532d", "#7f1d1d", "#78350f"]


def can_see_story(db, viewer, story, close_cache=None):
    owner = story.author
    if not owner:
        return False
    if viewer and viewer.id == owner.id:
        return True
    if not social.can_see_content(db, viewer, owner):
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
    stories = db.query(models.Story).filter(models.Story.expires_at > now).order_by(models.Story.created_at.asc()).all()
    hidden = social.blocked_ids(db, user) | social.muted_ids(db, user)
    seen = set()
    if user:
        seen = {v.story_id for v in db.query(models.StoryView.story_id).filter(models.StoryView.user_id == user.id)}
    groups = {}
    for s in stories:
        if s.user_id in hidden or not can_see_story(db, user, s):
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
    return render(request, db, "stories_create.html", bg_colors=STORY_BG)


@router.post("/stories/create")
async def create_story(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    if social.is_active_block(user) or social.needs_email(user):
        return redirect("/verify" if social.needs_email(user) else "/")
    form = await request.form()
    text = (form.get("text_overlay") or "").strip()[:300]
    bg = form.get("bg_color") if re.match(r"^#[0-9a-fA-F]{6}$", form.get("bg_color") or "") else ""
    url, mtype = "", "text"
    if is_upload(form.get("media")):
        url, mtype = save_file(form.get("media"), allowed=("image", "video"))
        if not url:
            return render(request, db, "stories_create.html", bg_colors=STORY_BG, error=mtype)
    elif not text:
        return render(request, db, "stories_create.html", bg_colors=STORY_BG, error="Добавьте фото, видео или текст")
    story = models.Story(user_id=user.id, media_url=url, media_type=mtype, text_overlay=text, bg_color=bg or "#18181b",
                         audience="close" if form.get("audience") == "close" else "all",
                         expires_at=datetime.utcnow() + timedelta(hours=24))
    db.add(story)
    gamification.add_points(user, db, 5)
    db.commit()
    gamification.complete_task(user, db, "story")
    if db.query(models.Story).filter_by(user_id=user.id).count() >= 10:
        gamification.check_achievement(user, db, "storyteller")
        db.commit()
    return redirect(f"/stories/{user.username}")


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
    if user and user.id != su.id:
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
                  highlights=highlights)


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
    text = (data.get("text") or "").strip()[:1000]
    if not text:
        return json_error("Пустой ответ")
    ok, reason = social.can_message(db, user, s.author)
    if not ok:
        return json_error(reason, 403)
    db.add(models.Message(sender_id=user.id, receiver_id=s.user_id, content=f"↩️ Ответ на историю: {text}"))
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
    if not user or not s or (s.user_id != user.id and not social.can_mod(user)):
        return json_error("forbidden", 403)
    delete_file(s.media_url)
    for model in (models.StoryView, models.StoryReaction, models.StoryHighlightItem):
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
    stories = [i.story for i in h.items if i.story]
    if not stories:
        return redirect(f"/profile/{owner.username}")
    return render(request, db, "stories_view.html", sidebar=False, story_user=owner, stories=stories, next_user=None, start=0,
                  story_reactions=STORY_REACTIONS, my_reactions={}, highlight=h, highlights=[])


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
