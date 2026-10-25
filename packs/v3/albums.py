"""Фотоальбомы (в профиле и в сообществах) и отметки друзей на фото (Nuvora 3.2).

Отметить можно того, на кого вы подписаны или кто подписан на вас (или любого, если вы — админ сообщества).
Отмеченный получает уведомление и может убрать отметку; «Фото со мной» — все фото, где человек отмечен.
"""
from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import current_user, json_error, login_redirect, redirect, render
from services import handles, social
from services.uploads import delete_file, is_upload, save_file

from . import communities
from . import models as m
from .common import router, s

PRIVACY = {"all": "Все", "followers": "Подписчики", "me": "Только я"}
MAX_UPLOAD = 30  # фото за один раз


def _owner_user(db, a):
    return db.get(models.User, a.user_id)


def can_view(db, viewer, a):
    if not a:
        return False
    if a.community_id:
        return True  # альбомы сообществ открыты, как и их записи
    owner = _owner_user(db, a)
    if viewer and owner and viewer.id == owner.id:
        return True
    if viewer and social.can_mod(viewer):
        return True
    if not social.can_see_content(db, viewer, owner):
        return False
    if a.privacy == "me":
        return False
    if a.privacy == "followers":
        return bool(viewer) and social.is_following(db, viewer, owner)
    return True


def can_edit(db, user, a):
    if not user or not a:
        return False
    if a.community_id:
        return communities.can_manage(db, db.get(m.Community, a.community_id), user)
    return a.user_id == user.id


def _cover(db, a):
    p = db.query(m.Photo).filter_by(album_id=a.id).order_by(m.Photo.id.desc()).first()
    return p.url if p else ""


def _cards(db, albums):
    out = []
    for a in albums:
        out.append({"a": a, "cover": _cover(db, a), "n": db.query(m.Photo).filter_by(album_id=a.id).count()})
    return out


def tagged_photos(db, viewer, user, limit=60):
    rows = (db.query(m.Photo).join(m.PhotoTag, m.PhotoTag.photo_id == m.Photo.id).filter(m.PhotoTag.user_id == user.id)
            .order_by(m.PhotoTag.id.desc()).limit(limit * 2).all())
    return [p for p in rows if can_view(db, viewer, db.get(m.Album, p.album_id))][:limit]


# ---------------------------------------------------------------- страницы
@router.get("/profile/{username}/photos")
def user_photos(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    pu = handles.owner_of(db, username)
    if not pu:
        return redirect("/")
    albums = [a for a in db.query(m.Album).filter_by(user_id=pu.id, community_id=None).order_by(m.Album.id.desc()) if can_view(db, user, a)]
    return render(request, db, "packs/v3/albums.html", pu=pu, albums=_cards(db, albums), tagged=tagged_photos(db, user, pu, 24),
                  me=bool(user and user.id == pu.id), privacy=PRIVACY, community=None)


@router.get("/c/{slug}/photos")
def community_photos(slug: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    c = communities.by_ref(db, slug)
    if not c:
        return redirect("/c")
    albums = db.query(m.Album).filter_by(community_id=c.id).order_by(m.Album.id.desc()).all()
    return render(request, db, "packs/v3/albums.html", pu=None, community=c, albums=_cards(db, albums), tagged=[],
                  me=communities.can_manage(db, c, user), privacy=PRIVACY)


@router.post("/albums/new")
async def album_new(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    f = await request.form()
    title = s(f.get("title")).strip()[:80]
    if not title:
        return json_error("Назовите альбом")
    cid = None
    if f.get("community"):
        c = communities.by_ref(db, f.get("community"))
        if not communities.can_manage(db, c, user):
            return json_error("Альбомы сообщества создают админы", 403)
        cid = c.id
    if db.query(m.Album).filter_by(user_id=user.id).count() >= 100:
        return json_error("Можно создать до 100 альбомов")
    from services.text import BANNED_MSG, banned
    if banned(title + " " + s(f.get("description")), social.stop_words(db)):
        return json_error(BANNED_MSG)
    a = m.Album(user_id=user.id, community_id=cid, title=title, description=s(f.get("description")).strip()[:300],
                privacy=s(f.get("privacy")) if s(f.get("privacy")) in PRIVACY and not cid else "all")
    db.add(a)
    db.commit()
    return JSONResponse({"ok": True, "url": f"/albums/{a.id}"})


@router.get("/albums/{aid}")
def album_page(aid: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    a = db.get(m.Album, aid)
    if not can_view(db, user, a):
        return render(request, db, "error.html", status_code=404, code=404, title="Альбом недоступен", text="Его удалили или владелец его скрыл.")
    photos = db.query(m.Photo).filter_by(album_id=a.id).order_by(m.Photo.id.desc()).all()
    return render(request, db, "packs/v3/album.html", a=a, photos=photos, can_edit=can_edit(db, user, a), owner=_owner_user(db, a),
                  community=db.get(m.Community, a.community_id) if a.community_id else None, privacy=PRIVACY)


@router.post("/albums/{aid}/upload")
async def upload(aid: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    a = db.get(m.Album, aid)
    if not can_edit(db, user, a):
        return json_error("Нет доступа", 403)
    f = await request.form()
    files = [x for x in f.getlist("photos") if is_upload(x)][:MAX_UPLOAD]
    if not files:
        return json_error("Выберите фото")
    ok, errs = 0, []
    for x in files:
        url, mt = save_file(x, allowed=("image",))
        if url:
            db.add(m.Photo(album_id=a.id, user_id=user.id, url=url))
            ok += 1
        else:
            errs.append(mt)
    db.commit()
    if not ok:
        return json_error(errs[0] if errs else "Не удалось загрузить")
    return JSONResponse({"ok": True, "added": ok})


@router.post("/albums/{aid}/{act}")
async def album_act(aid: int, act: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    a = db.get(m.Album, aid)
    if not can_edit(db, user, a):
        return json_error("Нет доступа", 403)
    f = await request.form()
    if act == "save":
        a.title = s(f.get("title")).strip()[:80] or a.title
        a.description = s(f.get("description")).strip()[:300]
        if not a.community_id and s(f.get("privacy")) in PRIVACY:
            a.privacy = s(f.get("privacy"))
        db.commit()
        return redirect(f"/albums/{a.id}")
    if act == "delete":
        back = f"/c/{db.get(m.Community, a.community_id).slug}/photos" if a.community_id else f"/profile/{user.username}/photos"
        for p in db.query(m.Photo).filter_by(album_id=a.id).all():
            db.query(m.PhotoTag).filter_by(photo_id=p.id).delete()
            delete_file(p.url)
            db.delete(p)
        db.delete(a)
        db.commit()
        return JSONResponse({"ok": True, "url": back})
    return json_error("Неизвестное действие")


@router.get("/photos/{pid}")
def photo_page(pid: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    p = db.get(m.Photo, pid)
    a = db.get(m.Album, p.album_id) if p else None
    if not can_view(db, user, a):
        return render(request, db, "error.html", status_code=404, code=404, title="Фото недоступно", text="Его удалили или владелец его скрыл.")
    ids = [x for (x,) in db.query(m.Photo.id).filter_by(album_id=a.id).order_by(m.Photo.id.desc())]
    i = ids.index(p.id)
    tags = [(t, db.get(models.User, t.user_id)) for t in db.query(m.PhotoTag).filter_by(photo_id=p.id)]
    return render(request, db, "packs/v3/photo.html", p=p, a=a, tags=[(t, u) for t, u in tags if u],
                  prev=ids[i - 1] if i > 0 else None, next=ids[i + 1] if i + 1 < len(ids) else None, pos=i + 1, total=len(ids),
                  can_edit=can_edit(db, user, a), can_tag=bool(user) and (can_edit(db, user, a) or user.id == p.user_id or can_view(db, user, a)),
                  uploader=db.get(models.User, p.user_id))


@router.post("/photos/{pid}/{act}")
async def photo_act(pid: int, act: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    p = db.get(m.Photo, pid)
    a = db.get(m.Album, p.album_id) if p else None
    if not user or not can_view(db, user, a):
        return json_error("Фото не найдено", 404)
    f = await request.form()
    if act == "tag":
        t = handles.owner_of(db, s(f.get("username")).strip().lstrip("@"))
        if not t:
            return json_error("Пользователь не найден")
        manage = bool(a.community_id) and can_edit(db, user, a)  # в своих альбомах — только тех, с кем есть подписка
        if t.id != user.id and not manage and not (social.is_following(db, user, t) or social.is_following(db, t, user)):
            return json_error("Отмечать можно тех, с кем вы подписаны друг на друга или хотя бы один на другого")
        if social.is_blocked_between(db, user, t):
            return json_error("Этого человека нельзя отметить", 403)
        if db.query(m.PhotoTag).filter_by(photo_id=p.id).count() >= 30:
            return json_error("На фото уже 30 отметок")
        try:
            x, y = max(0, min(100, int(float(s(f.get("x")) or 50)))), max(0, min(100, int(float(s(f.get("y")) or 50))))
        except ValueError:
            x, y = 50, 50
        row = db.query(m.PhotoTag).filter_by(photo_id=p.id, user_id=t.id).first()
        if not row:
            db.add(m.PhotoTag(photo_id=p.id, user_id=t.id, by_user_id=user.id, x=x, y=y))
            social.notify(db, t.id, "photo_tag", user, text="отметил(а) вас на фото", url=f"/photos/{p.id}")
        else:
            row.x, row.y = x, y
        db.commit()
        return JSONResponse({"ok": True})
    if act == "untag":
        uid = int(s(f.get("user")) or 0) if s(f.get("user")).isdigit() else user.id
        row = db.query(m.PhotoTag).filter_by(photo_id=p.id, user_id=uid).first()
        if row and (uid == user.id or row.by_user_id == user.id or can_edit(db, user, a)):
            db.delete(row)
            db.commit()
            return JSONResponse({"ok": True})
        return json_error("Эту отметку убрать нельзя", 403)
    if not (can_edit(db, user, a) or p.user_id == user.id):
        return json_error("Нет доступа", 403)
    if act == "caption":
        p.caption = s(f.get("caption")).strip()[:300]
        db.commit()
        return JSONResponse({"ok": True})
    if act == "delete":
        db.query(m.PhotoTag).filter_by(photo_id=p.id).delete()
        delete_file(p.url)
        db.delete(p)
        db.commit()
        return JSONResponse({"ok": True, "url": f"/albums/{a.id}"})
    return json_error("Неизвестное действие")
