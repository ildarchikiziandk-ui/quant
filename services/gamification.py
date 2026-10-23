"""Очки, уровни, стрики, ежедневные задания, недельные челленджи и достижения."""
import random
from datetime import date, datetime, timedelta

import config
import models
from services import prefs


def level_for(points):
    return max(1, (points or 0) // config.POINTS_PER_LEVEL + 1)


def level_progress(user):
    pts = user.total_points or 0
    return {"current": pts % config.POINTS_PER_LEVEL, "need": config.POINTS_PER_LEVEL,
            "pct": int((pts % config.POINTS_PER_LEVEL) / config.POINTS_PER_LEVEL * 100)}


def add_points(user, db, points):
    if not user or not points:
        return
    from services import plus
    points = plus.points(user, points)
    user.daily_points = (user.daily_points or 0) + points
    user.weekly_points = (user.weekly_points or 0) + points
    user.total_points = (user.total_points or 0) + points
    new_level = level_for(user.total_points)
    if new_level > (user.level or 1):
        if prefs.get(user, "notify_achievements"):
            db.add(models.Notification(user_id=user.id, type="level", text=f"Новый уровень: {new_level}"))
    user.level = new_level
    if (user.total_points or 0) >= 1000:
        check_achievement(user, db, "rich")


def complete_task(user, db, task_type):
    if not user:
        return
    today = date.today().isoformat()
    task = db.query(models.DailyTask).filter(models.DailyTask.task_type == task_type, models.DailyTask.is_active == True).first()
    if task:
        ut = db.query(models.UserDailyTask).filter_by(user_id=user.id, task_id=task.id, date=today).first()
        if not ut:
            ut = models.UserDailyTask(user_id=user.id, task_id=task.id, progress=0, date=today)
            db.add(ut)
            db.flush()
        if not ut.is_completed:
            ut.progress = (ut.progress or 0) + 1
            if ut.progress >= (task.target_count or 1):
                ut.is_completed = True
                ut.completed_at = datetime.utcnow()
                add_points(user, db, task.points)
                _add_raffle_ticket(user, db)
    _progress_challenge(user, db, task_type)
    db.commit()


def _progress_challenge(user, db, task_type):
    now = datetime.utcnow()
    ch = db.query(models.WeeklyChallenge).filter(models.WeeklyChallenge.is_active == True, models.WeeklyChallenge.task_type == task_type,
                                                 models.WeeklyChallenge.week_end > now).first()
    if not ch:
        return
    uc = db.query(models.UserWeeklyChallenge).filter_by(user_id=user.id, challenge_id=ch.id).first()
    if not uc:
        uc = models.UserWeeklyChallenge(user_id=user.id, challenge_id=ch.id, progress=0)
        db.add(uc)
        db.flush()
    if uc.is_completed:
        return
    uc.progress = (uc.progress or 0) + 1
    if uc.progress >= (ch.target_count or 1):
        uc.is_completed = True
        uc.completed_at = now
        add_points(user, db, ch.points)
        if prefs.get(user, "notify_achievements"):
            db.add(models.Notification(user_id=user.id, type="achievement", text=f"Челлендж выполнен: {ch.title}"))


def current_raffle(db):
    raffle = db.query(models.WeeklyRaffle).filter(models.WeeklyRaffle.is_finished == False).order_by(models.WeeklyRaffle.created_at.desc()).first()
    if not raffle:
        now = datetime.utcnow()
        raffle = models.WeeklyRaffle(week_start=now, week_end=now + timedelta(days=7), prize=f"{config.BRAND_PLUS} на 30 дней")
        db.add(raffle)
        db.commit()
    return raffle


def _add_raffle_ticket(user, db):
    if user.is_owner:  # владелец в розыгрышах не участвует
        return
    raffle = current_raffle(db)
    entry = db.query(models.RaffleEntry).filter_by(raffle_id=raffle.id, user_id=user.id).first()
    if entry:
        entry.tickets = (entry.tickets or 0) + 1
    else:
        db.add(models.RaffleEntry(raffle_id=raffle.id, user_id=user.id, tickets=1))
        db.flush()


def draw_raffle(db, raffle):
    entries = db.query(models.RaffleEntry).filter_by(raffle_id=raffle.id).all()
    raffle.is_finished = True
    if entries:
        pool = [e.user for e in entries for _ in range(max(1, e.tickets or 1)) if e.user and not e.user.is_owner]
        winner = random.SystemRandom().choice(pool) if pool else None
        if winner:
            raffle.winner_id = winner.id
            grant_plus(winner, raffle.prize_days or 30)
            if prefs.get(winner, "notify_raffle"):
                db.add(models.Notification(user_id=winner.id, type="raffle", text=f"Ты выиграл розыгрыш: {raffle.prize}!"))
    db.commit()
    return raffle


def grant_plus(user, days):
    now = datetime.utcnow()
    start = user.plus_until if (user.is_plus and user.plus_until and user.plus_until > now) else now
    user.is_plus = True
    user.plus_until = start + timedelta(days=days)


def _shield_ready(user):
    from services import plus
    if not plus.active(user):
        return False
    last = user.plus_shield_date or ""
    return not last or last <= (date.today() - timedelta(days=plus.SHIELD_DAYS)).isoformat()


def update_streak(user, db):
    today = date.today().isoformat()
    if user.last_streak_date == today:
        return False
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    missed = 0
    if user.last_streak_date and user.last_streak_date != yesterday:
        try:
            missed = (date.today() - date.fromisoformat(user.last_streak_date)).days - 1
        except ValueError:
            missed = 0
    if user.last_streak_date == yesterday:
        user.streak_days = (user.streak_days or 0) + 1
    elif 0 < missed <= (user.streak_freezes or 0):  # заморозка стрика: пропущенные дни не обнуляют серию
        user.streak_freezes -= missed
        user.streak_days = (user.streak_days or 0) + 1
        if prefs.get(user, "notify_achievements"):
            db.add(models.Notification(user_id=user.id, type="system", text=f"Заморозка спасла ваш стрик (пропущено дней: {missed})"))
    elif missed == 1 and _shield_ready(user):  # Nuvora+: один пропуск в неделю прощается
        user.plus_shield_date = today
        user.streak_days = (user.streak_days or 0) + 1
        if prefs.get(user, "notify_achievements"):
            db.add(models.Notification(user_id=user.id, type="streak", text="Защита стрика Nuvora+ сохранила вашу серию"))
    else:
        user.streak_days = 1
    user.last_streak_date = today
    user.daily_points = 0
    db.commit()
    complete_task(user, db, "login")
    for days, code in ((3, "streak_3"), (7, "streak_7"), (30, "streak_30")):
        if user.streak_days >= days:
            check_achievement(user, db, code)
    db.commit()
    return True


def get_daily_tasks(user, db):
    if not user:
        return []
    today = date.today().isoformat()
    tasks = db.query(models.DailyTask).filter(models.DailyTask.is_active == True).all()
    existing = {ut.task_id: ut for ut in db.query(models.UserDailyTask).filter_by(user_id=user.id, date=today).all()}
    result, created = [], False
    for task in tasks:
        ut = existing.get(task.id)
        if not ut:
            ut = models.UserDailyTask(user_id=user.id, task_id=task.id, progress=0, date=today)
            db.add(ut)
            created = True
        ut.task = task
        result.append(ut)
    if created:
        db.commit()
    return result


def check_achievement(user, db, code):
    ach = db.query(models.Achievement).filter_by(code=code).first()
    if not ach:
        return False
    if db.query(models.UserAchievement).filter_by(user_id=user.id, achievement_id=ach.id).first():
        return False
    db.add(models.UserAchievement(user_id=user.id, achievement_id=ach.id))
    if prefs.get(user, "notify_achievements"):
        db.add(models.Notification(user_id=user.id, type="achievement", text=f"Получено достижение: {ach.name}"))
    db.flush()
    add_points(user, db, ach.points_reward)
    return True
