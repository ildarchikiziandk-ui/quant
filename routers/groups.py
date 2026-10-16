import secrets

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import current_user, json_error, login_redirect, redirect, render, templates
from routers.posts import read_payload, wants_json
from services import gamification, push, ratelimit, social
from services.text import censor
from services.uploads import delete_file, is_upload, save_file

router = APIRouter()


def _membership(db, group_id, user):
    if not user:
        return None
    return db.query(models.GroupMember).filter_by(group_id=group_id, user_id=user.id).first()


def _ctx(db, request, group_id, admin=False):
    user = current_user(request, db)
    if not user:
        return None, None, None, json_error("auth", 401)
    g = db.get(models.GroupChat, group_id)
    member = _membership(db, group_id, user)
    if not g or not member:
        return None, None, None, json_error("not found", 404)
    if admin and not (member.is_admin or g.owner_id == user.id):
        return None, None, None, json_error("forbidden", 403)
    return user, g, member, None


@router.get("/groups")
def groups_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    ids = [gm.group_id for gm in db.query(models.GroupMember).filter_by(user_id=user.id)]
    groups = db.query(models.GroupChat).filter(models.GroupChat.id.in_(ids or [-1])).all()
    counts = dict(db.query(models.GroupMember.group_id, func.count(models.GroupMember.id))
                  .filter(models.GroupMember.group_id.in_(ids or [-1])).group_by(models.GroupMember.group_id).all())
    return render(request, db, "groups.html", groups=groups, counts=counts)


@router.post("/groups/create")
async def create_group(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    form = await request.form()
    name = (form.get("name") or "").strip()[:60]
    if not name:
        return redirect("/groups")
    if not ratelimit.hit(f"group:{user.id}", 5, 3600):
        return redirect("/groups")
    av_url = ""
    if is_upload(form.get("avatar")):
        url, _ = save_file(form.get("avatar"), allowed=("image",))
        av_url = url or ""
    g = models.GroupChat(name=name, description=(form.get("description") or "").strip()[:300], owner_id=user.id, avatar=av_url,
                         invite_code=secrets.token_urlsafe(8))
    db.add(g)
    db.flush()
    db.add(models.GroupMember(group_id=g.id, user_id=user.id, is_admin=True))
    added = {user.id}
    for uname in (form.get("members") or "").replace(",", " ").split()[:50]:
        u = db.query(models.User).filter(func.lower(models.User.username) == uname.lstrip("@").lower()).first()
        # добавить можно только того, кому вы и так можете написать (уважаем «кто может мне писать»), и только один раз
        if u and u.id not in added and social.can_message(db, user, u)[0]:
            added.add(u.id)
            db.add(models.GroupMember(group_id=g.id, user_id=u.id))
            social.notify(db, u.id, "group_invite", user, text=f"добавил(а) вас в группу «{name}»", url=f"/groups/{g.id}")
    gamification.check_achievement(user, db, "group_founder")
    db.commit()
    return redirect(f"/groups/{g.id}")


@router.get("/groups/join/{code}")
def join_by_code(code: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    g = db.query(models.GroupChat).filter(models.GroupChat.invite_code == code, models.GroupChat.invite_code != "").first()
    if not g:
        return render(request, db, "error.html", status_code=404, code=404, title="Приглашение недействительно", text="Ссылка устарела или неверна.")
    if not _membership(db, g.id, user):
        db.add(models.GroupMember(group_id=g.id, user_id=user.id))
        db.add(models.GroupMessage(group_id=g.id, sender_id=user.id, content=f"{user.name or user.username} присоединился(лась) по ссылке"))
        db.commit()
    return redirect(f"/groups/{g.id}")


@router.get("/groups/{group_id}")
def group_chat_page(group_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    g = db.get(models.GroupChat, group_id)
    member = _membership(db, group_id, user)
    if not g or not member:
        return redirect("/groups")
    msgs = list(reversed(db.query(models.GroupMessage).filter_by(group_id=group_id).order_by(models.GroupMessage.id.desc()).limit(150).all()))
    members = db.query(models.GroupMember).filter_by(group_id=group_id).all()
    if not g.invite_code:
        g.invite_code = secrets.token_urlsafe(8)
        db.commit()
    return render(request, db, "group_chat.html", sidebar=False, group=g, messages=msgs, members=members, me=member,
                  is_admin=member.is_admin or g.owner_id == user.id,
                  candidates=db.query(models.User).filter(models.User.id.in_(social.following_ids(db, user) or {-1}),
                                                          ~models.User.id.in_([m.user_id for m in members])).limit(50).all())


@router.post("/groups/{group_id}/send")
async def send_group_msg(group_id: int, request: Request, db: Session = Depends(get_db)):
    user, g, member, err = _ctx(db, request, group_id)
    if err:
        return err
    if social.is_active_block(user):
        return json_error("Аккаунт заблокирован", 403)
    if social.needs_email(user):
        return json_error(social.VERIFY_MSG, 403)
    if not ratelimit.hit(f"gmsg:{user.id}", 40, 60):
        return json_error("Слишком часто", 429)
    form = await request.form()
    content = censor((form.get("content") or "").strip()[:4000], social.stop_words(db))
    img_url = file_url = voice_url = file_name = ""
    circle = False
    upload = form.get("image") or form.get("file") or form.get("voice")
    if is_upload(upload):
        url, mt = save_file(upload)
        if not url:
            return json_error(mt)
        if mt == "image":
            img_url = url
        elif mt == "audio":
            voice_url = url
        elif mt == "video" and form.get("circle"):
            img_url, circle = url, True
        else:
            file_url, file_name = url, (upload.filename or "file")[:120]
    if not content and not (img_url or file_url or voice_url):
        return json_error("Пустое сообщение")
    reply = form.get("reply_to_id")
    reply_id = int(reply) if reply and str(reply).isdigit() else None
    m = models.GroupMessage(group_id=group_id, sender_id=user.id, content=content, image=img_url, voice=voice_url,
                            file_url=file_url, file_name=file_name, reply_to_id=reply_id, is_video_circle=circle)
    db.add(m)
    db.commit()
    gamification.complete_task(user, db, "message")
    muted = {mm.user_id for mm in db.query(models.MutedChat).filter_by(muted_group_id=group_id)}
    for mem in db.query(models.GroupMember).filter(models.GroupMember.group_id == group_id, models.GroupMember.user_id != user.id).all():
        if mem.user_id not in muted:
            push.send_push_to_user(mem.user_id, db, g.name, f"{user.name or user.username}: {content[:80] or 'вложение'}", f"/groups/{group_id}")
    if wants_json(request):
        return JSONResponse({"ok": True, "id": m.id})
    return redirect(f"/groups/{group_id}")


@router.get("/api/groups/{group_id}/messages")
def api_group_messages(group_id: int, request: Request, after: int = 0, db: Session = Depends(get_db)):
    user, g, member, err = _ctx(db, request, group_id)
    if err:
        return err
    msgs = db.query(models.GroupMessage).filter(models.GroupMessage.group_id == group_id, models.GroupMessage.id > after).order_by(
        models.GroupMessage.id.asc()).limit(200).all()
    html = templates.get_template("partials/group_messages.html").render(request=request, user=user, messages=msgs, group=g) if msgs else ""
    return JSONResponse({"ok": True, "html": html, "last_id": max([after] + [m.id for m in msgs])})


@router.post("/groups/{group_id}/messages/{msg_id}/delete")
def delete_group_msg(group_id: int, msg_id: int, request: Request, db: Session = Depends(get_db)):
    user, g, member, err = _ctx(db, request, group_id)
    if err:
        return err
    m = db.query(models.GroupMessage).filter_by(id=msg_id, group_id=group_id).first()
    if m and (m.sender_id == user.id or member.is_admin or g.owner_id == user.id):
        m.is_deleted, m.content, m.image, m.voice, m.file_url = True, "", "", "", ""
        db.commit()
    return JSONResponse({"ok": True})


@router.post("/groups/{group_id}/invite/{username}")
def invite_to_group(group_id: int, username: str, request: Request, db: Session = Depends(get_db)):
    user, g, member, err = _ctx(db, request, group_id, admin=True)
    if err:
        return err
    target = db.query(models.User).filter(func.lower(models.User.username) == username.lower()).first()
    if target and not _membership(db, group_id, target) and social.can_message(db, user, target)[0]:
        db.add(models.GroupMember(group_id=group_id, user_id=target.id))
        db.add(models.GroupMessage(group_id=group_id, sender_id=user.id, content=f"добавил(а) {target.name or target.username}"))
        social.notify(db, target.id, "group_invite", user, text=f"добавил(а) вас в группу «{g.name}»", url=f"/groups/{group_id}")
        db.commit()
    if wants_json(request):
        return JSONResponse({"ok": True})
    return redirect(f"/groups/{group_id}")


@router.post("/groups/{group_id}/kick/{user_id}")
def kick_member(group_id: int, user_id: int, request: Request, db: Session = Depends(get_db)):
    user, g, member, err = _ctx(db, request, group_id, admin=True)
    if err:
        return err
    if user_id != g.owner_id:
        db.query(models.GroupMember).filter_by(group_id=group_id, user_id=user_id).delete()
        g.invite_code = secrets.token_urlsafe(8)  # старая ссылка-приглашение больше не пустит исключённого обратно
        db.commit()
    return redirect(f"/groups/{group_id}")


@router.post("/groups/{group_id}/admin/{user_id}")
def toggle_admin(group_id: int, user_id: int, request: Request, db: Session = Depends(get_db)):
    user, g, member, err = _ctx(db, request, group_id)
    if err:
        return err
    if g.owner_id != user.id:
        return json_error("Только владелец", 403)
    m = db.query(models.GroupMember).filter_by(group_id=group_id, user_id=user_id).first()
    if m and user_id != g.owner_id:
        m.is_admin = not m.is_admin
        db.commit()
    return redirect(f"/groups/{group_id}")


@router.post("/groups/{group_id}/edit")
async def edit_group(group_id: int, request: Request, db: Session = Depends(get_db)):
    user, g, member, err = _ctx(db, request, group_id, admin=True)
    if err:
        return err
    form = await request.form()
    g.name = (form.get("name") or g.name).strip()[:60] or g.name
    g.description = (form.get("description") or "").strip()[:300]
    if is_upload(form.get("avatar")):
        url, _ = save_file(form.get("avatar"), allowed=("image",))
        if url:
            delete_file(g.avatar)
            g.avatar = url
    if form.get("reset_link"):
        g.invite_code = secrets.token_urlsafe(8)
    db.commit()
    return redirect(f"/groups/{group_id}")


@router.post("/groups/{group_id}/leave")
def leave_group(group_id: int, request: Request, db: Session = Depends(get_db)):
    user, g, member, err = _ctx(db, request, group_id)
    if err:
        return err
    db.query(models.GroupMember).filter_by(group_id=group_id, user_id=user.id).delete()  # вместе со старыми дублями
    db.flush()
    if g.owner_id == user.id:
        heir = db.query(models.GroupMember).filter_by(group_id=group_id).order_by(models.GroupMember.is_admin.desc(), models.GroupMember.id).first()
        if heir:
            g.owner_id, heir.is_admin = heir.user_id, True
        else:
            db.query(models.GroupMessage).filter_by(group_id=group_id).delete()
            db.query(models.PinnedChat).filter_by(pinned_group_id=group_id).delete()
            db.query(models.MutedChat).filter_by(muted_group_id=group_id).delete()
            db.query(models.TypingStatus).filter_by(group_id=group_id).delete()
            db.delete(g)
    db.commit()
    return redirect("/groups")


@router.post("/groups/{group_id}/mute")
def mute_group(group_id: int, request: Request, db: Session = Depends(get_db)):
    user, g, member, err = _ctx(db, request, group_id)
    if err:
        return err
    ex = db.query(models.MutedChat).filter_by(user_id=user.id, muted_group_id=group_id).first()
    if ex:
        db.delete(ex)
    else:
        db.add(models.MutedChat(user_id=user.id, muted_group_id=group_id))
    db.commit()
    return JSONResponse({"ok": True, "muted": not ex})
