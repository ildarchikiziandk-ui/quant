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
