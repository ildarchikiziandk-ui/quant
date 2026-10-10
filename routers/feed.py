from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import current_user, render, templates
from services import feed, social

router = APIRouter()

TABS = ("foryou", "following", "latest", "media")


def _stories_strip(db, user):
    from routers.stories import story_groups
    return story_groups(db, user)


@router.get("/")
def home(request: Request, tab: str = "foryou", db: Session = Depends(get_db)):
    user = current_user(request, db)
    tab = tab if tab in TABS else "foryou"
    if tab == "following" and not user:
        tab = "foryou"
    posts, has_more = feed.get_feed(db, user, tab, 1)
    drafts = []
    if user:
        drafts = db.query(models.Draft).filter_by(user_id=user.id).order_by(models.Draft.updated_at.desc()).limit(5).all()
    return render(request, db, "home.html", tab=tab, has_more=has_more, page=1, drafts=drafts,
                  story_groups=_stories_strip(db, user), **feed.feed_context(db, user, posts))


@router.get("/feed/more")
def feed_more(request: Request, tab: str = "foryou", page: int = 2, db: Session = Depends(get_db)):
    user = current_user(request, db)
    page = max(1, min(page, 200))
    posts, has_more = feed.get_feed(db, user, tab if tab in TABS else "foryou", page)
    ctx = {"request": request, "user": user, "can_mod": social.can_mod(user), "has_more": has_more, "page": page,
           "more_url": f"/feed/more?tab={tab}&page={page + 1}"}
    ctx.update(feed.feed_context(db, user, posts))
    return templates.TemplateResponse(request, "partials/post_list.html", ctx)


@router.get("/welcome")
def welcome(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return render(request, db, "landing.html", sidebar=False)
    popular = (db.query(models.User).filter(models.User.id != user.id, models.User.is_blocked == False)
               .order_by(models.User.total_points.desc()).limit(12).all())
    return render(request, db, "welcome.html", popular=popular, following=social.following_ids(db, user))
