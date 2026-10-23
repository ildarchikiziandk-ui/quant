"""Наборы стикеров: «Кит Нуви», «Кот Мур», «Капибара Капи». Картинки лежат в static/stickers/<набор>
(встроены в приложение, не занимают место на сервере). В сообщении стикер — метка [[v3:st:имя]].
Картинки рисуют tools/stickers_gen.py и tools/stickers_more.py. Наборы можно выключать в админ-панели."""
from fastapi.responses import JSONResponse

from . import site
from .common import router

PACKS = [
    ("nuvi", "Кит Нуви", [
        ("privet", "Привет!"), ("spasibo", "Спасибо"), ("lyublyu", "Люблю"), ("haha", "Ха-ха"),
        ("ok", "Окей"), ("ura", "Ура!"), ("grust", "Грущу"), ("zlyus", "Злюсь"),
        ("vau", "Вау!"), ("splyu", "Сплю"), ("kofe", "Кофе?"), ("ogon", "Огонь"),
        ("obnimayu", "Обнимаю"), ("dumayu", "Думаю…"), ("zhdu", "Жду"), ("poka", "Пока!"),
        ("pshikalka", "Пшикалка"),
    ]),
    ("mur", "Кот Мур", [
        ("mur-myau", "Мяу!"), ("mur-murmur", "Мур-мур"), ("mur-spasibo", "Спасибо"), ("mur-pozhaluysta", "Ну пожалуйста"),
        ("mur-obidelsya", "Обиделся"), ("mur-golodny", "Голодный"), ("mur-oy-vsyo", "Ой всё"), ("mur-lyublyu", "Люблю"),
        ("mur-hihi", "Хи-хи"), ("mur-splyu", "Сплю"), ("mur-zhdu", "Жду"), ("mur-poka", "Пока!"),
    ]),
    ("kapi", "Капибара Капи", [
        ("kapi-spokoyno", "Спокойно"), ("kapi-kayf", "Кайф"), ("kapi-norm", "Норм"), ("kapi-utro", "Доброе утро"),
        ("kapi-noch", "Спокойной ночи"), ("kapi-ustal", "Устал"), ("kapi-rabotayu", "Работаю"), ("kapi-pyatnica", "Пятница!"),
        ("kapi-nu-i-ladno", "Ну и ладно"), ("kapi-obnimayu", "Обнимаю"), ("kapi-ogo", "Ого"), ("kapi-ok", "Ок"),
    ]),
]
NAMES = {k: n for _, _, items in PACKS for k, n in items}
PACK_OF = {k: pid for pid, _, items in PACKS for k, _ in items}


def url(name):
    return f"/static/stickers/{PACK_OF[name]}/{name}.webp"  # без версии: встроены в приложение (services/assets.STABLE)


def from_marker(content):
    """Имя стикера из метки или None. Стикеры из выключенного набора в старых сообщениях всё равно видны."""
    if content and content.startswith("[[v3:st:") and content.endswith("]]"):
        name = content[8:-2]
        return name if name in NAMES else None
    return None


def enabled_packs():
    off = set(site.get("sticker_packs_off") or [])
    return [p for p in PACKS if p[0] not in off]


def allowed_text(content):
    """Служебные метки [[v3:…]] вручную отправлять нельзя (кроме стикеров из включённых наборов) — иначе можно подделать чужой опрос или звонок."""
    if not (content or "").startswith("[[v3:"):
        return True
    name = from_marker(content)
    return bool(name) and PACK_OF[name] in {p[0] for p in enabled_packs()}


def picker():
    return [{"id": pid, "title": title, "stickers": [{"id": k, "name": n, "url": url(k)} for k, n in items]} for pid, title, items in enabled_packs()]


@router.get("/v3/stickers")
def stickers_list():
    return JSONResponse({"ok": True, "packs": picker()}, headers={"Cache-Control": "private, max-age=300"})
