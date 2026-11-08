"""Ивенты Nuvora (8.11.2026): календарь, двойные искры, подарки один раз, адвент, Масленица, валентинки, турнир, админка."""
import datetime as dt

import models
from database import SessionLocal
from packs.v3 import events, site
from tests.conftest import make_client, register
from tests.test_app import J


def _user(name):
    s = SessionLocal()
    u = s.query(models.User).filter_by(username=name).first()
    s.close()
    return u


def _on(db_key, monkeypatch, day):
    monkeypatch.setattr(events, "today", lambda: day)
    s = SessionLocal()
    site.put(s, "events", {})
    s.commit()
    s.close()


def test_calendar():
    D = dt.date
    assert events.easter(2027) == D(2027, 5, 2)  # православная Пасха
    assert events.span("maslenitsa", 2027) == (D(2027, 3, 8), D(2027, 3, 14))
    assert events.by_calendar("x2", D(2026, 11, 7)) and not events.by_calendar("x2", D(2026, 11, 9))
    assert events.by_calendar("x2", D(2027, 6, 1))  # 1 июня — двойные искры весь день
    assert events.by_calendar("nynight", D(2027, 1, 1)) and events.by_calendar("nynight", D(2026, 12, 31))
    assert events.by_calendar("may9", D(2027, 5, 9)) and events.by_calendar("summer_end", D(2027, 8, 31))
    assert not events.by_calendar("advent", D(2026, 11, 30))


def test_double_sparks(monkeypatch):
    c = register(make_client(), "alice")
    from services import gamification
    monkeypatch.setenv("EVENTS_X2", "1")
    monkeypatch.setattr(events, "today", lambda: dt.date(2026, 11, 7))  # суббота
    s = SessionLocal()
    u = s.query(models.User).filter_by(username="alice").first()
    before = u.total_points or 0
    gamification.add_points(u, s, 10)
    assert (u.total_points or 0) - before == 20
    s.close()


def test_gift_once_and_only_when_on(monkeypatch):
    c = register(make_client(), "alice")
    monkeypatch.setattr(events, "today", lambda: dt.date(2027, 4, 23))
    assert c.post("/prazdniki/bday/gift", headers=J).status_code == 403
    monkeypatch.setattr(events, "today", lambda: dt.date(2027, 4, 24))
    pts = _user("alice").total_points or 0
    r = c.post("/prazdniki/bday/gift", headers=J).json()
    assert r["ok"] and "Nuvora+" in r["text"]
    u = _user("alice")
    assert (u.total_points or 0) - pts == 100 and u.is_plus
    assert not c.post("/prazdniki/bday/gift", headers=J).json()["ok"]
    assert "День рождения Nuvora" in c.get("/prazdniki").text
    page = c.get("/").text
    assert "ev-bday" in page and "ev-banner" in page


def test_advent(monkeypatch):
    c = register(make_client(), "alice")
    monkeypatch.setattr(events, "today", lambda: dt.date(2026, 12, 7))
    assert "adv-cell" in c.get("/advent").text
    r = c.post("/advent/open", headers=J).json()
    assert r["ok"] and r["day"] == 7 and "Nuvora+" in r["text"]
    assert not c.post("/advent/open", headers=J).json()["ok"]
    monkeypatch.setattr(events, "today", lambda: dt.date(2026, 12, 8))
    assert c.post("/advent/open", headers=J).json()["ok"]
    monkeypatch.setattr(events, "today", lambda: dt.date(2026, 11, 8))
    assert c.get("/advent", follow_redirects=False).status_code == 303


def test_maslenitsa_needs_task(monkeypatch):
    c = register(make_client(), "alice")
    monkeypatch.setattr(events, "today", lambda: dt.date(2027, 3, 9))
    r = c.post("/maslenitsa/blin", headers=J).json()
    assert not r["ok"] and "задание" in r["error"]
    monkeypatch.setattr(events, "_did_task_today", lambda db, u: True)
    assert c.post("/maslenitsa/blin", headers=J).json()["n"] == 1
    assert not c.post("/maslenitsa/blin", headers=J).json()["ok"]
    assert "🥞" in c.get("/maslenitsa").text


def test_valentine(monkeypatch):
    alice = register(make_client(), "alice")
    bob = register(make_client(), "bob")
    monkeypatch.setattr(events, "today", lambda: dt.date(2027, 2, 10))
    assert not alice.post("/valentine/send", json={"to": "bob", "text": "hi"}, headers=J).json()["ok"]
    monkeypatch.setattr(events, "today", lambda: dt.date(2027, 2, 14))
    assert alice.post("/valentine/send", json={"to": "@bob", "text": "Ты классный", "anon": 1, "card": "red"}, headers=J).json()["ok"]
    page = bob.get("/valentine").text
    assert "от тайного поклонника" in page and 'от <a href="/profile/alice"' not in page
    s = SessionLocal()
    v = s.query(events.Valentine).first()
    n = s.query(models.Notification).filter_by(user_id=_user("bob").id, type="valentine").first()
    s.close()
    assert n.from_user_id is None
    assert bob.get(f"/valentine/{v.id}.png").headers["content-type"] == "image/png"
    carol = register(make_client(), "carol")
    assert carol.get(f"/valentine/{v.id}.png").status_code == 404


def test_turnir_and_admin(monkeypatch):
    owner = register(make_client(), "owner")
    alice = register(make_client(), "alice")
    bob = register(make_client(), "bob")
    s = SessionLocal()
    a, b = _user("alice"), _user("bob")
    s.add(events.ChatGame(kind="dice", a_id=a.id, b_id=b.id, winner=a.id, created_at=dt.datetime(2027, 2, 18, 12)))
    s.commit()
    s.close()
    monkeypatch.setattr(events, "today", lambda: dt.date(2027, 2, 20))
    page = alice.get("/turnir").text
    assert "@alice" in page and "Наградить" not in page
    assert "Наградить" in owner.get("/turnir").text
    owner.post(f"/turnir/award/{a.id}")
    assert _user("alice").is_plus
    assert alice.post(f"/turnir/award/{a.id}").status_code in (303, 403)
    # админка: выключить ивент и задать день рождения
    assert alice.get("/admin/events", follow_redirects=False).status_code == 303
    owner.post("/admin/events", data={"feb23": "off", "owner_bday": "2000-07-15"})
    assert not events.is_on("feb23") and events.span("owner_bday", 2027)[0] == dt.date(2027, 7, 15)
    assert "Ваш день рождения" in owner.get("/admin/events").text
