from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import current_user, login_redirect, redirect, render, templates
from services import feed, prefs, recommend, social

router = APIRouter()

TABS = ("foryou", "following")


def _stories_strip(db, user):
    from routers.stories import story_groups
    return story_groups(db, user)


@router.get("/")
def home(request: Request, tab: str = "", db: Session = Depends(get_db)):
    user = current_user(request, db)
    from packs.v3.accounts import posts_locked
    if posts_locked(user):  # аккаунт «только чаты и профиль» — ленты нет, сразу в переписку
        return redirect("/messages")
    if not tab and user:
        tab = prefs.get(user, "feed_default_tab")
    tab = tab if tab in TABS else "foryou"
    if tab == "following" and not user:
        tab = "foryou"
    posts, has_more, reasons = feed.get_feed(db, user, tab, 1)
    from services import extras
    resp = render(request, db, "home.html", tab=tab, has_more=has_more, page=1, memories_n=len(extras.memories(db, user)) if user else 0,
                  story_groups=_stories_strip(db, user), **feed.feed_context(db, user, posts, reasons))
    if tab == "foryou":  # после отрисовки: commit сбросил бы уже загруженные посты и страница грузила бы их заново по одному
        recommend.mark_seen(db, user, posts)
    return resp


@router.get("/create")
def create_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    from packs.v3.accounts import posts_locked
    if posts_locked(user):
        return render(request, db, "error.html", status_code=403, code=403, title="Публикация недоступна",
                      text="Для вашего аккаунта публикация постов отключена. Переписка, профиль и остальные функции работают как обычно.")
    drafts = db.query(models.Draft).filter_by(user_id=user.id).order_by(models.Draft.updated_at.desc()).limit(8).all()
    return render(request, db, "create.html", drafts=drafts)


@router.get("/feed/more")
def feed_more(request: Request, tab: str = "foryou", page: int = 2, db: Session = Depends(get_db)):
    user = current_user(request, db)
    page = max(1, min(page, 200))
    tab = tab if tab in TABS else "foryou"
    posts, has_more, reasons = feed.get_feed(db, user, tab, page)
    ctx = {"request": request, "user": user, "can_mod": social.can_mod(user), "has_more": has_more, "page": page,
           "more_url": f"/feed/more?tab={tab}&page={page + 1}"}
    ctx.update(feed.feed_context(db, user, posts, reasons))
    resp = templates.TemplateResponse(request, "partials/post_list.html", ctx)
    if tab == "foryou":
        recommend.mark_seen(db, user, posts)
    return resp


@router.get("/welcome")
def welcome(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return render(request, db, "landing.html", sidebar=False)
    popular = (db.query(models.User).filter(models.User.id != user.id, models.User.is_blocked == False)
               .order_by(models.User.total_points.desc()).limit(12).all())
    return render(request, db, "welcome.html", popular=popular, following=social.following_ids(db, user))
