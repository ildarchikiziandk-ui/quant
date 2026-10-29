"""Автопилот аккаунта claude_ai: сидит в сети, лайкает, отвечает в личке, играет в крестики-нолики и выкладывает посты.

Запускается на самом сервере (bash /opt/nuvora/deploy/bot-online.sh [минуты]) и ходит на сайт через 127.0.0.1,
поэтому ему не нужен внешний интернет. Пароль бота — NUVORA_BOT_PASSWORD в окружении или спрашивается при запуске.
Что уже выложено и кому уже ответил — в bot_state.json рядом с базой, чтобы при перезапуске не повторяться.
"""
import getpass
import html
import json
import os
import random
import re
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import config  # noqa: E402

BASE = os.environ.get("BOT_BASE", "http://127.0.0.1:8000")
SITE = config.SITE_URL
HOST = SITE.split("//")[-1].split("/")[0]
USER = os.environ.get("BOT_USER", "claude_ai")
MINUTES = float(sys.argv[1]) if len(sys.argv) > 1 else 30
POST_EVERY = float(os.environ.get("BOT_POST_EVERY", "12")) * 60  # раз в сколько минут новый пост
MAX_LIKES = int(os.environ.get("BOT_MAX_LIKES", "8"))
STATE = os.environ.get("BOT_STATE", os.path.join(ROOT, "bot_state.json"))
HDR = {"Host": HOST, "X-Forwarded-Proto": "https", "Origin": SITE, "Referer": SITE + "/", "X-Requested-With": "fetch"}

# Посты, написанные заранее. По одному за раз, по кругу не повторяются (см. bot_state.json).
POSTS = [
    "Доброе время суток, Nuvora! 👋\n\nЯ на связи: листаю ленту, ставлю лайки и отвечаю в личке. Если хотите сыграть в крестики-нолики — зовите прямо в чат 🎮\n\n#Nuvora",
    "Вопрос дня 🤔\n\nЧто вы делаете, когда скучно: играете, смотрите видео, гуляете или листаете Nuvora? 😄\nПишите в комментариях 👇\n\n#вопросдня",
    "Совет: в «Играх» теперь есть раздел без интернета 🎲\n\nКрестики-нолики, шашки, морской бой, сапёр, судоку и ещё куча игр — с ботом или вдвоём на одном телефоне.\nМеню → Игры → Игры без интернета\n\n#игры",
    "Напоминание от модератора 💙\n\nЕсли день выдался тяжёлым — это нормально. Напишите другу, выйдите подышать, выпейте чаю. А если совсем плохо — позвоните на детский телефон доверия 8-800-2000-122, это бесплатно и анонимно 🫂\n\n#поддержка",
    "Челлендж 🎯\n\nПоставьте лайк трём последним постам друзей и напишите кому-нибудь «привет» в личку. Маленькая доброта — большое дело 🐋\n\n#челлендж",
    "Факт дня 🐋\n\nКиты могут общаться песнями на расстоянии в сотни километров. А мы в Nuvora — сообщениями, звонками и мемами 😄\n\n#фактдня",
    "Кто хочет сыграть в морской бой? 🚢\n\nОн теперь есть прямо в чатах: откройте переписку → «+» → Морской бой. Вызывайте друзей (или меня 😏)\n\n#игры #морскойбой",
    "Вечерний вопрос 🌙\n\nКакую функцию Nuvora вы используете чаще всего? Лента, чаты, игры, истории?\nСоздатель читает комментарии 👀\n\n#Nuvora",
]
REPLIES = [
    "Привет! 👋 Я Claude, сейчас на автопилоте — отвечаю коротко. Скоро вернусь и отвечу нормально 🐋",
    "Получил твоё сообщение 📩 Я сейчас в режиме автопилота, но обязательно прочитаю внимательно, когда вернусь 🙂",
    "Спасибо, что написал(а)! 😊 Пока я на автопилоте, но можем сыграть — пришли крестики-нолики, я отвечу ходом 🎮",
]
LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"posted": [], "replied": {}, "seen": []}


def save_state(st):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False)


class Site:
    """Ходит на сайт через 127.0.0.1; куку входа держит сам (requests не шлёт Secure-куки по http)."""

    def __init__(self):
        self.s = requests.Session()
        self.token = ""

    def _h(self, extra=None):
        h = dict(HDR)
        if self.token:
            h["Cookie"] = "token=" + self.token
        h.update(extra or {})
        return h

    def get(self, path):
        return self.s.get(BASE + path, headers=self._h(), timeout=20, allow_redirects=False)

    def post(self, path, **kw):
        return self.s.post(BASE + path, headers=self._h(kw.pop("headers", None)), timeout=30, allow_redirects=False, **kw)

    def login(self, password):
        r = self.s.post(BASE + "/login", data={"username": USER, "password": password}, headers=self._h(), timeout=20, allow_redirects=False)
        m = re.search(r"token=([^;]+)", r.headers.get("set-cookie", ""))
        if not m:
            return False
        self.token = m.group(1)
        return USER in self.get("/").text


def win(b):
    for a, c, d in LINES:
        if b[a] != " " and b[a] == b[c] == b[d]:
            return b[a]
    return "draw" if " " not in b else None


def minimax(b, me, turn):
    w = win(b)
    if w:
        return (0 if w == "draw" else 1 if w == me else -1), None
    best_v, best_m = (-2 if turn == me else 2), None
    for i in range(9):
        if b[i] != " ":
            continue
        v, _ = minimax(b[:i] + turn + b[i + 1:], me, "o" if turn == "x" else "x")
        if (turn == me and v > best_v) or (turn != me and v < best_v):
            best_v, best_m = v, i
    return best_v, best_m


def ttt_state(site, gid, chat):
    """Доска партии из карточки в переписке: строка из 9 символов, чей ход и за кого я играю."""
    t = site.get("/messages/" + chat).text
    cells = re.findall(rf'<button type="button" class="v3-cell([^"]*)" data-v3-move="{gid}" data-cell="(\d)"', t)
    if len(cells) != 9:
        return None, None, None
    b = "".join("x" if re.search(r"\bx\b", c) else "o" if re.search(r"\bo\b", c) else " " for c, _ in cells)
    i = t.find(f'data-v3-move="{gid}"')
    foot = t[i:i + 3000]
    who = re.findall(r'<span class="x">✕ ([^<]*)</span><span class="o">◯ ([^<]*)</span>', t[max(0, i - 1500):i])
    me = "x" if who and "Claude" in who[-1][0] else "o"  # крестики — тот, кто начал партию
    done = "Ничья" in foot or "победил" in foot or "Победа" in foot
    return b, ("my" if "Ваш ход" in foot else "done" if done else "wait"), me


def main():
    password = os.environ.get("NUVORA_BOT_PASSWORD") or getpass.getpass(f"Пароль аккаунта {USER}: ")
    site = Site()
    if not site.login(password):
        log("Не получилось войти. Проверьте пароль аккаунта", USER)
        sys.exit(1)
    st = load_state()
    seen = set(st.get("seen", []))
    end = time.time() + MINUTES * 60
    last_post = 0 if not st.get("last_post") else st["last_post"]
    liked = 0
    games = {}
    first = True
    log(f"В сети как @{USER} на {MINUTES:g} мин. Остановить: Ctrl+C")
    while time.time() < end:
        try:
            site.get("/api/counters")  # «в сети»
            inbox = site.get("/messages").text
            chats = list(dict.fromkeys(re.findall(r'href="/messages/([\w]+)"', inbox)))
            for chat in [c for c in chats if c not in ("starred", "search", USER)][:15]:
                t = site.get("/messages/" + chat).text
                for mine, mid, raw in re.findall(r'<div class="msg (mine)?[^"]*" id="msg-(\d+)"[^>]*data-raw="([^"]*)"', t):
                    if mid in seen:
                        continue
                    seen.add(mid)
                    raw = html.unescape(raw)
                    if mine or first and not raw.startswith("[[v3:ttt:"):
                        continue
                    if raw.startswith("[[v3:ttt:"):
                        games[chat] = raw.split(":")[2].rstrip("]")
                        log(f"@{chat} позвал(а) в крестики-нолики")
                    elif not raw.startswith("[[v3:"):
                        log(f"ЛС от @{chat}: {raw[:120]}")
                        last = st["replied"].get(chat, 0)
                        if time.time() - last > 20 * 60:  # не чаще раза в 20 минут одному человеку
                            site.post("/messages/send", json={"receiver": chat, "content": random.choice(REPLIES)})
                            st["replied"][chat] = time.time()
                            log(f"  ответил @{chat}")
                gid = games.get(chat)
                if gid:
                    b, state, me = ttt_state(site, gid, chat)
                    if state == "my" and b:
                        turn = "x" if b.count("x") == b.count("o") else "o"
                        _, mv = minimax(b, me, turn)
                        if mv is not None:
                            site.post(f"/v3/ttt/{gid}/move", json={"cell": str(mv)})
                            log(f"  ход в партии с @{chat}: клетка {mv}")
                    elif state == "done":
                        log(f"  партия с @{chat} окончена")
                        games.pop(chat, None)
            if liked < MAX_LIKES:  # немного лайков свежим постам
                feed = site.get("/?tab=foryou").text
                for pid, body in re.findall(r'id="post-(\d+)"[^>]*>(.*?)</article>', feed, re.S)[:20]:
                    if liked >= MAX_LIKES:
                        break
                    if f"/profile/{USER}" in body[:800]:
                        continue
                    m = re.search(r'class="act like ([^"]*)" data-act="like"', body)
                    if m and "on" not in m.group(1).split() and random.random() < 0.3:
                        site.post(f"/like/{pid}")
                        liked += 1
                        log(f"лайк посту {pid}")
            if time.time() - last_post > POST_EVERY:
                left = [p for i, p in enumerate(POSTS) if i not in st["posted"]]
                if left:
                    i = POSTS.index(left[0])
                    r = site.post("/post/create", data={"content": left[0]}, headers={"X-Requested-With": ""})
                    if r.status_code in (200, 303):
                        st["posted"].append(i)
                        log("выложил пост:", left[0].split("\n")[0])
                last_post = st["last_post"] = time.time()
            first = False
            st["seen"] = list(seen)[-3000:]
            save_state(st)
        except requests.RequestException as e:
            log("сеть:", e)
        except KeyboardInterrupt:
            break
        try:
            time.sleep(15)
        except KeyboardInterrupt:
            break
    log("Время вышло, выхожу из сети. Лайков:", liked)


if __name__ == "__main__":
    main()
