"""Люди 3.0: ежедневный сундук."""
from datetime import datetime, timedelta

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from deps import current_user, json_error
from services import gamification

from . import models as m
from .common import router, today


# ---------------------------------------------------------------- ежедневный сундук
REWARDS = [5, 10, 15, 20, 25, 30, 50]  # 7-й день подряд — большой приз, дальше цикл


def chest_state(user):
    """Можно ли сегодня открыть сундук, и какая награда ждёт."""
    if not user:
        return None
    db = SessionLocal()
    try:
        row = db.get(m.DailyChest, user.id)
        t = today(user)
        yest = (datetime.strptime(t, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        streak = (row.streak if row and row.last_day == yest else 0) if not (row and row.last_day == t) else row.streak
        return {"open": bool(row and row.last_day == t), "streak": streak, "reward": REWARDS[streak % len(REWARDS)],
                "day": streak % len(REWARDS) + 1}
    finally:
        db.close()


@router.post("/v3/chest")
def chest_open(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return json_error("auth", 401)
    t = today(user)
    yest = (datetime.strptime(t, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    row = db.get(m.DailyChest, user.id)
    if row and row.last_day == t:
        return json_error("Сундук уже открыт — приходите завтра")
    if not row:
        row = m.DailyChest(user_id=user.id, streak=0, total=0)
        db.add(row)
    streak = row.streak if row.last_day == yest else 0
    reward = REWARDS[streak % len(REWARDS)]
    row.streak, row.last_day, row.total = streak + 1, t, (row.total or 0) + reward
    gamification.add_points(user, db, reward)
    db.commit()
    return JSONResponse({"ok": True, "reward": reward, "streak": row.streak})
