from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import current_user, login_redirect, render
from services import gamification, social

router = APIRouter()


@router.get("/tasks")
def tasks_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return login_redirect(request)
    raffle = gamification.current_raffle(db)
    entry = db.query(models.RaffleEntry).filter_by(raffle_id=raffle.id, user_id=user.id).first()
    total_tickets = sum(e.tickets or 0 for e in db.query(models.RaffleEntry).filter_by(raffle_id=raffle.id))
    challenge = db.query(models.WeeklyChallenge).filter(models.WeeklyChallenge.is_active == True,
                                                        models.WeeklyChallenge.week_end > datetime.utcnow()).first()
    my_challenge = None
    if challenge:
        my_challenge = db.query(models.UserWeeklyChallenge).filter_by(challenge_id=challenge.id, user_id=user.id).first()
    last_raffle = (db.query(models.WeeklyRaffle).filter(models.WeeklyRaffle.is_finished == True)
                   .order_by(models.WeeklyRaffle.created_at.desc()).first())
    leaderboard = db.query(models.User).filter(models.User.is_blocked == False).order_by(models.User.weekly_points.desc()).limit(5).all()
    return render(request, db, "tasks.html", raffle=raffle, my_tickets=entry.tickets if entry else 0, total_tickets=total_tickets,
                  challenge=challenge, my_challenge=my_challenge, last_raffle=last_raffle, leaderboard=leaderboard,
                  level=gamification.level_progress(user))


@router.get("/leaderboard")
def leaderboard_page(request: Request, by: str = "total", scope: str = "all", db: Session = Depends(get_db)):
    col = {"total": models.User.total_points, "weekly": models.User.weekly_points, "streak": models.User.streak_days,
           "level": models.User.level}.get(by, models.User.total_points)
    user = current_user(request, db)
    uq = db.query(models.User).filter(models.User.is_blocked == False)
    if scope == "friends" and user:  # рейтинг среди тех, на кого вы подписаны
        uq = uq.filter(models.User.id.in_(social.following_ids(db, user) | {user.id}))
    else:
        scope = "all"
    users = uq.order_by(col.desc()).limit(100).all()
    my_rank = None
    if user:
        mine = getattr(user, col.key) or 0
        my_rank = db.query(models.User).filter(col > mine, models.User.is_blocked == False).count() + 1
    if scope == "friends" and user:
        my_rank = next((i + 1 for i, u in enumerate(users) if u.id == user.id), None)
    return render(request, db, "leaderboard.html", users=users, by=by if by in ("total", "weekly", "streak", "level") else "total",
                  my_rank=my_rank, scope=scope)


@router.get("/achievements")
def achievements_page(request: Request, username: str = "", db: Session = Depends(get_db)):
    user = current_user(request, db)
    target = user
    if username:
        target = db.query(models.User).filter_by(username=username).first() or user
    if not target:
        return login_redirect(request)
    earned = {ua.achievement_id: ua.earned_at for ua in db.query(models.UserAchievement).filter_by(user_id=target.id)}
    all_ach = db.query(models.Achievement).filter(models.Achievement.code != "videographer").order_by(models.Achievement.points_reward.asc()).all()
    return render(request, db, "achievements.html", target=target, achievements=all_ach, earned=earned)
