"""Школа: электронный дневник. Учитель ведёт предметы, расписание, оценки, поведение и домашние задания,
ученик видит всё это в своём кабинете; учитель и ученик переписываются.

Запуск: uvicorn school.app:app --port 8010
"""
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from . import appfile, config
from . import db as m
from .core import (BEHAVIOR, COLORS, KINDS, average, bells, check_password, current_term, current_user,
                   end_session, hash_password, jerr, next_lesson_date, period, put_setting, rate_ok, redirect, render,
                   school_name, start_session, today, wants_json)

app = FastAPI(title="Школа", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=f"{config.BASE}/static"), name="static")
app.include_router(appfile.router)
LOGIN_RE = re.compile(r"^[a-z0-9_.-]{3,40}$")


@app.on_event("startup")
def _startup():
    m.init()


@app.middleware("http")
async def guard(request: Request, call_next):
    # запросы, меняющие данные, — только со своего сайта (защита от подделки запросов)
    if request.method in ("POST", "PUT", "DELETE"):
        origin = request.headers.get("origin") or request.headers.get("referer")
        if origin:
            host = urlparse(origin).netloc.split(":")[0]
            own = (request.headers.get("host") or "").split(":")[0]
            if host and host != own:
                return PlainTextResponse("Запрос с чужого сайта отклонён", status_code=403)
    resp = await call_next(request)
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


def _need(request, db, role):
    u = current_user(request, db)
    if not u or u.role != role:
        return None
    return u


def _back(request, fallback):
    ref = request.headers.get("referer") or ""
    return ref if urlparse(ref).netloc == request.headers.get("host") else fallback


def _parse_date(s, default=None):
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return default


def _students(db):
    return db.query(m.User).filter_by(role="student").order_by(m.User.active.desc(), m.User.name).all()


def _subjects(db, archived=False):
    q = db.query(m.Subject)
    if not archived:
        q = q.filter_by(archived=False)
    return q.order_by(m.Subject.position, m.Subject.name).all()


# ================================================================ вход
@app.get("/")
def root(request: Request, db: Session = Depends(m.get_db)):
    u = current_user(request, db)
    if not u:
        return redirect("/login")
    return redirect("/t" if u.is_teacher else "/s")


@app.get("/login")
def login_page(request: Request, db: Session = Depends(m.get_db)):
    if current_user(request, db):
        return redirect("/")
    return render(request, db, "login.html")


@app.post("/login")
def login(request: Request, login: str = Form(""), password: str = Form(""), db: Session = Depends(m.get_db)):
    ident = login.strip().lower()
    ip = request.client.host if request.client else "?"
    if not rate_ok(f"login:{ip}"):
        return render(request, db, "login.html", error="Слишком много попыток. Подождите 10 минут.", login=ident)
    u = db.query(m.User).filter(func.lower(m.User.login) == ident).first()
    if not u or not u.active or not check_password(password, u.pw_hash):
        return render(request, db, "login.html", error="Неверный логин или пароль", login=ident)
    return start_session(db, u, request, redirect("/"))


@app.post("/logout")
def logout(request: Request, db: Session = Depends(m.get_db)):
    end_session(db, request)
    resp = redirect("/login")
    resp.delete_cookie("school_sid")
    return resp


# ================================================================ учитель
@app.get("/t")
def teacher_home(request: Request, db: Session = Depends(m.get_db)):
    me = _need(request, db, "teacher")
    if not me:
        return redirect("/login")
    t = today()
    students = [s for s in _students(db) if s.active]
    a, b = period(current_term())
    cards = []
    for s in students:
        gs = db.query(m.Grade).filter(m.Grade.student_id == s.id, m.Grade.date >= a, m.Grade.date <= b).all()
        beh = db.query(m.Behavior).filter_by(student_id=s.id).order_by(m.Behavior.date.desc(), m.Behavior.id.desc()).first()
        unread = db.query(m.Message).filter_by(student_id=s.id, from_teacher=False, read=False).count()
        cards.append({"s": s, "avg": average(gs), "n": len(gs), "beh": beh, "unread": unread})
    lessons = db.query(m.Lesson).filter_by(weekday=t.weekday()).order_by(m.Lesson.num).all() if t.weekday() < 6 else []
    hw_soon = db.query(m.Homework).filter(m.Homework.due >= t, m.Homework.due <= t + timedelta(days=2)).order_by(m.Homework.due).all()
    return render(request, db, "t_home.html", cards=cards, lessons=lessons, bells=bells(db), hw_soon=hw_soon,
                  no_subjects=not _subjects(db), term=current_term())


# ---------------------------------------------------------------- ученики
@app.get("/t/students")
def students_page(request: Request, ok: str = "", err: str = "", db: Session = Depends(m.get_db)):
    if not _need(request, db, "teacher"):
        return redirect("/login")
    return render(request, db, "t_students.html", students=_students(db), ok=ok, err=err)


@app.post("/t/students/new")
def student_new(request: Request, name: str = Form(""), login: str = Form(""), password: str = Form(""), db: Session = Depends(m.get_db)):
    if not _need(request, db, "teacher"):
        return redirect("/login")
    name, login = name.strip()[:80], login.strip().lower()
    if not name:
        return redirect("/t/students?err=Укажите имя ученика")
    if not LOGIN_RE.match(login):
        return redirect("/t/students?err=Логин: 3–40 символов — латиница, цифры, точка, _ или -")
    if len(password) < 4:
        return redirect("/t/students?err=Пароль — не короче 4 символов")
    if db.query(m.User).filter(func.lower(m.User.login) == login).first():
        return redirect("/t/students?err=Такой логин уже занят")
    db.add(m.User(role="student", login=login, name=name, pw_hash=hash_password(password)))
    db.commit()
    return redirect(f"/t/students?ok=Ученик {name} добавлен. Логин: {login}")


@app.post("/t/students/{sid}/{act}")
def student_act(sid: int, act: str, request: Request, password: str = Form(""), name: str = Form(""), db: Session = Depends(m.get_db)):
    if not _need(request, db, "teacher"):
        return redirect("/login")
    s = db.get(m.User, sid)
    if not s or s.role != "student":
        return redirect("/t/students")
    if act == "password":
        if len(password) < 4:
            return redirect("/t/students?err=Пароль — не короче 4 символов")
        s.pw_hash = hash_password(password)
        db.query(m.Session).filter_by(user_id=s.id).delete()
        msg = f"Новый пароль для {s.name} сохранён"
    elif act == "rename" and name.strip():
        s.name = name.strip()[:80]
        msg = "Имя изменено"
    elif act == "toggle":
        s.active = not s.active
        if not s.active:
            db.query(m.Session).filter_by(user_id=s.id).delete()
        msg = f"{s.name}: вход {'включён' if s.active else 'выключен'}"
    elif act == "delete":
        msg = f"Ученик {s.name} удалён со всеми оценками"
        db.delete(s)
    else:
        return redirect("/t/students")
    db.commit()
    return redirect(f"/t/students?ok={msg}")


# ---------------------------------------------------------------- предметы
@app.get("/t/subjects")
def subjects_page(request: Request, ok: str = "", db: Session = Depends(m.get_db)):
    if not _need(request, db, "teacher"):
        return redirect("/login")
    return render(request, db, "t_subjects.html", subjects=_subjects(db, archived=True), colors=COLORS, ok=ok)


@app.post("/t/subjects/new")
def subject_new(request: Request, name: str = Form(""), color: str = Form(""), db: Session = Depends(m.get_db)):
    if not _need(request, db, "teacher"):
        return redirect("/login")
    name = name.strip()[:60]
    if name:
        n = db.query(m.Subject).count()
        db.add(m.Subject(name=name, color=color if re.fullmatch(r"#[0-9a-fA-F]{6}", color or "") else COLORS[n % len(COLORS)], position=n))
        db.commit()
    return redirect(f"/t/subjects?ok=Предмет «{name}» создан" if name else "/t/subjects")


@app.post("/t/subjects/{sid}/{act}")
def subject_act(sid: int, act: str, request: Request, name: str = Form(""), color: str = Form(""), note: str = Form(""), db: Session = Depends(m.get_db)):
    if not _need(request, db, "teacher"):
        return redirect("/login")
    sub = db.get(m.Subject, sid)
    if not sub:
        return redirect("/t/subjects")
    if act == "save":
        sub.name = name.strip()[:60] or sub.name
        if re.fullmatch(r"#[0-9a-fA-F]{6}", color or ""):
            sub.color = color
        sub.teacher_note = note.strip()[:200]
    elif act == "archive":
        sub.archived = not sub.archived
    elif act == "delete":
        db.delete(sub)
    elif act in ("up", "down"):
        subs = _subjects(db, archived=True)
        i = next(i for i, x in enumerate(subs) if x.id == sub.id)
        j = i - 1 if act == "up" else i + 1
        if 0 <= j < len(subs):
            subs[i], subs[j] = subs[j], subs[i]
        for k, x in enumerate(subs):
            x.position = k
    db.commit()
    return redirect("/t/subjects")


# ---------------------------------------------------------------- расписание
@app.get("/t/schedule")
def schedule_edit(request: Request, ok: str = "", db: Session = Depends(m.get_db)):
    if not _need(request, db, "teacher"):
        return redirect("/login")
    grid = {(l.weekday, l.num): l for l in db.query(m.Lesson).all()}
    return render(request, db, "t_schedule.html", grid=grid, subjects=_subjects(db), bells=bells(db), ok=ok, day=today().weekday() if today().weekday() < 6 else 0)


@app.post("/t/schedule")
async def schedule_save(request: Request, db: Session = Depends(m.get_db)):
    if not _need(request, db, "teacher"):
        return redirect("/login")
    f = await request.form()
    subs = {s.id for s in _subjects(db, archived=True)}
    db.query(m.Lesson).delete()
    for wd in range(6):
        for num in range(1, 9):
            v = f.get(f"s_{wd}_{num}") or ""
            if v.isdigit() and int(v) in subs:
                db.add(m.Lesson(weekday=wd, num=num, subject_id=int(v), room=(f.get(f"r_{wd}_{num}") or "").strip()[:30]))
    new_bells = [(f.get(f"bell_{i}") or "").strip()[:20] for i in range(1, 9)]
    put_setting(db, "bells", new_bells)
    db.commit()
    return redirect("/t/schedule?ok=Расписание сохранено")


# ---------------------------------------------------------------- журнал: оценки
@app.get("/t/journal")
def journal(request: Request, student: int = 0, term: str = "", db: Session = Depends(m.get_db)):
    if not _need(request, db, "teacher"):
        return redirect("/login")
    students = [s for s in _students(db) if s.active]
    if not students:
        return render(request, db, "t_journal.html", students=[], st=None)
    st = next((s for s in students if s.id == student), students[0])
    term = term or str(current_term())
    a, b = period(term)
    grades = (db.query(m.Grade).filter(m.Grade.student_id == st.id, m.Grade.date >= a, m.Grade.date <= b)
              .order_by(m.Grade.date, m.Grade.id).all())
    by_sub = defaultdict(list)
    for g in grades:
        by_sub[g.subject_id].append(g)
    rows = [{"sub": s, "grades": by_sub.get(s.id, []), "avg": average(by_sub.get(s.id, []))} for s in _subjects(db)]
    return render(request, db, "t_journal.html", students=students, st=st, rows=rows, term=term, kinds=KINDS,
                  total=average(grades))


@app.post("/t/grades/new")
def grade_new(request: Request, student: int = Form(0), subject: int = Form(0), value: int = Form(0), kind: str = Form(""),
              comment: str = Form(""), day: str = Form(""), db: Session = Depends(m.get_db)):
    if not _need(request, db, "teacher"):
        return jerr("Нет доступа", 403)
    s, sub = db.get(m.User, student), db.get(m.Subject, subject)
    if not s or s.role != "student" or not sub or not 1 <= value <= 5:
        return jerr("Проверьте ученика, предмет и оценку")
    g = m.Grade(student_id=s.id, subject_id=sub.id, value=value, kind=kind if kind in dict(KINDS) else "",
                comment=comment.strip()[:300], date=_parse_date(day, today()))
    db.add(g)
    db.commit()
    if wants_json(request):
        return JSONResponse({"ok": True, "id": g.id})
    return redirect(_back(request, f"/t/journal?student={s.id}"))


@app.post("/t/grades/{gid}/delete")
def grade_delete(gid: int, request: Request, db: Session = Depends(m.get_db)):
    if not _need(request, db, "teacher"):
        return jerr("Нет доступа", 403)
    g = db.get(m.Grade, gid)
    if g:
        db.delete(g)
        db.commit()
    return JSONResponse({"ok": True}) if wants_json(request) else redirect(_back(request, "/t/journal"))


# ---------------------------------------------------------------- поведение
@app.get("/t/behavior")
def behavior_page(request: Request, student: int = 0, db: Session = Depends(m.get_db)):
    if not _need(request, db, "teacher"):
        return redirect("/login")
    students = [s for s in _students(db) if s.active]
    st = next((s for s in students if s.id == student), students[0] if students else None)
    rows = (db.query(m.Behavior).filter_by(student_id=st.id).order_by(m.Behavior.date.desc(), m.Behavior.id.desc()).limit(60).all()
            if st else [])
    return render(request, db, "t_behavior.html", students=students, st=st, rows=rows, avg_total=average(rows))


@app.post("/t/behavior/new")
def behavior_new(request: Request, student: int = Form(0), value: int = Form(0), comment: str = Form(""), day: str = Form(""),
                 db: Session = Depends(m.get_db)):
    if not _need(request, db, "teacher"):
        return redirect("/login")
    s = db.get(m.User, student)
    if s and s.role == "student" and 1 <= value <= 5:
        db.add(m.Behavior(student_id=s.id, value=value, comment=comment.strip()[:300], date=_parse_date(day, today())))
        db.commit()
    return redirect(f"/t/behavior?student={student}")


@app.post("/t/behavior/{bid}/delete")
def behavior_delete(bid: int, request: Request, db: Session = Depends(m.get_db)):
    if not _need(request, db, "teacher"):
        return redirect("/login")
    b = db.get(m.Behavior, bid)
    sid = b.student_id if b else 0
    if b:
        db.delete(b)
        db.commit()
    return redirect(f"/t/behavior?student={sid}")


# ---------------------------------------------------------------- домашние задания
@app.get("/t/homework")
def homework_page(request: Request, ok: str = "", db: Session = Depends(m.get_db)):
    if not _need(request, db, "teacher"):
        return redirect("/login")
    t = today()
    upcoming = db.query(m.Homework).filter(m.Homework.due >= t).order_by(m.Homework.due, m.Homework.id).all()
    past = db.query(m.Homework).filter(m.Homework.due < t).order_by(m.Homework.due.desc()).limit(30).all()
    done = defaultdict(set)
    for d in db.query(m.HomeworkDone).filter(m.HomeworkDone.homework_id.in_([h.id for h in upcoming + past] or [0])):
        done[d.homework_id].add(d.student_id)
    subs = _subjects(db)
    due_for = {s.id: next_lesson_date(db, s.id).isoformat() for s in subs}
    return render(request, db, "t_homework.html", upcoming=upcoming, past=past, done=done, subjects=subs, students=[s for s in _students(db) if s.active],
                  due_for=due_for, ok=ok, names={s.id: s.name for s in _students(db)})


@app.post("/t/homework/new")
def homework_new(request: Request, subject: int = Form(0), due: str = Form(""), text: str = Form(""), student: int = Form(0),
                 db: Session = Depends(m.get_db)):
    if not _need(request, db, "teacher"):
        return redirect("/login")
    sub = db.get(m.Subject, subject)
    text = text.strip()[:4000]
    if not sub or not text:
        return redirect("/t/homework?ok=Выберите предмет и напишите задание")
    st = db.get(m.User, student) if student else None
    db.add(m.Homework(subject_id=sub.id, due=_parse_date(due, next_lesson_date(db, sub.id)), text=text,
                      student_id=st.id if st and st.role == "student" else None))
    db.commit()
    return redirect("/t/homework?ok=Задание добавлено")


@app.post("/t/homework/{hid}/delete")
def homework_delete(hid: int, request: Request, db: Session = Depends(m.get_db)):
    if not _need(request, db, "teacher"):
        return redirect("/login")
    h = db.get(m.Homework, hid)
    if h:
        db.delete(h)
        db.commit()
    return redirect("/t/homework")


# ---------------------------------------------------------------- переписка (учитель)
@app.get("/t/chat")
def chats(request: Request, db: Session = Depends(m.get_db)):
    if not _need(request, db, "teacher"):
        return redirect("/login")
    rows = []
    for s in _students(db):
        last = db.query(m.Message).filter_by(student_id=s.id).order_by(m.Message.id.desc()).first()
        unread = db.query(m.Message).filter_by(student_id=s.id, from_teacher=False, read=False).count()
        rows.append({"s": s, "last": last, "unread": unread})
    rows.sort(key=lambda r: (r["last"].id if r["last"] else 0), reverse=True)
    return render(request, db, "t_chats.html", rows=rows)


@app.get("/t/chat/{sid}")
def chat_teacher(sid: int, request: Request, db: Session = Depends(m.get_db)):
    if not _need(request, db, "teacher"):
        return redirect("/login")
    s = db.get(m.User, sid)
    if not s or s.role != "student":
        return redirect("/t/chat")
    return render(request, db, "chat.html", peer=s, sid=s.id, api=f"/api/chat/{s.id}")


# ---------------------------------------------------------------- настройки
@app.get("/t/settings")
def settings_page(request: Request, ok: str = "", err: str = "", db: Session = Depends(m.get_db)):
    me = _need(request, db, "teacher")
    if not me:
        return redirect("/login")
    return render(request, db, "t_settings.html", ok=ok, err=err, me=me)


@app.post("/t/settings")
def settings_save(request: Request, school: str = Form(""), name: str = Form(""), db: Session = Depends(m.get_db)):
    me = _need(request, db, "teacher")
    if not me:
        return redirect("/login")
    if school.strip():
        put_setting(db, "school_name", school.strip()[:60])
    if name.strip():
        me.name = name.strip()[:80]
    db.commit()
    return redirect("/t/settings?ok=Сохранено")


@app.post("/t/settings/password")
def settings_password(request: Request, old: str = Form(""), new: str = Form(""), new2: str = Form(""), db: Session = Depends(m.get_db)):
    me = _need(request, db, "teacher")
    if not me:
        return redirect("/login")
    if not check_password(old, me.pw_hash):
        return redirect("/t/settings?err=Текущий пароль неверный")
    if len(new) < 6 or new != new2:
        return redirect("/t/settings?err=Новый пароль — не короче 6 символов, оба раза одинаково")
    me.pw_hash = hash_password(new)
    db.commit()
    return redirect("/t/settings?ok=Пароль изменён")


# ================================================================ ученик
def _student_data(db, s, term=None):
    a, b = period(term or current_term())
    grades = (db.query(m.Grade).filter(m.Grade.student_id == s.id, m.Grade.date >= a, m.Grade.date <= b)
              .order_by(m.Grade.date, m.Grade.id).all())
    return grades


def _hw_for(db, s, a, b):
    return (db.query(m.Homework).filter(m.Homework.due >= a, m.Homework.due <= b,
                                         or_(m.Homework.student_id == None, m.Homework.student_id == s.id))  # noqa: E711
            .order_by(m.Homework.due, m.Homework.id).all())


@app.get("/s")
def student_home(request: Request, db: Session = Depends(m.get_db)):
    me = _need(request, db, "student")
    if not me:
        return redirect("/login")
    t = today()
    # если сегодня воскресенье или уроки кончились — показываем следующий учебный день
    show = t
    while show.weekday() == 6:
        show += timedelta(days=1)
    lessons = db.query(m.Lesson).filter_by(weekday=show.weekday()).order_by(m.Lesson.num).all()
    hw = _hw_for(db, me, t, t + timedelta(days=7))
    done = {d.homework_id for d in db.query(m.HomeworkDone).filter_by(student_id=me.id)}
    hw_by_day_sub = {(h.due, h.subject_id): h for h in hw}
    new_grades = (db.query(m.Grade).filter_by(student_id=me.id).order_by(m.Grade.created_at.desc()).limit(6).all())
    beh = db.query(m.Behavior).filter_by(student_id=me.id).order_by(m.Behavior.date.desc(), m.Behavior.id.desc()).first()
    resp = render(request, db, "s_home.html", lessons=lessons, show=show, bells=bells(db), hw=[h for h in hw if h.id not in done][:5],
                  hw_map=hw_by_day_sub, done=done, new_grades=new_grades, beh=beh, avg_total=average(_student_data(db, me)))
    return resp


@app.get("/s/grades")
def student_grades(request: Request, term: str = "", db: Session = Depends(m.get_db)):
    me = _need(request, db, "student")
    if not me:
        return redirect("/login")
    term = term or str(current_term())
    grades = _student_data(db, me, term)
    by_sub = defaultdict(list)
    for g in grades:
        by_sub[g.subject_id].append(g)
    rows = [{"sub": s, "grades": by_sub.get(s.id, []), "avg": average(by_sub.get(s.id, []))} for s in _subjects(db)]
    resp = render(request, db, "s_grades.html", rows=rows, term=term, total=average(grades))
    db.query(m.Grade).filter_by(student_id=me.id, seen=False).update({"seen": True})
    db.commit()
    return resp


@app.get("/s/behavior")
def student_behavior(request: Request, db: Session = Depends(m.get_db)):
    me = _need(request, db, "student")
    if not me:
        return redirect("/login")
    rows = db.query(m.Behavior).filter_by(student_id=me.id).order_by(m.Behavior.date.desc(), m.Behavior.id.desc()).limit(100).all()
    resp = render(request, db, "s_behavior.html", rows=rows, avg_total=average(rows))
    db.query(m.Behavior).filter_by(student_id=me.id, seen=False).update({"seen": True})
    db.commit()
    return resp


@app.get("/s/homework")
def student_homework(request: Request, db: Session = Depends(m.get_db)):
    me = _need(request, db, "student")
    if not me:
        return redirect("/login")
    t = today()
    hw = _hw_for(db, me, t - timedelta(days=14), t + timedelta(days=60))
    done = {d.homework_id for d in db.query(m.HomeworkDone).filter_by(student_id=me.id)}
    days = defaultdict(list)
    for h in hw:
        if h.due >= t or h.id not in done:
            days[h.due].append(h)
    return render(request, db, "s_homework.html", days=sorted(days.items()), done=done)


@app.post("/s/homework/{hid}/done")
def homework_done(hid: int, request: Request, db: Session = Depends(m.get_db)):
    me = _need(request, db, "student")
    h = db.get(m.Homework, hid)
    if not me or not h or (h.student_id and h.student_id != me.id):
        return jerr("Задание не найдено", 404)
    row = db.query(m.HomeworkDone).filter_by(homework_id=h.id, student_id=me.id).first()
    if row:
        db.delete(row)
    else:
        db.add(m.HomeworkDone(homework_id=h.id, student_id=me.id))
    db.commit()
    return JSONResponse({"ok": True, "done": not row})


@app.get("/s/schedule")
def student_schedule(request: Request, week: int = 0, db: Session = Depends(m.get_db)):
    me = _need(request, db, "student")
    if not me:
        return redirect("/login")
    return _week(request, db, me, week, "s_schedule.html")


@app.get("/t/week")
def teacher_week(request: Request, week: int = 0, db: Session = Depends(m.get_db)):
    me = _need(request, db, "teacher")
    if not me:
        return redirect("/login")
    return _week(request, db, me, week, "s_schedule.html")


def _week(request, db, me, week, tpl):
    week = max(-20, min(week, 20))
    t = today()
    monday = t - timedelta(days=t.weekday()) + timedelta(weeks=week)
    days = []
    lessons = defaultdict(list)
    for l in db.query(m.Lesson).order_by(m.Lesson.num):
        lessons[l.weekday].append(l)
    hw = (_hw_for(db, me, monday, monday + timedelta(days=6)) if not me.is_teacher else
          db.query(m.Homework).filter(m.Homework.due >= monday, m.Homework.due <= monday + timedelta(days=6)).all())
    hw_map = defaultdict(list)
    for h in hw:
        hw_map[(h.due, h.subject_id)].append(h)
    grade_map = defaultdict(list)
    if not me.is_teacher:
        for g in db.query(m.Grade).filter(m.Grade.student_id == me.id, m.Grade.date >= monday, m.Grade.date <= monday + timedelta(days=6)):
            grade_map[(g.date, g.subject_id)].append(g)
    for i in range(6):
        d = monday + timedelta(days=i)
        days.append({"date": d, "wd": i, "lessons": lessons.get(i, [])})
    return render(request, db, tpl, days=days, week=week, monday=monday, bells=bells(db), hw_map=hw_map, grade_map=grade_map)


@app.get("/s/chat")
def chat_student(request: Request, db: Session = Depends(m.get_db)):
    me = _need(request, db, "student")
    if not me:
        return redirect("/login")
    teacher = db.query(m.User).filter_by(role="teacher").first()
    return render(request, db, "chat.html", peer=teacher, sid=me.id, api=f"/api/chat/{me.id}")


# ================================================================ переписка: общий API
def _chat_access(db, user, sid):
    if not user:
        return False
    return user.is_teacher or user.id == sid


def _msg(x):
    return {"id": x.id, "mine_t": x.from_teacher, "text": x.text, "at": (x.created_at + timedelta(hours=3)).strftime("%d.%m %H:%M"),
            "read": x.read}


@app.get("/api/chat/{sid}")
def chat_poll(sid: int, request: Request, after: int = 0, db: Session = Depends(m.get_db)):
    u = current_user(request, db)
    if not _chat_access(db, u, sid):
        return jerr("Нет доступа", 403)
    q = db.query(m.Message).filter(m.Message.student_id == sid, m.Message.id > after).order_by(m.Message.id)
    rows = q.limit(300).all() if after else list(reversed(db.query(m.Message).filter_by(student_id=sid).order_by(m.Message.id.desc()).limit(200).all()))
    # входящие — прочитаны
    db.query(m.Message).filter(m.Message.student_id == sid, m.Message.from_teacher == (not u.is_teacher), m.Message.read == False).update(  # noqa: E712
        {"read": True})
    db.commit()
    last_read = db.query(func.max(m.Message.id)).filter(m.Message.student_id == sid, m.Message.from_teacher == u.is_teacher, m.Message.read == True).scalar() or 0  # noqa: E712
    return JSONResponse({"ok": True, "me_teacher": u.is_teacher, "messages": [_msg(x) for x in rows], "read_upto": last_read})


@app.post("/api/chat/{sid}")
def chat_send(sid: int, request: Request, text: str = Form(""), db: Session = Depends(m.get_db)):
    u = current_user(request, db)
    if not _chat_access(db, u, sid):
        return jerr("Нет доступа", 403)
    s = db.get(m.User, sid)
    text = text.strip()[:4000]
    if not s or s.role != "student" or not text:
        return jerr("Пустое сообщение")
    if not rate_ok(f"msg:{u.id}", 30, 60):
        return jerr("Слишком часто", 429)
    msg = m.Message(student_id=sid, from_teacher=u.is_teacher, text=text)
    db.add(msg)
    db.commit()
    return JSONResponse({"ok": True, "message": _msg(msg)})


# ---------------------------------------------------------------- для приложения: что нового
@app.get("/api/updates")
def updates(request: Request, db: Session = Depends(m.get_db)):
    """Счётчики и последние новые события — по ним приложение показывает уведомления."""
    u = current_user(request, db)
    if not u:
        return jerr("auth", 401)
    out = {"ok": True, "role": u.role}
    if u.is_teacher:
        last = db.query(m.Message).filter_by(from_teacher=False, read=False).order_by(m.Message.id.desc()).first()
        out["messages"] = db.query(m.Message).filter_by(from_teacher=False, read=False).count()
        out["last_message"] = {"id": last.id, "text": last.text[:120], "from": (db.get(m.User, last.student_id).name if last else ""),
                               "url": f"/t/chat/{last.student_id}"} if last else None
        return JSONResponse(out)
    msgs = db.query(m.Message).filter_by(student_id=u.id, from_teacher=True, read=False).order_by(m.Message.id.desc())
    grades = db.query(m.Grade).filter_by(student_id=u.id, seen=False).order_by(m.Grade.id.desc())
    beh = db.query(m.Behavior).filter_by(student_id=u.id, seen=False).order_by(m.Behavior.id.desc())
    hw = (db.query(m.Homework).filter(or_(m.Homework.student_id == None, m.Homework.student_id == u.id))  # noqa: E711
          .order_by(m.Homework.id.desc()).first())
    lm, lg, lb = msgs.first(), grades.first(), beh.first()
    out.update({
        "messages": msgs.count(), "grades": grades.count(), "behavior": beh.count(),
        "last_message": {"id": lm.id, "text": lm.text[:120], "url": "/s/chat"} if lm else None,
        "last_grade": {"id": lg.id, "value": lg.value, "subject": lg.subject.name if lg.subject else "", "url": "/s/grades"} if lg else None,
        "last_behavior": {"id": lb.id, "value": lb.value, "label": BEHAVIOR.get(lb.value, ""), "url": "/s/behavior"} if lb else None,
        "last_homework": {"id": hw.id, "subject": hw.subject.name if hw.subject else "", "due": hw.due.isoformat(), "url": "/s/homework"} if hw else None,
    })
    return JSONResponse(out)


@app.get("/manifest.webmanifest")
def manifest(db: Session = Depends(m.get_db)):
    name = school_name(db)
    return JSONResponse({"name": name, "short_name": name[:12], "start_url": "/", "display": "standalone", "lang": "ru",
                         "background_color": "#f4f7fb", "theme_color": "#1f6fb8",
                         "icons": [{"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
                                   {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}]},
                        media_type="application/manifest+json")


@app.get("/healthz")
def healthz():
    return {"ok": True}
