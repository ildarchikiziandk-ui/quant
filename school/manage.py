"""Управление школой из консоли сервера.

  python -m school.manage teacher            — создать учителя или сменить ему пароль (пароль спросит, на экран не выводится)
  python -m school.manage teacher --login rubl
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


def main(argv=None):
    p = argparse.ArgumentParser(prog="school.manage")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("teacher")
    t.add_argument("--login", default=config.TEACHER_LOGIN)
    a = p.parse_args(argv)
    if a.cmd == "teacher":
        return teacher(a.login)


if __name__ == "__main__":
    sys.exit(main())
