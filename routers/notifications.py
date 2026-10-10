from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import current_user, json_error, login_redirect, redirect, render
from routers.posts import wants_json

router = APIRouter()

FILTERS = {
    "all": None,
    "mentions": ("mention",),
    "likes": ("like", "whale", "reaction", "comment_like", "repost", "story_reaction"),
    "comments": ("comment", "reply"),
    "follows": ("follow", "follow_request", "follow_accept"),
    "system": ("system", "achievement", "level", "raffle", "support", "support_reply", "group_invite", "moderation"),
}


@router.get("/notifications")
def notifs_page(request: Request, f: str = "all", db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    q = db.query(models.Notification).filter(models.Notification.user_id == user.id, models.Notification.type != "promo")
    types = FILTERS.get(f)
    if types:
        q = q.filter(models.Notification.type.in_(types))
    notifs = q.order_by(models.Notification.created_at.desc()).limit(150).all()
    unread_ids = {n.id for n in notifs if not n.is_read}
    if unread_ids:
        db.query(models.Notification).filter(models.Notification.id.in_(unread_ids)).update({"is_read": True}, synchronize_session=False)
        db.commit()
    requests_count = db.query(models.FollowRequest).filter_by(target_id=user.id).count()
    return render(request, db, "notifications.html", notifications=notifs, unread_ids=unread_ids, f=f if f in FILTERS else "all",
                  requests_count=requests_count, filters=FILTERS)


@router.post("/notifications/read-all")
@router.post("/notifications/read")
def notifs_read_all(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    db.query(models.Notification).filter_by(user_id=user.id, is_read=False).update({"is_read": True})
    db.commit()
    if wants_json(request):
        return JSONResponse({"ok": True})
    return redirect("/notifications")


@router.post("/notifications/clear")
def notifs_clear(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    db.query(models.Notification).filter(models.Notification.user_id == user.id, models.Notification.type != "promo").delete(synchronize_session=False)
    db.commit()
    return redirect("/notifications")


@router.post("/notifications/{notif_id}/read")
def notif_read(notif_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    n = db.query(models.Notification).filter_by(id=notif_id, user_id=user.id).first()
    if n:
        n.is_read = True
        db.commit()
    return JSONResponse({"ok": True})


@router.post("/notifications/{notif_id}/delete")
def notif_delete(notif_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    db.query(models.Notification).filter_by(id=notif_id, user_id=user.id).delete()
    db.commit()
    return JSONResponse({"ok": True})
