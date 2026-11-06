"""Статус у имени для Nuvora+ — как эмодзи-статус в Telegram Premium (6.11.2026, просьба владельца):
вместо кружка Plus рядом с именем стоит выбранный стикер или эмодзи. Больше 200 вариантов:
все наши стикеры (packs/v3/stickers.py) и подборка эмодзи Twemoji (static/emoji, CC BY 4.0).
Выбор — страница /plus/status (Nuvora+ → «Статус у имени»)."""
import os

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from database import get_db
from deps import current_user, json_error, redirect, render
from services import social

from . import stickers
from .common import router, s

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EMOJI = [
    ("Настроение", "😀 😄 😁 😆 😂 🤣 😊 😇 🙂 😉 😍 🥰 😘 😎 🤩 🥳 😏 🤔 🤗 🤭 😴 🥱 😤 😡 🥺 😢 😭 😱 🤯 🥶 🥵 🤠 🤓 😈 👻 💀 🤖 👽 🙈 💩"),
    ("Сердца и знаки", "❤️ 🧡 💛 💚 💙 💜 🖤 🤍 🤎 💖 💘 💝 💔 ❤️‍🔥 💯 ✨ ⭐ 🌟 💫 ⚡ 🔥 💥 💎 👑 🏆 🥇 🎯 ✅ ❌ ⚠️ 🔔 🎵 🎶 💤 🆒 🆕"),
    ("Животные", "🐶 🐱 🐭 🐹 🐰 🦊 🐻 🐼 🐨 🐯 🦁 🐮 🐷 🐸 🐵 🐔 🐧 🐦 🦉 🦄 🐝 🦋 🐢 🐍 🦖 🐙 🦀 🐬 🐳 🐋 🦈 🐠"),
    ("Еда", "🍎 🍓 🍉 🍌 🍒 🥑 🍕 🍔 🍟 🌭 🌮 🍣 🍜 🍩 🍪 🎂 🍰 🍫 🍬 🍭 🍿 ☕ 🧃 🥤 🧋"),
    ("Природа и погода", "🌸 🌹 🌻 🌷 🍀 🌵 🌲 🍁 🍄 🌈 ☀️ 🌙 🌚 🌝 ⛄ ❄️ 🌊 🌍 🪐 ☁️"),
    ("Игры и хобби", "🎮 🕹️ 🎲 ♟️ 🧩 🎨 🎸 🎧 🎤 📷 📚 ✏️ 💻 📱 🚀 🛸 🚗 🏍️ ✈️ ⚽ 🏀 🏐 🎾 🏓 🥊 🛹 🏄 🎣"),
    ("Праздники", "🎉 🎊 🎈 🎁 🎄 🎅 🎆 🎇 🧨 🎃 🪅 🕯️"),
]


def _code(e):
    cps = [ord(c) for c in e]
    zwj = 0x200D in cps
    return "-".join(f"{c:x}" for c in cps if zwj or c != 0xFE0F)


def _build():
    groups, by_id = [], {}
    for _, title, items in stickers.PACKS:
        row = [{"id": "st:" + k, "img": stickers.url(k), "title": n} for k, n in items]
        groups.append({"title": title, "items": row})
    for title, line in EMOJI:
        row = []
        for e in line.split():
            code = _code(e)
            if os.path.exists(os.path.join(ROOT, "static", "emoji", code + ".svg")):
                row.append({"id": "e:" + code, "img": f"/static/emoji/{code}.svg", "title": e})
        groups.append({"title": title, "items": row})
    for g in groups:
        for it in g["items"]:
            by_id[it["id"]] = it["img"]
    return groups, by_id


GROUPS, BY_ID = _build()


def img_of(user):
    """Картинка статуса у имени, если у человека Nuvora+ и статус выбран; иначе пусто."""
    code = getattr(user, "emoji_status", "") or ""
    return BY_ID.get(code, "") if code and social.is_plus(user) else ""


@router.get("/plus/status")
def status_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return redirect("/login?next=/plus/status")
    return render(request, db, "packs/v3/estatus.html", sidebar=False, groups=GROUPS, total=len(BY_ID),
                  current=user.emoji_status or "", plus=social.is_plus(user))


@router.post("/plus/status")
async def status_save(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    if not social.is_plus(user):
        return json_error("Статус у имени — для Nuvora+", 403)
    from routers.posts import read_payload
    code = s((await read_payload(request)).get("id"))[:40]
    if code and code not in BY_ID:
        return json_error("Такого статуса нет")
    user.emoji_status = code
    db.commit()
    return {"ok": True, "img": BY_ID.get(code, "")}
