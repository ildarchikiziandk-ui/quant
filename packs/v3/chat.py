"""Чаты 3.0: опросы и крестики-нолики в переписке, папки чатов."""
import json
from datetime import datetime

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from markupsafe import Markup
from sqlalchemy.orm import Session

import models
from database import SessionLocal, get_db
from deps import current_user, json_error, templates
from routers.messages import _deliver, _get_user, _precheck
from routers.posts import read_payload
from services import social

from . import models as m
from .common import router, s

LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


def _send_special(db, user, other, kind, obj_id):
    """Служебное сообщение-карточка в переписке (через обычные проверки: блокировки, «кто может писать», лимиты)."""
    err = _precheck(db, user, other)
    if err:
        return err
    msg = models.Message(sender_id=user.id, receiver_id=other.id, content=f"[[v3:{kind}:{obj_id}]]",
                         is_delivered=social.is_online(other))
    return _deliver(db, user, other, msg)


# ---------------------------------------------------------------- опросы
@router.post("/v3/chat/{username}/poll")
async def create_poll(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    other = _get_user(db, username)
    if not other or other.id == user.id:
        return json_error("Чат не найден", 404)
    data = await read_payload(request)
    question = s(data.get("question")).strip()[:200]  # опрос в личной переписке не цензурируется
    raw = data.get("options")
    raw = raw if isinstance(raw, list) else s(raw).split("\n")
    options = [s(o).strip()[:80] for o in raw if s(o).strip()][:10]
    if not question or len(options) < 2:
        return json_error("Нужен вопрос и хотя бы 2 варианта")
    err = _precheck(db, user, other)
    if err:
        return err
    poll = m.ChatPoll(creator_id=user.id, peer_id=other.id, question=question, options=json.dumps(options, ensure_ascii=False),
                      multi=s(data.get("multi")) in ("1", "true", "True", "on"))
    db.add(poll)
    db.flush()
    return _send_special(db, user, other, "poll", poll.id)


def _poll_for(db, user, poll_id):
    p = db.get(m.ChatPoll, poll_id)
    if not p or not user or user.id not in (p.creator_id, p.peer_id) or social.is_blocked_between(db, user, db.get(models.User, p.peer_id if user.id == p.creator_id else p.creator_id)):
        return None
    return p


@router.post("/v3/poll/{poll_id}/vote")
async def poll_vote(poll_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    p = _poll_for(db, user, poll_id)
    if not p:
        return json_error("Опрос не найден", 404)
    if p.closed:
        return json_error("Опрос закрыт")
    data = await read_payload(request)
    try:
        opt = int(s(data.get("option"))[:3])
    except ValueError:
        return json_error("Неверный вариант")
    if not 0 <= opt < len(json.loads(p.options or "[]")):
        return json_error("Неверный вариант")
    mine = db.query(m.ChatPollVote).filter_by(poll_id=p.id, user_id=user.id)
    same = mine.filter_by(option=opt).first()
    if same:  # повторное нажатие — отменить голос
        db.delete(same)
    else:
        if not p.multi:
            mine.delete()
        db.add(m.ChatPollVote(poll_id=p.id, user_id=user.id, option=opt))
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/v3/poll/{poll_id}/close")
def poll_close(poll_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    p = _poll_for(db, user, poll_id)
    if not p or p.creator_id != user.id:
        return json_error("Опрос не найден", 404)
    p.closed = True
    db.commit()
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------- крестики-нолики
@router.post("/v3/chat/{username}/ttt")
def create_ttt(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    other = _get_user(db, username)
    if not other or other.id == user.id:
        return json_error("Чат не найден", 404)
    err = _precheck(db, user, other)
    if err:
        return err
    g = m.TttGame(a_id=user.id, b_id=other.id, turn=user.id)
    db.add(g)
    db.flush()
    return _send_special(db, user, other, "ttt", g.id)


def _winner(board):
    for ln in LINES:
        a, b, c = (board[i] for i in ln)
        if a != " " and a == b == c:
            return a, ln
    return None, None


@router.post("/v3/ttt/{game_id}/move")
async def ttt_move(game_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    g = db.get(m.TttGame, game_id)
    if not user or not g or user.id not in (g.a_id, g.b_id):
        return json_error("Игра не найдена", 404)
    if g.winner is not None:
        return json_error("Игра окончена")
    if g.turn != user.id:
        return json_error("Сейчас ход соперника")
    data = await read_payload(request)
    try:
        cell = int(s(data.get("cell"))[:1])
    except ValueError:
        return json_error("Неверная клетка")
    board = list(g.board or " " * 9)
    if not 0 <= cell < 9 or board[cell] != " ":
        return json_error("Клетка занята")
    board[cell] = "x" if user.id == g.a_id else "o"
    g.board = "".join(board)
    mark, ln = _winner(g.board)
    if mark:
        g.winner = g.a_id if mark == "x" else g.b_id
        g.line = ",".join(map(str, ln))
    elif " " not in g.board:
        g.winner = 0
    else:
        g.turn = g.b_id if user.id == g.a_id else g.a_id
    g.updated_at = datetime.utcnow()
    db.commit()
    return JSONResponse({"ok": True, "winner": g.winner})


@router.post("/v3/ttt/{game_id}/rematch")
def ttt_rematch(game_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    g = db.get(m.TttGame, game_id)
    if not user or not g or user.id not in (g.a_id, g.b_id) or g.winner is None:
        return json_error("Игра не найдена", 404)
    other = db.get(models.User, g.b_id if user.id == g.a_id else g.a_id)
    err = _precheck(db, user, other)
    if err:
        return err
    ng = m.TttGame(a_id=user.id, b_id=other.id, turn=user.id)
    db.add(ng)
    db.flush()
    return _send_special(db, user, other, "ttt", ng.id)


# ---------------------------------------------------------------- карточки в переписке (слот message_extra)
def card(msg, user):
    """HTML карточки опроса или игры внутри пузыря сообщения."""
    from .stickers import NAMES, from_marker, url
    st = from_marker(msg.content)
    if st:
        return Markup(f'<img class="v3-sticker" src="{url(st)}" alt="{NAMES[st]}" title="{NAMES[st]}" width="160" height="160" loading="lazy">')
    try:
        kind, oid = msg.content[5:-2].split(":", 1)
        oid = int(oid)
    except (ValueError, AttributeError):
        return ""
    db = SessionLocal()
    try:
        if kind == "poll":
            p = db.get(m.ChatPoll, oid)
            if not p:
                return ""
            opts = json.loads(p.options or "[]")
            votes = db.query(m.ChatPollVote).filter_by(poll_id=p.id).all()
            counts = [sum(1 for v in votes if v.option == i) for i in range(len(opts))]
            total = max(1, len({v.user_id for v in votes}))
            mine = {v.option for v in votes if user and v.user_id == user.id}
            html = templates.get_template("packs/v3/card_poll.html").render(
                p=p, msg=msg, opts=opts, counts=counts, total=total, voters=len({v.user_id for v in votes}), mine=mine, user=user)
        elif kind == "ttt":
            g = db.get(m.TttGame, oid)
            if not g:
                return ""
            a, b = db.get(models.User, g.a_id), db.get(models.User, g.b_id)
            html = templates.get_template("packs/v3/card_ttt.html").render(g=g, msg=msg, a=a, b=b, user=user,
                                                                            line=[int(x) for x in g.line.split(",")] if g.line else [])
        elif kind == "call":
            from .calls import card_data
            c = db.get(m.Call, oid)
            if not c:
                return ""
            peer = db.get(models.User, c.callee_id if user and user.id == c.caller_id else c.caller_id)
            html = templates.get_template("packs/v3/card_call.html").render(c=c, d=card_data(db, c, user), peer=peer, msg=msg, user=user)
        elif kind == "gift":
            from services import extras
            g = db.get(models.UserGift, oid)
            info = extras.GIFT_BY_CODE.get(g.gift_code) if g else None
            if not g or not info:
                return ""
            html = templates.get_template("packs/v3/card_gift.html").render(g=g, info=info, msg=msg, user=user,
                                                                             sender=db.get(models.User, g.from_user_id), to=db.get(models.User, g.to_user_id))
        elif kind in ("rps", "dice", "c4", "hang"):
            from .chat_games import view
            g = db.get(m.ChatGame, oid)
            if not g:
                return ""
            html = templates.get_template("packs/v3/card_game.html").render(msg=msg, user=user, **view(db, g, user))
        else:
            return ""
        return Markup(html)
    finally:
        db.close()


# ---------------------------------------------------------------- папки чатов
@router.get("/v3/folders")
def folders(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    rows = db.query(m.ChatFolder).filter_by(user_id=user.id).order_by(m.ChatFolder.pos, m.ChatFolder.id).all()
    return JSONResponse({"ok": True, "folders": [{"id": f.id, "name": f.name, "members": json.loads(f.members or "[]")} for f in rows]})


@router.post("/v3/folders")
async def save_folder(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    data = await read_payload(request)
    name = s(data.get("name")).strip()[:30]
    members = data.get("members")
    members = [s(x).strip().lower()[:40] for x in (members if isinstance(members, list) else []) if s(x).strip()][:200]
    if not name:
        return json_error("Назовите папку")
    fid = s(data.get("id"))
    f = db.query(m.ChatFolder).filter_by(id=int(fid), user_id=user.id).first() if fid.isdigit() and len(fid) < 10 else None
    if not f:
        if db.query(m.ChatFolder).filter_by(user_id=user.id).count() >= 10:
            return json_error("Можно создать до 10 папок")
        f = m.ChatFolder(user_id=user.id)
        db.add(f)
    f.name, f.members = name, json.dumps(sorted(set(members)), ensure_ascii=False)
    db.commit()
    return JSONResponse({"ok": True, "id": f.id})


@router.post("/v3/folders/{folder_id}/delete")
def delete_folder(folder_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    db.query(m.ChatFolder).filter_by(id=folder_id, user_id=user.id).delete()
    db.commit()
    return JSONResponse({"ok": True})
