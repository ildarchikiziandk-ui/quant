from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import current_user, json_error, login_redirect, redirect, render
from routers.posts import wants_json
from services import feed, gamification, social
from services.uploads import save_file

router = APIRouter()


def _get_user(db, username):
    return db.query(models.User).filter(func.lower(models.User.username) == username.lower().lstrip("@")).first()


@router.get("/profile/{username}")
def profile(username: str, request: Request, tab: str = "posts", db: Session = Depends(get_db)):
    user = current_user(request, db)
    pu = _get_user(db, username)
    if not pu:
        return render(request, db, "error.html", status_code=404, code=404, title="Пользователь не найден",
                      text=f"Аккаунта @{username} не существует.")
    if pu.username != username:
        return redirect(f"/profile/{pu.username}", 301)
    blocked_me = user and db.query(models.UserBlock).filter_by(blocker_id=pu.id, blocked_id=user.id).first() is not None
    i_blocked = user and db.query(models.UserBlock).filter_by(blocker_id=user.id, blocked_id=pu.id).first() is not None
    can_see = social.can_see_content(db, user, pu)
    if user and user.id != pu.id:
        pu.profile_views = (pu.profile_views or 0) + 1
        db.commit()
    q = social.visible_posts(db, user, hide_muted=False).filter(models.Post.user_id == pu.id)
    posts, reels, liked_posts = [], [], []
    if can_see:
        if tab == "media":
            posts = feed.with_loads(q.filter(models.Post.image != "", models.Post.image != None)).order_by(models.Post.created_at.desc()).limit(60).all()
        elif tab == "likes":
            if pu.hide_likes and (not user or user.id != pu.id):
                posts = []
            else:
                liked_ids = [lk.post_id for lk in db.query(models.Like.post_id).filter(models.Like.user_id == pu.id).order_by(models.Like.id.desc()).limit(60)]
                posts = feed.with_loads(social.visible_posts(db, user, hide_muted=False)).filter(models.Post.id.in_(liked_ids or [-1])).all()
                order = {pid: i for i, pid in enumerate(liked_ids)}
                posts.sort(key=lambda p: order.get(p.id, 0))
        elif tab == "reels":
            reels = db.query(models.Reel).filter_by(user_id=pu.id).order_by(models.Reel.created_at.desc()).all()
        elif tab == "replies":
            liked_posts = (db.query(models.Comment).filter_by(user_id=pu.id).order_by(models.Comment.created_at.desc()).limit(50).all())
            liked_posts = [c for c in liked_posts if social.can_view_post(db, user, c.post)]
        else:
            tab = "posts"
            posts = feed.with_loads(q).order_by(models.Post.created_at.desc()).limit(100).all()
    pinned = None
    if can_see and pu.pinned_post_id and tab == "posts":
        pinned = db.get(models.Post, pu.pinned_post_id)
        if pinned and social.can_view_post(db, user, pinned):
            posts = [p for p in posts if p.id != pinned.id]
        else:
            pinned = None
    stats = {"posts": db.query(models.Post).filter_by(user_id=pu.id, is_draft=False).count(),
             "followers": db.query(models.Follow).filter_by(following_id=pu.id).count(),
             "following": db.query(models.Follow).filter_by(follower_id=pu.id).count(),
             "likes": db.query(models.Like).join(models.Post, models.Post.id == models.Like.post_id).filter(models.Post.user_id == pu.id).count()}
    if user and user.id == pu.id:
        stats["views"] = db.query(func.coalesce(func.sum(models.Post.views), 0)).filter(models.Post.user_id == pu.id).scalar()
        stats["profile_views"] = pu.profile_views or 0
    rel = {"is_following": social.is_following(db, user, pu), "follows_me": social.is_following(db, pu, user),
           "requested": bool(user and db.query(models.FollowRequest).filter_by(requester_id=user.id, target_id=pu.id).first()),
           "is_muted": bool(user and db.query(models.UserMute).filter_by(user_id=user.id, muted_id=pu.id).first()),
           "is_close": bool(user and db.query(models.CloseFriend).filter_by(user_id=user.id, friend_id=pu.id).first()),
           "i_blocked": bool(i_blocked), "blocked_me": bool(blocked_me)}
    mutual = []
    if user and user.id != pu.id:
        mine = social.following_ids(db, user)
        mutual_ids = [f.follower_id for f in db.query(models.Follow.follower_id).filter(models.Follow.following_id == pu.id)
                      if f.follower_id in mine][:3]
        mutual = db.query(models.User).filter(models.User.id.in_(mutual_ids or [-1])).all()
    achievements = db.query(models.UserAchievement).filter_by(user_id=pu.id).all()
    highlights = db.query(models.StoryHighlight).filter_by(user_id=pu.id).order_by(models.StoryHighlight.created_at.desc()).all() if can_see else []
    has_story = db.query(models.Story.id).filter(models.Story.user_id == pu.id, models.Story.expires_at > datetime.utcnow()).first() is not None if can_see else False
    ctx = feed.feed_context(db, user, ([pinned] if pinned else []) + posts)
    ctx["posts"] = posts
    return render(request, db, "profile.html", profile_user=pu, tab=tab, can_see=can_see, pinned_post=pinned, reels=reels,
                  replies=liked_posts, stats=stats, rel=rel, mutual=mutual, achievements=achievements, highlights=highlights,
                  has_story=has_story, level=gamification.level_progress(pu), profile_is_plus=social.is_plus(pu), **ctx)


def _people_page(request, db, username, kind):
    user = current_user(request, db)
    pu = _get_user(db, username)
    if not pu:
        return redirect("/")
    if not social.can_see_content(db, user, pu):
        return redirect(f"/profile/{pu.username}")
    if kind == "followers":
        people = [f.follower for f in db.query(models.Follow).filter_by(following_id=pu.id).order_by(models.Follow.id.desc()).limit(500) if f.follower]
    else:
        people = [f.following for f in db.query(models.Follow).filter_by(follower_id=pu.id).order_by(models.Follow.id.desc()).limit(500) if f.following]
    return render(request, db, "people.html", profile_user=pu, people=people, kind=kind, following=social.following_ids(db, user))


@router.get("/profile/{username}/followers")
def followers_page(username: str, request: Request, db: Session = Depends(get_db)):
    return _people_page(request, db, username, "followers")


@router.get("/profile/{username}/following")
def following_page(username: str, request: Request, db: Session = Depends(get_db)):
    return _people_page(request, db, username, "following")


@router.get("/followers/{username}")
def followers_legacy(username: str):
    return redirect(f"/profile/{username}/followers", 301)


@router.get("/following/{username}")
def following_legacy(username: str):
    return redirect(f"/profile/{username}/following", 301)


def _accept_follow(db, requester, target):
    if not db.query(models.Follow).filter_by(follower_id=requester.id, following_id=target.id).first():
        db.add(models.Follow(follower_id=requester.id, following_id=target.id))
        db.flush()
    gamification.complete_task(requester, db, "follow")
    gamification.check_achievement(requester, db, "first_follow")
    tc = db.query(models.Follow).filter_by(following_id=target.id).count()
    if tc >= 10:
        gamification.check_achievement(target, db, "popular")
    if tc >= 100:
        gamification.check_achievement(target, db, "very_popular")


@router.post("/follow/{username}")
def follow(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401) if wants_json(request) else login_redirect(request)
    target = _get_user(db, username)
    if not target or target.id == user.id or social.is_blocked_between(db, user, target):
        return json_error("Недоступно", 404) if wants_json(request) else redirect("/")
    ex = db.query(models.Follow).filter_by(follower_id=user.id, following_id=target.id).first()
    req = db.query(models.FollowRequest).filter_by(requester_id=user.id, target_id=target.id).first()
    state = "none"
    if ex:
        db.delete(ex)
    elif req:
        db.delete(req)
    elif target.is_private:
        db.add(models.FollowRequest(requester_id=user.id, target_id=target.id))
        social.notify(db, target.id, "follow_request", user)
        state = "requested"
    else:
        _accept_follow(db, user, target)
        social.notify(db, target.id, "follow", user)
        state = "following"
    db.commit()
    if wants_json(request):
        return JSONResponse({"ok": True, "state": state, "followers": db.query(models.Follow).filter_by(following_id=target.id).count()})
    return redirect(request.headers.get("referer") or f"/profile/{target.username}")


@router.post("/follower/{username}/remove")
def remove_follower(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    target = _get_user(db, username)
    if user and target:
        db.query(models.Follow).filter_by(follower_id=target.id, following_id=user.id).delete()
        db.commit()
    return JSONResponse({"ok": True})


@router.get("/follow-requests")
def follow_requests_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    reqs = db.query(models.FollowRequest).filter_by(target_id=user.id).order_by(models.FollowRequest.created_at.desc()).all()
    return render(request, db, "follow_requests.html", requests=reqs)


@router.post("/follow-requests/{req_id}/{action}")
def follow_request_action(req_id: int, action: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    req = db.query(models.FollowRequest).filter_by(id=req_id, target_id=user.id).first()
    if req:
        if action == "accept" and req.requester:
            _accept_follow(db, req.requester, user)
            social.notify(db, req.requester_id, "follow_accept", user)
        db.delete(req)
        db.commit()
    if wants_json(request):
        return JSONResponse({"ok": True})
    return redirect("/follow-requests")


def _toggle_rel(db, model, user, target, field):
    ex = db.query(model).filter(model.user_id == user.id if hasattr(model, "user_id") else model.blocker_id == user.id,
                                getattr(model, field) == target.id).first()
    if ex:
        db.delete(ex)
        return False
    kwargs = {field: target.id}
    kwargs["user_id" if hasattr(model, "user_id") else "blocker_id"] = user.id
    db.add(model(**kwargs))
    return True


@router.post("/block/{username}")
@router.post("/block_user/{username}")
def block_user(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    target = _get_user(db, username)
    if not user or not target or target.id == user.id:
        return json_error("bad request")
    blocked = _toggle_rel(db, models.UserBlock, user, target, "blocked_id")
    if blocked:
        db.query(models.Follow).filter(((models.Follow.follower_id == user.id) & (models.Follow.following_id == target.id)) |
                                       ((models.Follow.follower_id == target.id) & (models.Follow.following_id == user.id))).delete(synchronize_session=False)
        db.query(models.FollowRequest).filter(((models.FollowRequest.requester_id == user.id) & (models.FollowRequest.target_id == target.id)) |
                                              ((models.FollowRequest.requester_id == target.id) & (models.FollowRequest.target_id == user.id))).delete(synchronize_session=False)
    db.commit()
    if wants_json(request):
        return JSONResponse({"ok": True, "blocked": blocked})
    return redirect(request.headers.get("referer") or f"/profile/{target.username}")


@router.post("/unblock/{username}")
def unblock_user(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    target = _get_user(db, username)
    if user and target:
        db.query(models.UserBlock).filter_by(blocker_id=user.id, blocked_id=target.id).delete()
        db.commit()
    if wants_json(request):
        return JSONResponse({"ok": True})
    return redirect(request.headers.get("referer") or "/settings/privacy")


@router.post("/mute/{username}")
def mute_user(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    target = _get_user(db, username)
    if not user or not target or target.id == user.id:
        return json_error("bad request")
    muted = _toggle_rel(db, models.UserMute, user, target, "muted_id")
    db.commit()
    return JSONResponse({"ok": True, "muted": muted})


@router.post("/close-friends/{username}")
def close_friend(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    target = _get_user(db, username)
    if not user or not target or target.id == user.id:
        return json_error("bad request")
    added = _toggle_rel(db, models.CloseFriend, user, target, "friend_id")
    db.commit()
    return JSONResponse({"ok": True, "close": added})


@router.get("/close-friends")
def close_friends_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    friends = [c.friend for c in db.query(models.CloseFriend).filter_by(user_id=user.id).all() if c.friend]
    followers = [f.follower for f in db.query(models.Follow).filter_by(following_id=user.id).limit(300) if f.follower]
    close_ids = {f.id for f in friends}
    return render(request, db, "close_friends.html", friends=friends, candidates=[u for u in followers if u.id not in close_ids])


@router.get("/qr/{username}")
@router.get("/profile/{username}/qr")
def qr_page(username: str, request: Request, db: Session = Depends(get_db)):
    pu = _get_user(db, username)
    if not pu:
        return redirect("/")
    return render(request, db, "qr.html", profile_user=pu)


@router.get("/qr-code/{username}.svg")
def qr_svg(username: str, db: Session = Depends(get_db)):
    import io
    import qrcode
    import qrcode.image.svg
    from fastapi.responses import Response
    import config
    pu = _get_user(db, username)
    if not pu:
        return redirect("/")
    img = qrcode.make(f"{config.SITE_URL}/profile/{pu.username}", image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=1)
    buf = io.BytesIO()
    img.save(buf)
    return Response(buf.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/report/{username}")
def report_page(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    target = _get_user(db, username)
    if not target or target.id == user.id:
        return redirect("/")
    return render(request, db, "report.html", target=target)


@router.post("/report/{username}")
async def report_submit(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    target = _get_user(db, username)
    if not target or target.id == user.id:
        return redirect("/")
    form = await request.form()
    r = models.Report(reporter_id=user.id, target_id=target.id, reason=(form.get("reason") or "")[:100],
                      text=(form.get("text") or "")[:3000])
    imgs = [f for f in form.getlist("images") if hasattr(f, "filename") and f.filename][:5]
    for i, f in enumerate(imgs, 1):
        url, _ = save_file(f, allowed=("image",))
        if url:
            setattr(r, f"image_{i}", url)
    db.add(r)
    db.commit()
    return render(request, db, "report.html", target=target, success=True)
