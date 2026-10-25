"""Общее для всех страниц школы: вход, сеансы, настройки, четверти, средний балл, шаблоны."""
import hashlib
import json
import secrets
import time
from datetime import date, datetime, timedelta

import bcrypt
from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import config
from . import db as m

COOKIE = "school_sid"
WEEKDAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
WD_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
KINDS = [("", "Работа на уроке"), ("контрольная", "Контрольная"), ("самостоятельная", "Самостоятельная"),
         ("домашняя", "Домашняя работа"), ("устно", "Устный ответ"), ("тест", "Тест")]
WEIGHT = {"контрольная": 2, "тест": 1.5}  # контрольная весит вдвое больше обычной оценки
BEHAVIOR = {5: "Отлично", 4: "Хорошо", 3: "Нормально", 2: "Плохо", 1: "Очень плохо"}
COLORS = ["#1f6fb8", "#e0475a", "#3c9a5f", "#f2b630", "#8a5cd6", "#e07a2f", "#1fa6a6", "#d6589a", "#5d6b7a", "#6f8f2f"]
DEFAULT_BELLS = ["08:30–09:15", "09:25–10:10", "10:25–11:10", "11:25–12:10", "12:20–13:05", "13:15–14:00", "14:10–14:55", "15:05–15:50"]

templates = Jinja2Templates(directory=f"{config.BASE}/templates")


# ---------------------------------------------------------------- пароли и сеансы
def hash_password(pw):
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt()).decode()


def check_password(pw, hashed):
    try:
        return bool(hashed) and bcrypt.checkpw(pw.encode()[:72], hashed.encode())
    except ValueError:
        return False


def _th(token):
    return hashlib.sha256(f"{config.SECRET_KEY}:{token}".encode()).hexdigest()


def start_session(db, user, request, resp):
    token = secrets.token_urlsafe(32)
    db.add(m.Session(user_id=user.id, token_hash=_th(token), device=(request.headers.get("user-agent") or "")[:120]))
    user.last_seen = datetime.utcnow()
    db.commit()
    resp.set_cookie(COOKIE, token, max_age=config.SESSION_DAYS * 86400, httponly=True, samesite="lax", secure=config.COOKIE_SECURE)
    return resp


def current_user(request, db):
    if hasattr(request.state, "user"):
        return request.state.user
    user = None
    token = request.cookies.get(COOKIE)
    if token:
        s = db.query(m.Session).filter_by(token_hash=_th(token)).first()
        if s and datetime.utcnow() - s.created_at < timedelta(days=config.SESSION_DAYS):
            u = db.get(m.User, s.user_id)
            if u and u.active:
                user = u
                now = datetime.utcnow()
                if not s.last_seen or (now - s.last_seen).total_seconds() > 120:
                    s.last_seen = u.last_seen = now
                    db.commit()
    request.state.user = user
    return user


def end_session(db, request):
    token = request.cookies.get(COOKIE)
    if token:
        db.query(m.Session).filter_by(token_hash=_th(token)).delete()
        db.commit()


# простой ограничитель попыток входа: не больше 8 за 10 минут с одного адреса
_hits = {}


def rate_ok(key, limit=8, window=600):
    now = time.time()
    arr = [t for t in _hits.get(key, []) if now - t < window]
    if len(arr) >= limit:
        _hits[key] = arr
        return False
    arr.append(now)
    _hits[key] = arr
    return True


# ---------------------------------------------------------------- настройки
def setting(db, key, default=""):
    row = db.get(m.Setting, key)
    if not row:
        return default
    try:
        return json.loads(row.value)
    except ValueError:
        return default


def put_setting(db, key, value):
    row = db.get(m.Setting, key) or m.Setting(key=key)
    row.value = json.dumps(value, ensure_ascii=False)
    db.merge(row)


def school_name(db):
    return setting(db, "school_name", "Моя школа")


def bells(db):
    return setting(db, "bells", DEFAULT_BELLS)


# ---------------------------------------------------------------- даты, четверти, оценки
def today():
    # сервер работает по UTC, школа — по Москве
    return (datetime.utcnow() + timedelta(hours=3)).date()


def school_year_start(d=None):
    d = d or today()
    return date(d.year if d.month >= 9 else d.year - 1, 9, 1)


def terms(d=None):
    """Четверти текущего учебного года: [(номер, начало, конец)]."""
    y = school_year_start(d).year
    return [(1, date(y, 9, 1), date(y, 10, 31)), (2, date(y, 11, 1), date(y, 12, 31)),
            (3, date(y + 1, 1, 1), date(y + 1, 3, 31)), (4, date(y + 1, 4, 1), date(y + 1, 8, 31))]


def current_term(d=None):
    d = d or today()
    for n, a, b in terms(d):
        if a <= d <= b:
            return n
    return 1


def period(term):
    """Границы выбранного периода: номер четверти 1–4 или «year»."""
    ts = terms()
    if term == "year":
        return ts[0][1], ts[-1][2]
    n = int(term) if str(term).isdigit() and 1 <= int(term) <= 4 else current_term()
    _, a, b = ts[n - 1]
    return a, b


def average(grades):
    tot = w = 0.0
    for g in grades:
        k = WEIGHT.get(getattr(g, "kind", ""), 1)
        tot += g.value * k
        w += k
    return round(tot / w, 2) if w else None


def human_date(d):
    if not d:
        return ""
    t = today()
    if d == t:
        return "сегодня"
    if d == t + timedelta(days=1):
        return "завтра"
    if d == t - timedelta(days=1):
        return "вчера"
    s = f"{d.day} {MONTHS[d.month - 1]}"
    if d.weekday() < 6:
        s = f"{WD_SHORT[d.weekday()]}, {s}"
    return s


def next_lesson_date(db, subject_id, after=None):
    """Ближайший день после [after], когда по расписанию есть этот предмет (для срока домашнего задания)."""
    days = {l.weekday for l in db.query(m.Lesson).filter_by(subject_id=subject_id)}
    d = (after or today()) + timedelta(days=1)
    if not days:
        return d
    for _ in range(14):
        if d.weekday() in days:
            return d
        d += timedelta(days=1)
    return d


def grade_class(v):
    return {5: "g5", 4: "g4", 3: "g3", 2: "g2", 1: "g1"}.get(int(round(v)) if v else 0, "")


# ---------------------------------------------------------------- ответы
def wants_json(request):
    return request.headers.get("x-requested-with") == "fetch" or "application/json" in request.headers.get("accept", "")


def redirect(url, status=303):
    return RedirectResponse(url, status_code=status)


def jerr(msg, status=400):
    return JSONResponse({"ok": False, "error": msg}, status_code=status)


def render(request, db, name, **ctx):
    user = current_user(request, db)
    unread = 0
    if user:
        if user.is_teacher:
            unread = db.query(m.Message).filter_by(from_teacher=False, read=False).count()
        else:
            unread = db.query(m.Message).filter_by(student_id=user.id, from_teacher=True, read=False).count()
    base = dict(request=request, user=user, school=school_name(db), unread=unread, path=request.url.path,
                human_date=human_date, msk=lambda dt: (dt + timedelta(hours=3)).strftime("%d.%m в %H:%M") if dt else "", WD=WEEKDAYS, WD_SHORT=WD_SHORT, BEHAVIOR=BEHAVIOR, KINDS=dict(KINDS), grade_class=grade_class,
                today=today())
    base.update(ctx)
    return templates.TemplateResponse(request, name, base)
