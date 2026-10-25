import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="school-test-")
os.environ["SCHOOL_DATABASE_URL"] = f"sqlite:///{_tmp}/s.db"
os.environ["SCHOOL_SECRET_KEY"] = "test"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from school import app as A  # noqa: E402
from school import core  # noqa: E402
from school import db as m  # noqa: E402
from school import manage  # noqa: E402

J = {"X-Requested-With": "fetch"}


@pytest.fixture(autouse=True)
def fresh():
    m.Base.metadata.drop_all(bind=m.engine)
    m.init()
    core._hits.clear()
    yield


def client():
    return TestClient(A.app, base_url="http://school.test")


def login(c, user, pw):
    return c.post("/login", data={"login": user, "password": pw}, follow_redirects=False)


@pytest.fixture
def teacher():
    assert manage.teacher("rubl", "test-pass-1") == 0
    c = client()
    assert login(c, "rubl", "test-pass-1").headers["location"] == "/"
    return c


def _sid(name="anya"):
    s = m.SessionLocal()
    try:
        return s.query(m.User).filter_by(login=name).one().id
    finally:
        s.close()


def _sub(name):
    s = m.SessionLocal()
    try:
        return s.query(m.Subject).filter_by(name=name).one().id
    finally:
        s.close()


def test_login_and_roles(teacher):
    anon = client()
    assert anon.get("/t", follow_redirects=False).headers["location"] == "/login"
    assert "Неверный логин" in login(anon, "rubl", "wrong").text
    assert teacher.get("/t").status_code == 200
    teacher.post("/t/students/new", data={"name": "Аня Петрова", "login": "Anya", "password": "1234"})
    st = client()
    assert login(st, "anya", "1234").status_code == 303
    assert st.get("/t", follow_redirects=False).headers["location"] == "/login"  # ученик не попадает в кабинет учителя
    assert st.get("/s").status_code == 200 and "Привет, Аня" in st.get("/s").text
    # чужой сайт не может отправить форму
    assert st.post("/logout", headers={"Origin": "https://evil.example"}).status_code == 403
    # выключенный вход
    teacher.post(f"/t/students/{_sid()}/toggle")
    assert st.get("/s", follow_redirects=False).status_code == 303


def test_rate_limit():
    c = client()
    for _ in range(8):
        login(c, "x", "y")
    assert "Слишком много попыток" in login(c, "x", "y").text


def test_teacher_full_flow(teacher):
    for n in ("Математика", "Русский язык"):
        teacher.post("/t/subjects/new", data={"name": n})
    math, rus = _sub("Математика"), _sub("Русский язык")
    teacher.post("/t/students/new", data={"name": "Аня", "login": "anya", "password": "1234"})
    sid = _sid()
    # расписание: математика в понедельник первым уроком
    teacher.post("/t/schedule", data={"s_0_1": str(math), "r_0_1": "кухня", "s_2_2": str(rus), "bell_1": "09:00–09:45"})
    assert "кухня" in teacher.get("/t/schedule").text
    # оценки
    for v, kind in ((5, ""), (4, ""), (3, "контрольная")):
        assert teacher.post("/t/grades/new", data={"student": sid, "subject": math, "value": v, "kind": kind,
                                                    "day": core.today().isoformat()}, headers=J).json()["ok"]
    assert teacher.post("/t/grades/new", data={"student": sid, "subject": math, "value": 7}, headers=J).status_code == 400
    page = teacher.get(f"/t/journal?student={sid}").text
    assert "3.75" in page  # (5+4+3*2)/4
    # поведение и ДЗ
    teacher.post("/t/behavior/new", data={"student": sid, "value": 5, "comment": "умница"})
    teacher.post("/t/homework/new", data={"subject": rus, "due": "", "text": "Упражнение 12"})
    st = client()
    login(st, "anya", "1234")
    upd = st.get("/api/updates").json()
    assert upd["grades"] == 3 and upd["behavior"] == 1 and upd["last_homework"]["subject"] == "Русский язык"
    g = st.get("/s/grades").text
    assert "3.75" in g and "Математика" in g
    assert st.get("/api/updates").json()["grades"] == 0  # просмотрено
    assert "умница" in st.get("/s/behavior").text
    hw = st.get("/s/homework").text
    assert "Упражнение 12" in hw
    s = m.SessionLocal()
    hid = s.query(m.Homework).one().id
    due = s.query(m.Homework).one().due
    s.close()
    assert due.weekday() == 2  # срок — ближайшая среда, когда по расписанию русский
    assert st.post(f"/s/homework/{hid}/done", headers=J).json()["done"] is True
    assert "сделал(а): Аня" in teacher.get("/t/homework").text
    assert "Математика" in st.get("/s/schedule").text


def test_chat(teacher):
    teacher.post("/t/students/new", data={"name": "Аня", "login": "anya", "password": "1234"})
    teacher.post("/t/students/new", data={"name": "Боря", "login": "borya", "password": "1234"})
    a, b = _sid("anya"), _sid("borya")
    st = client()
    login(st, "anya", "1234")
    assert st.post(f"/api/chat/{a}", data={"text": "Здравствуйте! Не поняла задачу"}, headers=J).json()["ok"]
    assert st.post(f"/api/chat/{b}", data={"text": "чужой чат"}, headers=J).status_code == 403
    assert st.get(f"/api/chat/{b}", headers=J).status_code == 403
    assert teacher.get("/api/updates").json()["messages"] == 1
    r = teacher.get(f"/api/chat/{a}", headers=J).json()
    assert r["messages"][0]["text"].startswith("Здравствуйте") and r["me_teacher"] is True
    assert teacher.get("/api/updates").json()["messages"] == 0
    teacher.post(f"/api/chat/{a}", data={"text": "Сейчас объясню"}, headers=J)
    assert st.get("/api/updates").json()["messages"] == 1
    assert st.get(f"/api/chat/{a}?after=0", headers=J).json()["messages"][-1]["text"] == "Сейчас объясню"


def test_settings_and_password(teacher):
    teacher.post("/t/settings", data={"school": "Школа Рубля", "name": "Ильдар"})
    assert "Школа Рубля" in teacher.get("/t").text
    assert "неверный" in teacher.post("/t/settings/password", data={"old": "x", "new": "new-pass-9", "new2": "new-pass-9"}).text
    teacher.post("/t/settings/password", data={"old": "test-pass-1", "new": "new-pass-9", "new2": "new-pass-9"})
    assert login(client(), "rubl", "new-pass-9").headers["location"] == "/"


def test_pages_render(teacher):
    teacher.post("/t/subjects/new", data={"name": "Чтение"})
    teacher.post("/t/students/new", data={"name": "Аня", "login": "anya", "password": "1234"})
    for p in ("/t", "/t/students", "/t/subjects", "/t/schedule", "/t/journal", "/t/behavior", "/t/homework", "/t/chat",
              f"/t/chat/{_sid()}", "/t/settings", "/t/week", "/app", "/manifest.webmanifest"):
        assert teacher.get(p).status_code == 200, p
    assert client().get("/login").status_code == 200
