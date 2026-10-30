"""Лимитированные подарки: владелец «дропает» их из админки (/admin/gifts) — с тиражом или без, и снимает с продажи.
Состояние хранится в настройках сайта (site «gift_drops»), проданные считаются по UserGift."""
from datetime import datetime

from fastapi import Depends, Request
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import current_user, log_mod, redirect, render
from services import extras

from . import site
from .common import router, s


def _owner(request, db):
    user = current_user(request, db)
    return user if user and user.is_owner else None


@router.get("/admin/gifts")
def drops_page(request: Request, db: Session = Depends(get_db), ok: str = ""):
    me = _owner(request, db)
    if not me:
        return redirect("/")
    st = extras.drops()
    rows = []
    for code, _e, name, price, month in extras.LIMITED:
        d = st.get(code) or {}
        rows.append({"code": code, "name": name, "price": price, "month": month, "on": bool(d.get("on")), "ever": bool(d.get("ever")),
                     "supply": int(d.get("supply") or 0), "sold": extras.sold(db, code), "since": d.get("since", "")})
    return render(request, db, "packs/v3/admin_gifts.html", sidebar=False, rows=rows, ok=ok, default_supply=extras.LIMITED_SUPPLY,
                  premium=extras.PREMIUM, founder=extras.FOUNDER, founder_sold=extras.sold(db, extras.FOUNDER[0]))


@router.post("/admin/gifts/{code}")
async def drops_save(code: str, request: Request, db: Session = Depends(get_db)):
    me = _owner(request, db)
    if not me or code not in extras.LIMITED_MONTH:
        return redirect("/")
    f = await request.form()
    st = dict(extras.drops())
    d = dict(st.get(code) or {})
    name = extras.GIFT_BY_CODE[code][2]
    if f.get("action") == "stop":
        d["on"] = False
        msg = f"«{name}» снят с продажи"
    else:
        try:
            supply = max(0, min(100000, int(s(f.get("supply")) or 0)))
        except ValueError:
            supply = extras.LIMITED_SUPPLY
        d.update(on=True, ever=True, supply=supply, since=datetime.utcnow().strftime("%d.%m.%Y"))
        msg = f"«{name}» в продаже" + (f", тираж {supply}" if supply else ", без ограничения тиража")
        if f.get("announce"):
            text = f"Новый лимитированный подарок — «{name}»!" + (f" Всего {supply} штук." if supply else "") + " Загляните в «Подарки»."
            ids = [u for (u,) in db.query(models.User.id).filter(models.User.is_blocked == False, models.User.id != me.id)]
            db.bulk_save_objects([models.Notification(user_id=u, type="system", text=text) for u in ids])
            msg += f", уведомления — {len(ids)} людям"
    st[code] = d
    site.put(db, "gift_drops", st)
    log_mod(db, me, "gift_drop", code, msg)
    db.commit()
    return redirect("/admin/gifts?ok=" + msg)
