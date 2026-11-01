"""Управление школой из консоли сервера.

  python -m school.manage teacher            — создать учителя или сменить ему пароль (пароль спросит, на экран не выводится)
  python -m school.manage teacher --login rubl
  python -m school.manage schedule --start 10:00 — вставить расписание занятий с сестрой (заменяет текущее)
"""
import argparse
import getpass
import sys

from . import config
from . import db as m
from .core import hash_password


def teacher(login, password=None):
    m.init()
    db = m.SessionLocal()
    try:
        login = login.strip().lower()
        if not password:
            password = getpass.getpass(f"Пароль для учителя «{login}»: ")
            if password != getpass.getpass("Ещё раз: "):
                print("Пароли не совпали"); return 1
        if len(password) < 4:
            print("Пароль слишком короткий"); return 1
        u = db.query(m.User).filter_by(login=login).first()
        if u and u.role != "teacher":
            print(f"Логин «{login}» уже занят учеником"); return 1
        if not u:
            # учитель один: если был другой — переименовываем его
            u = db.query(m.User).filter_by(role="teacher").first() or m.User(role="teacher", name="Учитель")
            u.login = login
            db.add(u)
        u.pw_hash = hash_password(password)
        u.active = True
        db.query(m.Session).filter_by(user_id=u.id).delete() if u.id else None
        db.commit()
        print(f"Готово: войдите на {config.SITE_URL}/login с логином «{login}»")
        return 0
    finally:
        db.close()


# Расписание занятий с сестрой (присланное 01.11.2026): уроки «предмет, минуты», None — перерыв (минуты).
# Пн–Чт идут по кругу: Пн как пятница, Вт как суббота, Ср как воскресенье, Чт снова как пятница.
_FRI = [("Чистописание", 20), ("Русский язык", 25), (None, 15), ("Английский язык", 20), ("Физика", 25), (None, 15), ("Литература", 20)]
_SAT = [("Чистописание", 20), ("Русский язык", 25), (None, 15), ("Физика", 20), ("Математика", 15), (None, 15), ("Химия", 10), ("Литература", 25)]
_SUN = [("Чистописание", 20), ("Русский язык", 25), (None, 15), ("Физика", 25), ("Английский язык", 20), ("Окружающий мир", 10), (None, 15), ("Литература", 25)]
SISTER_PLAN = {0: _FRI, 1: _SAT, 2: _SUN, 3: _FRI, 4: _FRI, 5: _SAT, 6: _SUN}


def plan_bells(day, start):
    """Время уроков дня подряд от start («10:00»), с перерывами между ними."""
    h, mnt = map(int, start.split(":"))
    t = h * 60 + mnt
    out = []
    for subject, minutes in day:
        if subject:
            out.append(f"{t // 60:02d}:{t % 60:02d}–{(t + minutes) // 60:02d}:{(t + minutes) % 60:02d}")
        t += minutes
    return out


def schedule(start="10:00", plan=None):
    """Заменяет расписание на plan (по умолчанию — SISTER_PLAN): создаёт недостающие предметы, ставит уроки и звонки каждого дня."""
    from .core import COLORS, put_setting
    plan = plan or SISTER_PLAN
    m.init()
    db = m.SessionLocal()
    try:
        subjects = {s.name.lower(): s for s in db.query(m.Subject)}
        for day in plan.values():
            for name, _ in day:
                if name and name.lower() not in subjects:
                    n = len(subjects)
                    s = m.Subject(name=name, color=COLORS[n % len(COLORS)], position=n)
                    db.add(s)
                    db.flush()
                    subjects[name.lower()] = s
                elif name and subjects[name.lower()].archived:
                    subjects[name.lower()].archived = False
        db.query(m.Lesson).delete()
        for wd, day in plan.items():
            for num, (name, _) in enumerate([x for x in day if x[0]], 1):
                db.add(m.Lesson(weekday=wd, num=num, subject_id=subjects[name.lower()].id, room=""))
        put_setting(db, "bells_day", {str(wd): (plan_bells(day, start) + [""] * 8)[:8] for wd, day in plan.items()})
        db.commit()
        print(f"Готово: расписание на все 7 дней, начало в {start}. Посмотреть: {config.SITE_URL}/t/schedule")
        return 0
    finally:
        db.close()


def main(argv=None):
    p = argparse.ArgumentParser(prog="school.manage")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("teacher")
    t.add_argument("--login", default=config.TEACHER_LOGIN)
    s = sub.add_parser("schedule")
    s.add_argument("--start", default="10:00", help="во сколько начинается первый урок, например 10:00")
    a = p.parse_args(argv)
    if a.cmd == "teacher":
        return teacher(a.login)
    if a.cmd == "schedule":
        return schedule(a.start)


if __name__ == "__main__":
    sys.exit(main())
