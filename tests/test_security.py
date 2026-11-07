"""Защита сайта (7.11.2026, по чек-листу из 20 пунктов): заголовки, подделанные запросы, поддельные файлы, закрытая админка."""
import main
from tests.conftest import make_client, register
from tests.test_app import J


def test_security_headers():
    c = make_client()
    h = c.get("/login").headers
    csp = h["content-security-policy"]
    assert "script-src 'self' 'unsafe-inline'" in csp and "object-src 'none'" in csp and "frame-ancestors 'self'" in csp
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "SAMEORIGIN"


def test_csrf_without_origin_blocked():
    alice = register(make_client(), "alice")
    alice.headers.pop("origin", None)
    r = alice.post("/messages/send", json={"receiver": "alice", "content": "x"}, headers=J)
    assert r.status_code == 403
    r = alice.post("/messages/send", json={"receiver": "alice", "content": "x"}, headers={**J, "Origin": "https://evil.example"})
    assert r.status_code == 403


def test_fake_video_rejected():
    alice = register(make_client(), "alice")
    register(make_client(), "bob")
    r = alice.post("/messages/send-media", data={"receiver": "bob"}, files={"file": ("v.mp4", b"<html><script>alert(1)</script>" + b"0" * 100, "video/mp4")}, headers=J)
    assert r.status_code >= 400 or r.json().get("ok") is False


def test_admin_closed_for_regular_user():
    """Админка остаётся, но открывается только владельцам и модераторам."""
    c = register(make_client(), "carol")
    anon = make_client()
    paths = sorted({r.path for r in main.app.routes if getattr(r, "path", "").startswith("/admin") and "GET" in getattr(r, "methods", set()) and "{" not in r.path})
    assert len(paths) > 10
    for p in paths:
        for cl in (c, anon):
            r = cl.get(p)  # переходим по всем переадресациям: в конце не должно оказаться страницы админки
            assert r.status_code >= 400 or not r.url.path.startswith("/admin"), (p, r.status_code, r.url.path)


def test_account_lock_after_many_wrong_passwords():
    """Подбор пароля с разных адресов: после 40 неверных паролей за час аккаунт временно не пускает даже с верным."""
    from routers import auth_routes
    from services import ratelimit
    import models
    from database import SessionLocal
    register(make_client(), "dave")
    s = SessionLocal()
    uid = s.query(models.User).filter_by(username="dave").first().id
    s.close()
    for _ in range(auth_routes.ACCOUNT_FAILS):
        ratelimit.hit(f"loginfail:{uid}", 10 ** 6, 3600)
    c = make_client()
    r = c.post("/login", data={"username": "dave", "password": "secret123"})
    assert "Слишком много неверных паролей" in r.text
    ratelimit.reset(f"loginfail:{uid}")
    r = c.post("/login", data={"username": "dave", "password": "secret123"}, follow_redirects=False)
    assert r.status_code == 303


def test_no_open_redirect():
    from deps import safe_next
    for bad in ("//evil.example", "/\\evil.example", "/\\/evil.example", "https://evil.example", "/x\r\nSet-Cookie: a=b"):
        assert safe_next(bad) == "/", bad
    assert safe_next("/post/1?x=1") == "/post/1?x=1"
    c = make_client()
    r = c.get("/lang/en?next=/%5Cevil.example", follow_redirects=False)
    assert r.headers["location"] == "/"


def test_moderator_cannot_touch_owner_content():
    import models
    from database import SessionLocal
    from tests.test_app import create_post
    owner = register(make_client(), "zara")
    mod = register(make_client(), "carol")
    eve = register(make_client(), "eve")
    s = SessionLocal()
    for u in s.query(models.User).all():
        u.is_owner = u.username == "zara"
        u.is_moderator = u.username == "carol"
    s.commit()
    s.close()
    p_owner = create_post(owner, "пост владельца")
    p_eve = create_post(eve, "пост нарушителя")
    assert mod.post(f"/post/{p_owner}/delete", headers=J).status_code == 403
    mod.post(f"/admin/posts/{p_owner}/delete")
    s = SessionLocal()
    assert s.get(models.Post, p_owner) is not None  # пост владельца на месте
    s.close()
    assert mod.post(f"/post/{p_eve}/delete", headers=J).json()["ok"]  # обычного нарушителя модератор удалить может


def test_promo_cannot_be_reused_after_deleting_notifications():
    import models
    from database import SessionLocal
    a = register(make_client(), "alice")
    s = SessionLocal()
    s.add(models.Promocode(code="MULTI", days=7, max_uses=100, is_active=True))
    s.commit()
    a.post("/settings/promocode", data={"code": "MULTI"})
    u = s.query(models.User).filter_by(username="alice").first()
    first = u.plus_until
    assert first
    a.post("/notifications/clear", headers=J)
    r = a.post("/settings/promocode", data={"code": "MULTI"})
    assert "уже активировали" in r.text
    s.expire_all()
    assert s.query(models.User).filter_by(username="alice").first().plus_until == first
    assert s.query(models.Promocode).filter_by(code="MULTI").first().uses == 1
    s.close()
