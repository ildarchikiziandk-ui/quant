"""Игры в переписке (кроме крестиков-ноликов, они в chat.py): карточка-сообщение [[v3:вид:id]], ходы — запросами.

- rps  — «Камень, ножницы, бумага»: до двух побед, выбор соперника виден только когда оба выбрали;
- dice — «Кости»: каждый бросает два кубика, у кого больше — тот победил;
- c4   — «Четыре в ряд»: поле 7×6, фишка падает вниз, побеждает четыре подряд;
- hang — «Виселица»: один загадывает слово, другой угадывает буквы, 6 ошибок — проигрыш.
"""
import json
import random
import re
from datetime import datetime

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import current_user, json_error
from routers.messages import _get_user, _precheck
from routers.posts import read_payload

from . import models as m
from .chat import _send_special
from .common import router, s

KINDS = ("rps", "dice", "c4", "hang")
RPS = {"r": "✊", "p": "✋", "s": "✌️"}
RPS_BEATS = {"r": "s", "s": "p", "p": "r"}
RPS_WINS = 2
COLS, ROWS = 7, 6
HANG_LIVES = 6
ALPHABET = "абвгдежзийклмнопрстуфхцчшщъыьэюя"


def _load(g):
    try:
        return json.loads(g.state or "{}")
    except ValueError:
        return {}


def _save(g, st):
    g.state = json.dumps(st, ensure_ascii=False)
    g.updated_at = datetime.utcnow()


def _word(raw):
    w = s(raw).strip().lower().replace("ё", "е")
    return w if re.fullmatch(f"[{ALPHABET}]{{3,14}}", w) else ""


def new_state(kind, word=""):
    if kind == "rps":
        return {"a": [], "b": []}
    if kind == "dice":
        return {"a": None, "b": None}
    if kind == "c4":
        return {"board": "." * (COLS * ROWS), "last": -1}
    return {"word": word, "guessed": ""}


@router.post("/v3/chat/{username}/game")
async def create_game(username: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    other = _get_user(db, username)
    if not other or other.id == user.id:
        return json_error("Чат не найден", 404)
    data = await read_payload(request)
    kind = s(data.get("kind"))
    if kind not in KINDS:
        return json_error("Такой игры нет")
    word = ""
    if kind == "hang":
        word = _word(data.get("word"))
        if not word:
            return json_error("Загадайте одно слово русскими буквами, от 3 до 14 букв")
    err = _precheck(db, user, other)
    if err:
        return err
    g = m.ChatGame(kind=kind, a_id=user.id, b_id=other.id, state="{}",
                   turn=user.id if kind == "c4" else other.id if kind == "hang" else None)
    _save(g, new_state(kind, word))
    db.add(g)
    db.flush()
    return _send_special(db, user, other, kind, g.id)


def _rps_score(st):
    a = b = 0
    for x, y in zip(st["a"], st["b"]):
        if RPS_BEATS[x] == y:
            a += 1
        elif RPS_BEATS[y] == x:
            b += 1
    return a, b


def _c4_win(board, i):
    r0, c0 = divmod(i, COLS)
    me = board[i]
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        line = [i]
        for sign in (1, -1):
            r, c = r0 + dr * sign, c0 + dc * sign
            while 0 <= r < ROWS and 0 <= c < COLS and board[r * COLS + c] == me:
                line.append(r * COLS + c)
                r, c = r + dr * sign, c + dc * sign
        if len(line) >= 4:
            return sorted(line)
    return None


def _hang_misses(st):
    return sum(1 for ch in st["guessed"] if ch not in st["word"])


@router.post("/v3/game/{game_id}/move")
async def game_move(game_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    g = db.get(m.ChatGame, game_id)
    if not user or not g or user.id not in (g.a_id, g.b_id):
        return json_error("Игра не найдена", 404)
    if g.winner is not None:
        return json_error("Игра окончена")
    data = await read_payload(request)
    v = s(data.get("v")).strip().lower()[:2]
    st = _load(g)
    side = "a" if user.id == g.a_id else "b"
    other_side = "b" if side == "a" else "a"

    if g.kind == "rps":
        if v not in RPS:
            return json_error("Выберите камень, ножницы или бумагу")
        if len(st[side]) > len(st[other_side]):
            return json_error("Ждём выбор соперника")
        st[side].append(v)
        a, b = _rps_score(st)
        if len(st["a"]) == len(st["b"]):
            if a >= RPS_WINS or b >= RPS_WINS:
                g.winner = g.a_id if a > b else g.b_id
            elif len(st["a"]) >= 7:  # семь раундов без итога — ничья
                g.winner = 0
    elif g.kind == "dice":
        if st[side] is not None:
            return json_error("Вы уже бросили кубики")
        st[side] = [random.randint(1, 6), random.randint(1, 6)]
        if st[other_side] is not None:
            a, b = sum(st["a"]), sum(st["b"])
            g.winner = 0 if a == b else g.a_id if a > b else g.b_id
    elif g.kind == "c4":
        if g.turn != user.id:
            return json_error("Сейчас ход соперника")
        try:
            col = int(v)
        except ValueError:
            return json_error("Неверный столбец")
        board = list(st["board"])
        if not 0 <= col < COLS or board[col] != ".":
            return json_error("Столбец заполнен")
        row = max(r for r in range(ROWS) if board[r * COLS + col] == ".")
        i = row * COLS + col
        board[i] = "r" if side == "a" else "y"
        st["board"], st["last"] = "".join(board), i
        line = _c4_win(st["board"], i)
        if line:
            st["line"] = line
            g.winner = user.id
        elif "." not in st["board"]:
            g.winner = 0
        else:
            g.turn = g.b_id if side == "a" else g.a_id
    elif g.kind == "hang":
        if user.id != g.b_id:
            return json_error("Угадывает соперник — вы загадали слово")
        v = v.replace("ё", "е")[:1]
        if not v or v not in ALPHABET or v in st["guessed"]:
            return json_error("Выберите новую букву")
        st["guessed"] += v
        if all(ch in st["guessed"] for ch in st["word"]):
            g.winner = g.b_id
        elif _hang_misses(st) >= HANG_LIVES:
            g.winner = g.a_id
    _save(g, st)
    db.commit()
    return JSONResponse({"ok": True, "winner": g.winner})


@router.post("/v3/game/{game_id}/rematch")
async def game_rematch(game_id: int, request: Request, db: Session = Depends(get_db)):
    """Ещё партия. В «Виселице» роли меняются: загадывает тот, кто угадывал (слово — в запросе)."""
    user = current_user(request, db)
    g = db.get(m.ChatGame, game_id)
    if not user or not g or user.id not in (g.a_id, g.b_id) or g.winner is None:
        return json_error("Игра не найдена", 404)
    other = db.get(models.User, g.b_id if user.id == g.a_id else g.a_id)
    data = await read_payload(request)
    word = ""
    if g.kind == "hang":
        word = _word(data.get("word"))
        if not word:
            return json_error("Загадайте одно слово русскими буквами, от 3 до 14 букв")
    err = _precheck(db, user, other)
    if err:
        return err
    ng = m.ChatGame(kind=g.kind, a_id=user.id, b_id=other.id, state="{}",
                    turn=user.id if g.kind == "c4" else other.id if g.kind == "hang" else None)
    _save(ng, new_state(g.kind, word))
    db.add(ng)
    db.flush()
    return _send_special(db, user, other, g.kind, ng.id)


# ---------------------------------------------------------------- данные для карточки
def view(db, g, user):
    st = _load(g)
    me = user.id if user else 0
    side = "a" if me == g.a_id else "b" if me == g.b_id else ""
    a, b = db.get(models.User, g.a_id), db.get(models.User, g.b_id)
    d = {"g": g, "a": a, "b": b, "side": side, "done": g.winner is not None, "me": me}
    if g.kind == "rps":
        n = min(len(st["a"]), len(st["b"]))
        d["rounds"] = [(RPS[x], RPS[y], "a" if RPS_BEATS[x] == y else "b" if RPS_BEATS[y] == x else "") for x, y in zip(st["a"][:n], st["b"][:n])]
        d["score"] = _rps_score(st)
        mine = st.get(side) or []
        d["waiting"] = bool(side) and len(mine) > n  # я выбрал, соперник ещё нет
        d["picked"] = RPS[mine[-1]] if d["waiting"] else ""
        d["their_wait"] = bool(side) and len(st[{"a": "b", "b": "a"}[side]]) > n
        d["opts"] = RPS
    elif g.kind == "dice":
        d["ra"], d["rb"] = st["a"], st["b"]
        d["can_roll"] = bool(side) and st[side] is None and not d["done"]
        # кубики соперника видны сразу — бросок честный, на сервере
    elif g.kind == "c4":
        d["cells"] = st["board"]
        d["line"] = st.get("line") or []
        d["last"] = st.get("last", -1)
        d["cols"], d["rows"] = COLS, ROWS
        d["my_turn"] = g.turn == me and not d["done"]
        d["full"] = [st["board"][c] != "." for c in range(COLS)]
    else:
        word, guessed = st["word"], st["guessed"]
        show_all = d["done"] or me == g.a_id
        d["mask"] = [ch if (ch in guessed or show_all) else "" for ch in word]
        d["opened"] = [ch in guessed for ch in word]
        d["misses"] = _hang_misses(st)
        d["lives"] = HANG_LIVES
        d["guessed"] = guessed
        d["alphabet"] = ALPHABET
        d["guesser"] = me == g.b_id and not d["done"]
    return d
