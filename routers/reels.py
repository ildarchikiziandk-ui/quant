from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import current_user, json_error, redirect, render
from routers.posts import read_payload, wants_json
from services import gamification, ratelimit, social
from services.text import censor, timeago
from services.uploads import delete_file, save_file

router = APIRouter()


def _visible_reels(db, user):
    hidden = social.blocked_ids(db, user)
    reels = db.query(models.Reel).order_by(models.Reel.created_at.desc()).limit(100).all()
    return [r for r in reels if r.author and r.user_id not in hidden and social.can_see_content(db, user, r.author)]


@router.get("/reels")
def reels_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    reels = _visible_reels(db, user)
    liked = set()
    if user:
        liked = {r.reel_id for r in db.query(models.ReelLike.reel_id).filter(models.ReelLike.user_id == user.id)}
    return render(request, db, "reels.html", sidebar=False, reels=reels, liked_reels=liked)


@router.get("/reels/{reel_id}")
def reel_single(reel_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    r = db.get(models.Reel, reel_id)
    if not r or not r.author or not social.can_see_content(db, user, r.author):
        return redirect("/reels")
    others = [x for x in _visible_reels(db, user) if x.id != r.id]
    liked = set()
    if user:
        liked = {x.reel_id for x in db.query(models.ReelLike.reel_id).filter(models.ReelLike.user_id == user.id)}
    return render(request, db, "reels.html", sidebar=False, reels=[r] + others, liked_reels=liked)


@router.post("/reels/upload")
async def upload_reel(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    if social.is_active_block(user):
        return json_error("Аккаунт заблокирован", 403)
    if not ratelimit.hit(f"reel:{user.id}", 10, 3600):
        return json_error("Слишком много загрузок", 429)
    form = await request.form()
    url, mtype = save_file(form.get("video"), allowed=("video",))
    if not url:
        return json_error(mtype)
    reel = models.Reel(user_id=user.id, video_url=url, caption=censor((form.get("caption") or "").strip()[:500], social.stop_words(db)))
    db.add(reel)
    gamification.add_points(user, db, 10)
    gamification.check_achievement(user, db, "videographer")
    db.commit()
    if wants_json(request):
        return JSONResponse({"ok": True, "id": reel.id})
    return redirect(f"/reels/{reel.id}")


@router.post("/reels/{reel_id}/like")
@router.post("/reels/like/{reel_id}")
def like_reel(reel_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    r = db.get(models.Reel, reel_id)
    if not user or not r:
        return json_error("not found", 404)
    ex = db.query(models.ReelLike).filter_by(user_id=user.id, reel_id=reel_id).first()
    if ex:
        db.delete(ex)
    else:
        db.add(models.ReelLike(user_id=user.id, reel_id=reel_id))
        social.notify(db, r.user_id, "like", user, text="оценил(а) ваш рилс", url=f"/reels/{reel_id}")
    db.commit()
    return JSONResponse({"ok": True, "liked": not ex, "count": db.query(models.ReelLike).filter_by(reel_id=reel_id).count()})


@router.post("/reels/{reel_id}/view")
def view_reel(reel_id: int, db: Session = Depends(get_db)):
    r = db.get(models.Reel, reel_id)
    if r:
        r.views = (r.views or 0) + 1
        db.commit()
    return JSONResponse({"ok": True})


@router.get("/reels/{reel_id}/comments")
def reel_comments(reel_id: int, request: Request, db: Session = Depends(get_db)):
    comments = db.query(models.ReelComment).filter_by(reel_id=reel_id).order_by(models.ReelComment.created_at.asc()).limit(200).all()
    return JSONResponse({"ok": True, "comments": [{"id": c.id, "username": c.author.username if c.author else "?",
                                                    "name": (c.author.name or c.author.username) if c.author else "?",
                                                    "content": c.content, "ago": timeago(c.created_at)} for c in comments]})


@router.post("/reels/{reel_id}/comment")
@router.post("/reels/comment/{reel_id}")
async def comment_reel(reel_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    r = db.get(models.Reel, reel_id)
    if not user or not r:
        return json_error("not found", 404)
    if not ratelimit.hit(f"rc:{user.id}", 20, 300):
        return json_error("Слишком часто", 429)
    data = await read_payload(request)
    content = censor((data.get("content") or "").strip()[:1000], social.stop_words(db))
    if not content:
        return json_error("Пустой комментарий")
    db.add(models.ReelComment(user_id=user.id, reel_id=reel_id, content=content))
    social.notify(db, r.user_id, "comment", user, text="прокомментировал(а) ваш рилс", url=f"/reels/{reel_id}")
    db.commit()
    if wants_json(request):
        return JSONResponse({"ok": True})
    return redirect(f"/reels/{reel_id}")


@router.post("/reels/{reel_id}/delete")
def delete_reel(reel_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    r = db.get(models.Reel, reel_id)
    if not user or not r or (r.user_id != user.id and not social.can_mod(user)):
        return json_error("forbidden", 403)
    delete_file(r.video_url)
    db.query(models.ReelLike).filter_by(reel_id=reel_id).delete()
    db.query(models.ReelComment).filter_by(reel_id=reel_id).delete()
    db.delete(r)
    db.commit()
    return JSONResponse({"ok": True})
