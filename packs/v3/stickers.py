"""Стикеры «Кит Нуви»: картинки лежат в static/stickers/nuvi (встроены в приложение, не занимают место на сервере).
В сообщении стикер — метка [[v3:st:имя]]. Картинки рисует tools/stickers_gen.py."""

PACK = [
    ("privet", "Привет!"), ("spasibo", "Спасибо"), ("lyublyu", "Люблю"), ("haha", "Ха-ха"),
    ("ok", "Окей"), ("ura", "Ура!"), ("grust", "Грущу"), ("zlyus", "Злюсь"),
    ("vau", "Вау!"), ("splyu", "Сплю"), ("kofe", "Кофе?"), ("ogon", "Огонь"),
    ("obnimayu", "Обнимаю"), ("dumayu", "Думаю…"), ("zhdu", "Жду"), ("poka", "Пока!"),
    ("pshikalka", "Пшикалка"),
]
NAMES = dict(PACK)


def url(name):
    return f"/static/stickers/nuvi/{name}.webp"  # картинки без версии: встроены в приложение (services/assets.STABLE)


def from_marker(content):
    """Имя стикера из метки или None."""
    if content and content.startswith("[[v3:st:") and content.endswith("]]"):
        name = content[8:-2]
        return name if name in NAMES else None
    return None


def allowed_text(content):
    """Служебные метки [[v3:…]] вручную отправлять нельзя (кроме стикеров) — иначе можно подделать чужой опрос или звонок."""
    return not (content or "").startswith("[[v3:") or from_marker(content) is not None


def picker():
    return [{"id": k, "name": n, "url": url(k)} for k, n in PACK]



from fastapi.responses import JSONResponse  # noqa: E402

from .common import router  # noqa: E402


@router.get("/v3/stickers")
def stickers_list():
    return JSONResponse({"ok": True, "stickers": picker()})
