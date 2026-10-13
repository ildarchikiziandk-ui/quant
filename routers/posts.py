from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

import config
import models
from database import get_db
from deps import REACTIONS, blocked_page, current_user, json_error, login_redirect, redirect, render
from services import feed, gamification, moderation, prefs, ratelimit, social
from services.text import censor, extract_hashtags
from services.uploads import delete_file, is_upload, save_file

router = APIRouter()


def wants_json(request: Request):
    return request.headers.get("x-requested-with") == "fetch" or "application/json" in request.headers.get("accept", "")


async def read_payload(request: Request):
    ct = request.headers.get("content-type", "")
    if "application/json" in ct:
        try:
            data = await request.json()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    form = await request.form()
    return {k: form.get(k) for k in form.keys()}


def update_trends(db, content, delta=1):
    for tag in extract_hashtags(content):
        t = db.query(models.Trend).filter_by(tag=tag).first()
        if t:
            t.count = max(0, (t.count or 0) + delta)
            t.updated_at = datetime.utcnow()
        elif delta > 0:
            db.add(models.Trend(tag=tag, count=1))
            db.flush()


def _get_post(db, post_id):
    return db.get(models.Post, post_id)


def _parse_dt(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


# --- Просмотр поста ----------------------------------------------------------
@router.get("/post/{post_id}")
def post_page(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    post = _get_post(db, post_id)
    if not social.can_view_post(db, user, post):
        return render(request, db, "error.html", status_code=404, code=404, title="Пост недоступен",
                      text="Пост удалён, скрыт настройками приватности или ещё не опубликован.")
    if not user or user.id != post.user_id:
        post.views = (post.views or 0) + 1
        db.commit()
    hidden = social.blocked_ids(db, user)
    comments = (db.query(models.Comment).filter(models.Comment.post_id == post_id)
                .order_by(models.Comment.is_pinned.desc(), models.Comment.created_at.asc()).all())
    comments = [c for c in comments if c.user_id not in hidden]
    roots = [c for c in comments if not c.parent_id]
    children = {}
    for c in comments:
        if c.parent_id:
            children.setdefault(c.parent_id, []).append(c)
    liked_comments = set()
    if user and comments:
        liked_comments = {r.comment_id for r in db.query(models.CommentLike.comment_id).filter(
            models.CommentLike.user_id == user.id, models.CommentLike.comment_id.in_([c.id for c in comments]))}
    ctx = feed.feed_context(db, user, [post])
    return render(request, db, "post.html", post=post, roots=roots, children=children, liked_comments=liked_comments,
                  comment_count=len(comments), **ctx)


@router.get("/post/{post_id}/stats")
def post_stats(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    post = _get_post(db, post_id)
    if not user or not post or (post.user_id != user.id and not social.can_mod(user)):
        return redirect("/")
    reposts = db.query(models.Post).filter(models.Post.repost_id == post.id).count()
    bookmarks = db.query(models.Bookmark).filter(models.Bookmark.post_id == post.id).count()
    reactions = dict(db.query(models.Reaction.emoji, func.count(models.Reaction.id)).filter(models.Reaction.post_id == post.id)
                     .group_by(models.Reaction.emoji).all())
    views = post.views or 0
    engagement = len(post.likes) + len(post.comments) + len(post.whales) + reposts + sum(reactions.values())
    rate = round(engagement / views * 100, 1) if views else 0
    likers = db.query(models.User).join(models.Like, models.Like.user_id == models.User.id).filter(models.Like.post_id == post.id).limit(30).all()
    return render(request, db, "post_stats.html", post=post, reposts=reposts, bookmarks=bookmarks, reactions=reactions,
                  views=views, engagement=engagement, rate=rate, likers=likers)


# --- Создание / редактирование / удаление ----------------------------------
@router.post("/post/create")
async def create_post(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401) if wants_json(request) else login_redirect(request)
    if social.is_active_block(user):
        return json_error("Аккаунт заблокирован", 403) if wants_json(request) else blocked_page(request, db, user)
    if social.needs_email(user):
        return json_error(social.VERIFY_MSG, 403)
    if not ratelimit.hit(f"post:{user.id}", 20, 600):
        return json_error("Слишком часто. Подождите немного.", 429)
    form = await request.form()
    content = (form.get("content") or "").strip()[:config.MAX_POST_LENGTH]
    files = [f for f in form.getlist("media") + form.getlist("image") + form.getlist("video") if is_upload(f)][:config.MAX_POST_MEDIA]
    poll_q = (form.get("poll_question") or "").strip()[:200]
    poll_opts = [o.strip()[:100] for o in form.getlist("poll_options") if isinstance(o, str) and o.strip()]
    for i in range(1, 7):
        v = (form.get(f"poll_option_{i}") or "").strip()
        if v:
            poll_opts.append(v[:100])
    if not content and not files and not (poll_q and len(poll_opts) >= 2):
        return json_error("Пост пустой")
    saved, errors = [], []
    for f in files:
        url, mt = save_file(f, allowed=("image", "video"))
        if url:
            saved.append((url, mt))
        else:
            errors.append(mt)
    if files and not saved:
        return json_error(errors[0] if errors else "Не удалось загрузить файл")
    content = censor(content, social.stop_words(db))
    scheduled = _parse_dt(form.get("scheduled_at"))
    if scheduled and scheduled <= datetime.utcnow():
        scheduled = None
    visibility = form.get("visibility") if form.get("visibility") in ("all", "followers") else "all"
    post = models.Post(content=content, user_id=user.id, image=saved[0][0] if saved else "", media_type=saved[0][1] if saved else "",
                       is_long=len(content) > 500, scheduled_at=scheduled, visibility=visibility,
                       comments_disabled=bool(form.get("comments_disabled")))
    db.add(post)
    db.flush()
    flag = moderation.review(db, "post", post, user, content)
    if len(saved) > 1:
        for i, (url, mt) in enumerate(saved):
            db.add(models.PostMedia(post_id=post.id, media_url=url, media_type=mt, position=i))
    if poll_q and len(poll_opts) >= 2:
        try:
            days = max(0, min(int(form.get("poll_days") or 0), 30))
        except ValueError:
            days = 0
        poll = models.Poll(post_id=post.id, question=poll_q, ends_at=datetime.utcnow() + timedelta(days=days) if days else None)
        db.add(poll)
        db.flush()
        for opt in poll_opts[:6]:
            db.add(models.PollOption(poll_id=poll.id, text=opt))
        gamification.check_achievement(user, db, "pollster")
    draft_id = form.get("draft_id")
    if draft_id and str(draft_id).isdigit():
        db.query(models.Draft).filter_by(id=int(draft_id), user_id=user.id).delete()
    update_trends(db, content)
    social.process_mentions(db, user, content, post.id)
    gamification.add_points(user, db, 5)
    db.commit()
    gamification.complete_task(user, db, "post")
    count = db.query(models.Post).filter(models.Post.user_id == user.id, models.Post.is_repost == False).count()
    for n, code in ((1, "first_post"), (10, "active"), (50, "prolific")):
        if count >= n:
            gamification.check_achievement(user, db, code)
    if saved and db.query(models.Post).filter(models.Post.user_id == user.id, models.Post.media_type == "image").count() >= 5:
        gamification.check_achievement(user, db, "photographer")
    if 0 <= datetime.now().hour < 5:
        gamification.check_achievement(user, db, "night_owl")
    db.commit()
    if wants_json(request):
        return JSONResponse({"ok": True, "post_id": post.id, "scheduled": bool(scheduled), "warnings": errors,
                             "held": bool(flag and flag.held),
                             "message": "Пост отправлен на проверку модераторам" if flag and flag.held else ""})
    return redirect(f"/post/{post.id}")


@router.post("/post/{post_id}/edit")
async def edit_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    post = _get_post(db, post_id)
    if not user or not post:
        return json_error("not found", 404)
    if post.user_id != user.id:
        return json_error("forbidden", 403)
    data = await read_payload(request)
    content = (data.get("content") or "").strip()[:config.MAX_POST_LENGTH]
    if not content and not post.image and not post.poll:
        return json_error("Пост не может быть пустым")
    update_trends(db, post.content or "", -1)
    post.content = censor(content, social.stop_words(db))
    post.is_long = len(post.content) > 500
    post.edited_at = datetime.utcnow()
    if "comments_disabled" in data:
        post.comments_disabled = bool(data.get("comments_disabled"))
    update_trends(db, post.content)
    moderation.review(db, "post", post, user, post.content)
    db.commit()
    return JSONResponse({"ok": True})


def purge_post(db, post):
    delete_file(post.image)
    for pm in post.media_items:
        delete_file(pm.media_url)
    update_trends(db, post.content or "", -1)
    pid = post.id
    poll_ids = [p.id for p in db.query(models.Poll.id).filter(models.Poll.post_id == pid)]
    if poll_ids:
        db.query(models.PollVote).filter(models.PollVote.poll_id.in_(poll_ids)).delete(synchronize_session=False)
        db.query(models.PollOption).filter(models.PollOption.poll_id.in_(poll_ids)).delete(synchronize_session=False)
        db.query(models.Poll).filter(models.Poll.id.in_(poll_ids)).delete(synchronize_session=False)
    cids = [c.id for c in db.query(models.Comment.id).filter(models.Comment.post_id == pid)]
    if cids:
        db.query(models.CommentLike).filter(models.CommentLike.comment_id.in_(cids)).delete(synchronize_session=False)
        db.query(models.Comment).filter(models.Comment.post_id == pid).update({"parent_id": None}, synchronize_session=False)
    for model in (models.Like, models.Whale, models.Comment, models.Notification, models.Reaction, models.Bookmark,
                  models.PostReport, models.PostMedia, models.ModerationFlag):
        db.query(model).filter(model.post_id == pid).delete(synchronize_session=False)
    db.query(models.User).filter(models.User.pinned_post_id == pid).update({"pinned_post_id": None}, synchronize_session=False)
    db.query(models.Post).filter(models.Post.id == pid).delete(synchronize_session=False)
    db.expunge(post)


@router.post("/post/{post_id}/delete")
async def delete_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    post = _get_post(db, post_id)
    if not post:
        return json_error("not found", 404)
    if post.user_id != user.id and not social.can_mod(user):
        return json_error("forbidden", 403)
    if post.user_id != user.id:
        from deps import log_mod
        log_mod(db, user, "delete_post", post.id, (post.content or "")[:200])
    purge_post(db, post)
    db.commit()
    if wants_json(request):
        return JSONResponse({"ok": True})
    return redirect("/")


# --- Реакции ------------------------------------------------------------------
def _toggle(db, model, user, post_id):
    ex = db.query(model).filter_by(user_id=user.id, post_id=post_id).first()
    if ex:
        db.delete(ex)
        return False
    db.add(model(user_id=user.id, post_id=post_id))
    db.flush()
    return True


def _check_access(db, user, post_id):
    post = _get_post(db, post_id)
    if not user:
        return None, json_error("auth", 401)
    if not social.can_view_post(db, user, post):
        return None, json_error("not found", 404)
    return post, None


@router.post("/like/{post_id}")
def like_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    post, err = _check_access(db, user, post_id)
    if err:
        return err
    liked = _toggle(db, models.Like, user, post_id)
    if liked:
        social.notify(db, post.user_id, "like", user, post_id)
        db.commit()
        gamification.complete_task(user, db, "like")
        n = db.query(models.Like).filter_by(user_id=user.id).count()
        if n >= 1:
            gamification.check_achievement(user, db, "first_like")
        if n >= 50:
            gamification.check_achievement(user, db, "liker")
    db.commit()
    return JSONResponse({"ok": True, "liked": liked, "count": db.query(models.Like).filter_by(post_id=post_id).count()})


@router.post("/whale/{post_id}")
def whale_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    post, err = _check_access(db, user, post_id)
    if err:
        return err
    whaled = _toggle(db, models.Whale, user, post_id)
    if whaled:
        social.notify(db, post.user_id, "whale", user, post_id)
        if db.query(models.Whale).filter_by(user_id=user.id).count() >= 10:
            gamification.check_achievement(user, db, "whale")
    db.commit()
    return JSONResponse({"ok": True, "whaled": whaled, "count": db.query(models.Whale).filter_by(post_id=post_id).count()})


@router.post("/bookmark/{post_id}")
def bookmark_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    _, err = _check_access(db, user, post_id)
    if err:
        return err
    bm = _toggle(db, models.Bookmark, user, post_id)
    db.commit()
    return JSONResponse({"ok": True, "bookmarked": bm})


@router.post("/post/{post_id}/react")
async def react_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    post, err = _check_access(db, user, post_id)
    if err:
        return err
    data = await read_payload(request)
    emoji = data.get("emoji", "")
    if emoji not in REACTIONS:
        return json_error("bad emoji")
    ex = db.query(models.Reaction).filter_by(user_id=user.id, post_id=post_id).first()
    mine = emoji
    if ex and ex.emoji == emoji:
        db.delete(ex)
        mine = None
    elif ex:
        ex.emoji = emoji
    else:
        db.add(models.Reaction(user_id=user.id, post_id=post_id, emoji=emoji))
        social.notify(db, post.user_id, "reaction", user, post_id, text=f"отреагировал(а) {emoji} на ваш пост")
    db.commit()
    counts = dict(db.query(models.Reaction.emoji, func.count(models.Reaction.id)).filter(models.Reaction.post_id == post_id)
                  .group_by(models.Reaction.emoji).all())
    return JSONResponse({"ok": True, "mine": mine, "counts": counts})


@router.get("/api/post/{post_id}/likers")
def post_likers(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    post = _get_post(db, post_id)
    if not social.can_view_post(db, user, post):
        return json_error("not found", 404)
    if post.author.hide_likes and (not user or user.id != post.user_id):
        return JSONResponse({"ok": True, "users": [], "hidden": True})
    users = db.query(models.User).join(models.Like, models.Like.user_id == models.User.id).filter(models.Like.post_id == post_id).limit(100).all()
    return JSONResponse({"ok": True, "users": [{"username": u.username, "name": u.name or u.username, "avatar": u.avatar or ""} for u in users]})


# --- Комментарии --------------------------------------------------------------
@router.post("/post/{post_id}/comment")
async def add_comment(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    post, err = _check_access(db, user, post_id)
    if err:
        return err if wants_json(request) else login_redirect(request)
    if social.is_active_block(user):
        return json_error("Аккаунт заблокирован", 403)
    if social.needs_email(user):
        return json_error(social.VERIFY_MSG, 403)
    if post.comments_disabled and post.user_id != user.id:
        return json_error("Автор отключил комментарии", 403)
    if not prefs.audience_allows(db, post.author, user, "who_can_comment"):
        return json_error("Автор ограничил, кто может комментировать", 403)
    if not ratelimit.hit(f"comment:{user.id}", 30, 300):
        return json_error("Слишком часто", 429)
    data = await read_payload(request)
    content = censor((data.get("content") or "").strip()[:2000], social.stop_words(db))
    if not content:
        return json_error("Пустой комментарий")
    parent = None
    pid = data.get("parent_id")
    if pid and str(pid).isdigit():
        parent = db.get(models.Comment, int(pid))
        if not parent or parent.post_id != post_id:
            parent = None
    c = models.Comment(content=content, user_id=user.id, post_id=post_id, parent_id=parent.id if parent else None)
    db.add(c)
    db.flush()
    moderation.review(db, "comment", c, user, content)
    social.notify(db, post.user_id, "comment", user, post_id)
    if parent and parent.user_id not in (user.id, post.user_id):
        social.notify(db, parent.user_id, "reply", user, post_id)
    social.process_mentions(db, user, content, post_id)
    gamification.add_points(user, db, 2)
    db.commit()
    gamification.complete_task(user, db, "comment")
    if db.query(models.Comment).filter_by(user_id=user.id).count() >= 20:
        gamification.check_achievement(user, db, "social")
        db.commit()
    if wants_json(request):
        return JSONResponse({"ok": True, "id": c.id})
    return redirect(f"/post/{post_id}#comment-{c.id}")


@router.post("/comment/{comment_id}/delete")
def delete_comment(comment_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    c = db.get(models.Comment, comment_id)
    if not c:
        return json_error("not found", 404)
    post = _get_post(db, c.post_id)
    if c.user_id != user.id and not social.can_mod(user) and not (post and post.user_id == user.id):
        return json_error("forbidden", 403)
    ids = [c.id]
    frontier = [c.id]
    while frontier:
        kids = [k.id for k in db.query(models.Comment.id).filter(models.Comment.parent_id.in_(frontier))]
        ids += kids
        frontier = kids
    db.query(models.CommentLike).filter(models.CommentLike.comment_id.in_(ids)).delete(synchronize_session=False)
    db.query(models.Comment).filter(models.Comment.id.in_(ids)).update({"parent_id": None}, synchronize_session=False)
    db.query(models.Comment).filter(models.Comment.id.in_(ids)).delete(synchronize_session=False)
    if post and post.pinned_comment_id in ids:
        post.pinned_comment_id = None
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/comment/{comment_id}/like")
def like_comment(comment_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    c = db.get(models.Comment, comment_id)
    if not c or not social.can_view_post(db, user, _get_post(db, c.post_id)):
        return json_error("not found", 404)
    ex = db.query(models.CommentLike).filter_by(comment_id=comment_id, user_id=user.id).first()
    if ex:
        db.delete(ex)
        liked = False
    else:
        db.add(models.CommentLike(comment_id=comment_id, user_id=user.id))
        social.notify(db, c.user_id, "comment_like", user, c.post_id)
        liked = True
    db.commit()
    return JSONResponse({"ok": True, "liked": liked, "count": db.query(models.CommentLike).filter_by(comment_id=comment_id).count()})


@router.post("/post/{post_id}/pin-comment/{comment_id}")
def pin_comment(post_id: int, comment_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    post = _get_post(db, post_id)
    if not user or not post or (post.user_id != user.id and not social.can_mod(user)):
        return json_error("forbidden", 403)
    c = db.get(models.Comment, comment_id)
    if not c or c.post_id != post_id:
        return json_error("not found", 404)
    pin = not c.is_pinned
    db.query(models.Comment).filter_by(post_id=post_id).update({"is_pinned": False})
    c.is_pinned = pin
    post.pinned_comment_id = comment_id if pin else None
    db.commit()
    return JSONResponse({"ok": True, "pinned": pin})


# --- Опросы, репосты, закреп, жалобы ----------------------------------------
@router.post("/poll/vote/{option_id}")
def poll_vote(option_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401) if wants_json(request) else login_redirect(request)
    opt = db.get(models.PollOption, option_id)
    if not opt:
        return json_error("not found", 404)
    poll = opt.poll
    if not social.can_view_post(db, user, poll.post):
        return json_error("not found", 404)
    if poll.ends_at and poll.ends_at < datetime.utcnow():
        return json_error("Опрос завершён")
    if not db.query(models.PollVote).filter_by(user_id=user.id, poll_id=opt.poll_id).first():
        db.add(models.PollVote(user_id=user.id, option_id=option_id, poll_id=opt.poll_id))
        db.commit()
    if wants_json(request):
        db.refresh(poll)
        total = sum(len(o.votes) for o in poll.options)
        return JSONResponse({"ok": True, "total": total, "options": [{"id": o.id, "votes": len(o.votes)} for o in poll.options]})
    return redirect(f"/post/{poll.post_id}")


@router.post("/post/{post_id}/not-interested")
def not_interested(post_id: int, request: Request, db: Session = Depends(get_db)):
    from services import recommend
    user = current_user(request, db)
    post = _get_post(db, post_id)
    if not user or not post:
        return json_error("not found", 404)
    if not db.query(models.NotInterested).filter_by(user_id=user.id, post_id=post_id).first():
        db.add(models.NotInterested(user_id=user.id, post_id=post_id, author_id=post.user_id))
        db.commit()
    recommend.invalidate(user.id)
    return JSONResponse({"ok": True})


@router.post("/repost/{post_id}")
async def repost(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    orig, err = _check_access(db, user, post_id)
    if err:
        return err
    if orig.is_repost and orig.repost_id:
        orig = _get_post(db, orig.repost_id) or orig
    if orig.user_id != user.id and not prefs.get(orig.author, "allow_reposts"):
        return json_error("Автор запретил репосты своих постов", 403)
    data = await read_payload(request)
    comment = censor((data.get("comment") or "").strip()[:1000], social.stop_words(db))
    existing = db.query(models.Post).filter_by(user_id=user.id, is_repost=True, repost_id=orig.id).first()
    if existing and not comment:
        purge_post(db, existing)
        db.commit()
        return JSONResponse({"ok": True, "reposted": False, "count": db.query(models.Post).filter_by(repost_id=orig.id).count()})
    p = models.Post(content=orig.content, user_id=user.id, image="", media_type="", is_repost=True, repost_id=orig.id,
                    original_comment=comment)
    db.add(p)
    db.flush()
    moderation.review(db, "post", p, user, comment)
    social.notify(db, orig.user_id, "repost", user, orig.id)
    if comment:
        social.process_mentions(db, user, comment, p.id)
    db.commit()
    return JSONResponse({"ok": True, "reposted": True, "count": db.query(models.Post).filter_by(repost_id=orig.id).count()})


@router.post("/post/{post_id}/pin")
def pin_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    post = db.query(models.Post).filter_by(id=post_id, user_id=user.id).first()
    if not post:
        return json_error("not found", 404)
    user.pinned_post_id = None if user.pinned_post_id == post_id else post_id
    db.commit()
    return JSONResponse({"ok": True, "pinned": user.pinned_post_id == post_id})


@router.post("/post/{post_id}/report")
async def report_post(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    _, err = _check_access(db, user, post_id)
    if err:
        return err
    data = await read_payload(request)
    if not db.query(models.PostReport).filter_by(reporter_id=user.id, post_id=post_id, status="new").first():
        db.add(models.PostReport(reporter_id=user.id, post_id=post_id, reason=(data.get("reason") or "")[:300]))
        db.commit()
    return JSONResponse({"ok": True})


# --- Закладки, черновики, отложенные -----------------------------------------
@router.get("/bookmarks")
def bookmarks_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    bms = db.query(models.Bookmark).filter_by(user_id=user.id).order_by(models.Bookmark.created_at.desc()).limit(200).all()
    posts = [b.post for b in bms if b.post and social.can_view_post(db, user, b.post)]
    return render(request, db, "bookmarks.html", **feed.feed_context(db, user, posts))


@router.post("/drafts/save")
async def save_draft(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    data = await read_payload(request)
    content = (data.get("content") or "").strip()[:config.MAX_POST_LENGTH]
    if not content:
        return json_error("Черновик пустой")
    did = data.get("draft_id")
    d = db.query(models.Draft).filter_by(id=int(did), user_id=user.id).first() if did and str(did).isdigit() else None
    if d:
        d.content, d.updated_at = content, datetime.utcnow()
    else:
        if db.query(models.Draft).filter_by(user_id=user.id).count() >= 50:
            return json_error("Слишком много черновиков")
        d = models.Draft(user_id=user.id, content=content)
        db.add(d)
    db.commit()
    return JSONResponse({"ok": True, "id": d.id})


@router.get("/drafts")
def drafts_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    drafts = db.query(models.Draft).filter_by(user_id=user.id).order_by(models.Draft.updated_at.desc()).all()
    scheduled = (db.query(models.Post).filter(models.Post.user_id == user.id, models.Post.scheduled_at > datetime.utcnow())
                 .order_by(models.Post.scheduled_at.asc()).all())
    return render(request, db, "drafts.html", drafts=drafts, scheduled=scheduled)


@router.post("/drafts/{draft_id}/delete")
def delete_draft(draft_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    db.query(models.Draft).filter_by(id=draft_id, user_id=user.id).delete()
    db.commit()
    if wants_json(request):
        return JSONResponse({"ok": True})
    return redirect("/drafts")


@router.post("/post/{post_id}/publish-now")
def publish_now(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    post = _get_post(db, post_id)
    if not user or not post or post.user_id != user.id:
        return json_error("forbidden", 403)
    post.scheduled_at = None
    post.created_at = datetime.utcnow()
    db.commit()
    return redirect(f"/post/{post_id}")
