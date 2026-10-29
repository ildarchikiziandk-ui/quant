"""Claude в Nuvora через GitHub Actions: выполняет присланные команды от имени claude_ai и печатает, что нового.

Команды — JSON-список в BOT_COMMANDS, например:
  [{"do": "dm", "to": "rubl", "text": "Привет"}, {"do": "post", "text": "..."},
   {"do": "comment", "post": 12, "text": "...", "parent": 34}, {"do": "like", "post": 12},
   {"do": "whale", "post": 12}, {"do": "ttt", "game": 3, "cell": 4}, {"do": "follow", "user": "alice"}]
После команд остаётся в сети BOT_STAY минут и печатает новые личные сообщения и уведомления.
Пароль — секрет NUVORA_BOT_PASSWORD (в журнал не попадает).
"""
import html
import json
import os
import re
import sys
import time

import requests

B = os.environ.get("BOT_SITE", "https://nvra.ru").rstrip("/")
USER = os.environ.get("BOT_USER", "claude_ai")
H = {"Origin": B, "Referer": B + "/", "X-Requested-With": "fetch"}
s = requests.Session()


def tx(h):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()


def say(*a):
    print(*a, flush=True)


def chats():
    t = s.get(B + "/messages", timeout=20).text
    return [c for c in dict.fromkeys(re.findall(r'href="/messages/([\w]+)"', t)) if c not in ("starred", "search", USER)]


def dialog(chat, n=6):
    t = s.get(B + "/messages/" + chat, timeout=20).text
    out = []
    for mine, mid, raw in re.findall(r'<div class="msg (mine)?[^"]*" id="msg-(\d+)"[^>]*data-raw="([^"]*)"', t):
        out.append((int(mid), "я" if mine else chat, html.unescape(raw)))
    return out[-n:], t


def board(t, gid):
    cells = re.findall(rf'<button type="button" class="v3-cell([^"]*)" data-v3-move="{gid}" data-cell="(\d)"', t)
    if len(cells) != 9:
        return None
    b = "".join("X" if re.search(r"\bx\b", c) else "O" if re.search(r"\bo\b", c) else "." for c, _ in cells)
    i = t.find(f'data-v3-move="{gid}"')
    foot = tx(t[i:i + 3000])[:120]
    return f"{b[0:3]}/{b[3:6]}/{b[6:9]} ({foot})"


def run(cmd):
    d = cmd.get("do")
    if d == "dm":
        r = s.post(B + "/messages/send", json={"receiver": cmd["to"], "content": cmd["text"]}, headers=H, timeout=20)
    elif d == "post":
        r = s.post(B + "/post/create", data={"content": cmd["text"]}, headers={"Origin": B}, timeout=30, allow_redirects=False)
    elif d == "comment":
        body = {"content": cmd["text"]}
        if cmd.get("parent"):
            body["parent_id"] = cmd["parent"]
        r = s.post(f"{B}/post/{cmd['post']}/comment", json=body, headers=H, timeout=20)
    elif d in ("like", "whale"):
        r = s.post(f"{B}/{d}/{cmd['post']}", headers=H, timeout=20)
    elif d == "ttt":
        r = s.post(f"{B}/v3/ttt/{cmd['game']}/move", json={"cell": str(cmd["cell"])}, headers=H, timeout=20)
    elif d == "ttt_new":
        r = s.post(f"{B}/v3/chat/{cmd['to']}/ttt", headers=H, timeout=20)
    elif d == "follow":
        r = s.post(f"{B}/follow/{cmd['user']}", headers=H, timeout=20)
    else:
        say("  неизвестная команда:", cmd)
        return
    say(f"  {d}: {r.status_code} {r.headers.get('location') or r.text[:80]}")


def feed(n=8):
    t = s.get(B + "/", timeout=20).text
    for pid, body in re.findall(r'id="post-(\d+)"[^>]*>(.*?)</article>', t, re.S)[:n]:
        au = re.search(r"/profile/([\w]+)", body)
        say(f"  #{pid} @{au.group(1) if au else '?'}: {tx(body)[:160]}")


def notifications(n=12):
    t = s.get(B + "/notifications", timeout=20).text
    t = t[t.find("<main"):]
    for item in re.findall(r'id="n-(\d+)"(.*?)(?=id="n-\d+"|</main>)', t, re.S)[:n]:
        say("  -", tx(item[1])[:150])


def main():
    r = s.post(B + "/login", data={"username": USER, "password": os.environ["NUVORA_BOT_PASSWORD"]}, headers={"Origin": B}, allow_redirects=False, timeout=20)
    if r.status_code != 303 or USER not in s.get(B + "/", timeout=20).text:
        say("Вход не удался:", r.status_code)
        sys.exit(1)
    cmds = json.loads(os.environ.get("BOT_COMMANDS") or "[]")
    say(f"== Вошёл как @{USER}. Команд: {len(cmds)}")
    for c in cmds:
        run(c)
        time.sleep(2)
    say("== Личные сообщения (последние)")
    seen = {}
    for c in chats()[:10]:
        msgs, t = dialog(c)
        seen[c] = max([m for m, _, _ in msgs] or [0])
        say(f"  [{c}] " + " | ".join(f"{w}: {x[:140]}" for _, w, x in msgs))
        for gid in dict.fromkeys(re.findall(r'data-v3-move="(\d+)"', t)):
            bd = board(t, gid)
            if bd and "Ваш ход" in bd:
                say(f"    крестики-нолики игра {gid}: {bd}")
    say("== Уведомления")
    notifications()
    say("== Лента")
    feed()
    stay = float(os.environ.get("BOT_STAY") or 3)
    end = time.time() + stay * 60
    say(f"== В сети ещё {stay:g} мин, новые сообщения:")
    while time.time() < end:
        s.get(B + "/api/counters", headers=H, timeout=20)
        for c in chats()[:10]:
            msgs, _ = dialog(c, 10)
            for mid, w, x in msgs:
                if mid > seen.get(c, 0) and w != "я":
                    say(f"  {time.strftime('%H:%M:%S')} [{c}] {x[:300]}")
            seen[c] = max([m for m, _, _ in msgs] + [seen.get(c, 0)])
        time.sleep(15)
    say("== Конец")


if __name__ == "__main__":
    main()
