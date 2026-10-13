import re

import models
from database import SessionLocal
from tests.conftest import make_client, png_bytes, register

J = {"X-Requested-With": "fetch"}


def db():
    return SessionLocal()


def create_post(client, content="Привет #мир @bob", files=None, **extra):
    data = {"content": content, **extra}
    r = client.post("/post/create", data=data, files=files or [], headers=J)
    assert r.status_code == 200, r.text
    return r.json()["post_id"]


def test_public_pages(anon):
    for url in ["/", "/login", "/register", "/explore", "/search?q=x", "/trends", "/terms", "/about", "/plus", "/support",
                "/forgot", "/offline", "/leaderboard", "/manifest.webmanifest", "/sw.js", "/robots.txt", "/healthz",
                "/?tab=latest", "/?tab=media", "/welcome"]:
        r = anon.get(url)
        assert r.status_code == 200, (url, r.status_code, r.text[:300])
    assert "Nuvora" in anon.get("/").text
    assert "Quant" not in anon.get("/").text


def test_404_page(anon):
    r = anon.get("/definitely-missing")
    assert r.status_code == 404 and "Страница не найдена" in r.text


def test_register_validation(anon):
    r = anon.post("/register", data={"username": "ab", "email": "x@y.z", "password": "secret123", "confirm_password": "secret123", "agree": "1"})
    assert "минимум 3" in r.text
    r = anon.post("/register", data={"username": "goodname", "email": "x@y.z", "password": "short", "confirm_password": "short", "agree": "1"})
    assert "минимум 8" in r.text


def test_login_logout_and_legacy_password(anon, alice):
    s = db()
    u = s.query(models.User).filter_by(username="alice").first()
    assert u.password.startswith("$2")  # bcrypt
    import hashlib
    u.password = hashlib.sha256(b"oldpass1").hexdigest()
    s.commit()
    r = anon.post("/login", data={"username": "alice", "password": "oldpass1"}, follow_redirects=False)
    assert r.status_code == 303
    s.refresh(u)
    assert u.password.startswith("$2"), "legacy hash should be upgraded"
    s.close()
    assert anon.get("/settings").status_code == 200
    bad = make_client().post("/login", data={"username": "alice", "password": "nope"})
    assert "Неверный пароль" in bad.text
    anon.post("/logout")
    r = anon.get("/settings", follow_redirects=False)
    assert r.status_code == 303


def test_session_revocation(alice):
    s = db()
    sess = s.query(models.UserSession).join(models.User).filter(models.User.username == "alice").all()
    for x in sess:
        x.is_active = False
    s.commit()
    s.close()
    assert alice.get("/settings", follow_redirects=False).status_code == 303


def test_logged_in_pages(owner, alice, bob):
    pid = create_post(alice)
    for url in ["/", "/?tab=following", "/explore", "/notifications", "/messages", "/groups", "/tasks", "/bookmarks", "/drafts",
                "/settings", "/mentions", "/achievements", "/leaderboard?by=weekly", "/stories/create", "/close-friends",
                "/follow-requests", "/special-request", "/messages/search?q=hi", "/profile/alice", "/profile/alice?tab=media",
                "/profile/alice?tab=likes", "/profile/alice?tab=reels", "/profile/alice?tab=replies", "/profile/alice/followers",
                "/profile/alice/following", f"/post/{pid}", f"/post/{pid}/stats", "/qr/alice", "/qr-code/alice.svg", "/report/bob",
                "/messages/bob", "/hashtag/мир", "/feed/more?tab=latest&page=2", "/welcome"]:
        r = alice.get(url)
        assert r.status_code == 200, (url, r.status_code, r.text[:500])
    for section in ["profile", "account", "privacy", "notifications", "appearance", "security", "plus", "data"]:
        r = alice.get(f"/settings?section={section}")
        assert r.status_code == 200, section
    assert alice.get("/settings/2fa/qr.svg").status_code == 200
    r = owner.get("/admin")
    assert r.status_code == 200
    for tab in ["users", "reports", "requests", "support", "moderation", "plus", "content", "logs"]:
        assert owner.get(f"/admin?tab={tab}").status_code == 200, tab
    assert alice.get("/admin", follow_redirects=False).status_code == 303


def test_post_lifecycle(alice, bob):
    pid = create_post(alice, "Первый пост #тест", files=[("media", ("a.png", png_bytes(), "image/png")),
                                                          ("media", ("b.png", png_bytes((10, 200, 30)), "image/png"))],
                      poll_question="Как дела?", poll_options=["Хорошо", "Отлично"])
    s = db()
    p = s.get(models.Post, pid)
    assert p.image.startswith("/uploads/") and len(p.media_items) == 2 and p.poll and len(p.poll.options) == 2
    opt = p.poll.options[0].id
    s.close()
    assert bob.post(f"/like/{pid}", headers=J).json()["liked"] is True
    assert bob.post(f"/whale/{pid}", headers=J).json()["whaled"] is True
    assert bob.post(f"/bookmark/{pid}", headers=J).json()["bookmarked"] is True
    r = bob.post(f"/post/{pid}/react", json={"emoji": "🔥"}, headers=J).json()
    assert r["counts"] == {"🔥": 1}
    assert bob.post(f"/poll/vote/{opt}", headers=J).json()["total"] == 1
    c = bob.post(f"/post/{pid}/comment", json={"content": "Круто, @alice!"}, headers=J).json()["id"]
    reply = alice.post(f"/post/{pid}/comment", json={"content": "Спасибо", "parent_id": c}, headers=J).json()["id"]
    assert alice.post(f"/comment/{c}/like", headers=J).json()["liked"]
    assert alice.post(f"/post/{pid}/pin-comment/{c}", headers=J).json()["pinned"]
    page = alice.get(f"/post/{pid}").text
    assert "Круто" in page and "Спасибо" in page and "закреплён" in page
    assert bob.post(f"/repost/{pid}", json={}, headers=J).json()["reposted"]
    assert bob.post(f"/repost/{pid}", json={"comment": "Смотрите!"}, headers=J).json()["reposted"]
    assert alice.post(f"/post/{pid}/edit", json={"content": "Изменённый #тест"}, headers=J).json()["ok"]
    assert bob.post(f"/post/{pid}/edit", json={"content": "hack"}, headers=J).status_code == 403
    assert alice.post(f"/post/{pid}/pin", headers=J).json()["pinned"]
    assert bob.post(f"/post/{pid}/report", json={"reason": "Спам"}, headers=J).json()["ok"]
    assert bob.post(f"/post/{pid}/delete", headers=J).status_code == 403
    s = db()
    kinds = {n.type for n in s.query(models.Notification).join(models.User, models.User.id == models.Notification.user_id).filter(models.User.username == "alice")}
    assert {"like", "whale", "comment", "mention", "repost", "reaction"} <= kinds
    s.close()
    alice.post(f"/comment/{c}/delete", headers=J)
    s = db()
    assert s.get(models.Comment, reply) is None
    s.close()
    assert alice.post(f"/post/{pid}/delete", headers=J).json()["ok"]
    s = db()
    assert s.get(models.Post, pid) is None
    s.close()


def test_xss_is_escaped(alice):
    pid = create_post(alice, '<script>alert(1)</script> https://example.com/a?b=1 #ok')
    html = alice.get(f"/post/{pid}").text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert 'href="https://example.com/a?b=1"' in html


def test_csrf_blocked(alice):
    r = alice.post("/settings/profile", data={"name": "x"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_private_profile_and_requests(alice, bob):
    register(make_client(), "carol", private=False)
    alice.post("/settings/privacy", data={"is_private": "on", "who_can_message": "all", "who_can_see_stories": "all"})
    pid = create_post(alice, "секрет")
    assert "закрытый профиль" in bob.get("/profile/alice").text.lower()
    assert bob.get(f"/post/{pid}").status_code == 404
    assert bob.post("/follow/alice", headers=J).json()["state"] == "requested"
    s = db()
    req = s.query(models.FollowRequest).first()
    s.close()
    alice.post(f"/follow-requests/{req.id}/accept", headers=J)
    assert bob.get(f"/post/{pid}").status_code == 200


def test_block_hides_and_prevents_messages(alice, bob):
    pid = create_post(alice, "видно?")
    assert alice.post("/block/bob", headers=J).json()["blocked"]
    assert bob.get(f"/post/{pid}").status_code == 404
    r = bob.post("/messages/send", json={"receiver": "alice", "content": "hi"}, headers=J)
    assert r.status_code == 403
    alice.post("/unblock/bob", headers=J)
    assert bob.post("/messages/send", json={"receiver": "alice", "content": "hi"}, headers=J).json()["ok"]


def test_messages_flow(alice, bob):
    mid = alice.post("/messages/send", json={"receiver": "bob", "content": "Привет, Боб!"}, headers=J).json()["id"]
    r = bob.get("/messages/poll/alice?after=0").json()
    assert "Привет, Боб!" in r["html"]
    assert alice.get("/messages/poll/bob?after=0").json()["read_upto"] == mid
    assert bob.post(f"/messages/{mid}/react", json={"emoji": "❤️"}, headers=J).json()["ok"]
    assert alice.post(f"/messages/{mid}/edit", json={"content": "Привет!"}, headers=J).json()["ok"]
    assert bob.post(f"/messages/{mid}/edit", json={"content": "x"}, headers=J).status_code == 404
    assert alice.post(f"/messages/{mid}/pin", headers=J).json()["pinned"]
    r = alice.post("/messages/send-media", data={"receiver": "bob"}, files={"file": ("p.png", png_bytes(), "image/png")}, headers=J)
    assert r.json()["ok"]
    r = alice.post("/messages/send-media", data={"receiver": "bob"}, files={"file": ("v.webm", b"\x1a\x45\xdf\xa3" + b"0" * 100, "audio/webm")}, headers=J)
    assert r.json()["ok"]
    register(make_client(), "dave")
    assert bob.post(f"/messages/{mid}/forward", json={"to": "dave"}, headers=J).json()["ok"]
    assert alice.post("/messages/typing/bob").json()["ok"]
    assert bob.get("/messages/poll/alice?after=0").json()["typing"]
    assert "Привет!" in bob.get("/messages").text
    assert "Привет" in alice.get("/messages/search?q=Привет").text
    assert alice.post(f"/messages/{mid}/delete", headers=J).json()["ok"]
    bob.post("/settings/privacy", data={"who_can_message": "nobody", "who_can_see_stories": "all"})
    register(make_client(), "eve").post("/messages/send", json={"receiver": "bob", "content": "x"}, headers=J)
    eve = make_client()
    eve.post("/login", data={"username": "eve", "password": "secret123"})
    assert eve.post("/messages/send", json={"receiver": "bob", "content": "x"}, headers=J).status_code == 403


def test_groups(alice, bob):
    r = alice.post("/groups/create", data={"name": "Команда", "description": "чат", "members": "@bob"}, follow_redirects=False)
    gid = int(r.headers["location"].rsplit("/", 1)[1])
    assert bob.get(f"/groups/{gid}").status_code == 200
    assert bob.post(f"/groups/{gid}/send", data={"content": "Всем привет"}, headers=J).json()["ok"]
    assert "Всем привет" in alice.get(f"/api/groups/{gid}/messages?after=0").json()["html"]
    outsider = register(make_client(), "mallory")
    assert outsider.get(f"/api/groups/{gid}/messages?after=0").status_code == 404
    assert outsider.post(f"/groups/{gid}/send", data={"content": "spam"}, headers=J).status_code == 404
    s = db()
    code = s.get(models.GroupChat, gid).invite_code
    s.close()
    outsider.get(f"/groups/join/{code}")
    assert outsider.get(f"/api/groups/{gid}/messages?after=0").status_code == 200
    bob.post(f"/groups/{gid}/leave")
    assert bob.get(f"/api/groups/{gid}/messages").status_code == 404


def test_stories(alice, bob):
    r = alice.post("/stories/create", data={"text_overlay": "Привет из истории", "bg_color": "#ec4899"}, follow_redirects=False)
    assert r.status_code == 303
    r = alice.post("/stories/create", files={"media": ("s.png", png_bytes(), "image/png")}, data={"audience": "all"}, follow_redirects=False)
    assert r.status_code == 303
    assert "Привет из истории" in bob.get("/stories/alice").text
    s = db()
    sid = s.query(models.Story).first().id
    s.close()
    assert bob.post(f"/stories/{sid}/react", json={"emoji": "🔥"}, headers=J).json()["ok"]
    assert bob.post(f"/stories/{sid}/reply", json={"text": "Класс"}, headers=J).json()["ok"]
    v = alice.get(f"/stories/{sid}/viewers").json()
    assert v["count"] == 1 and v["users"][0]["reaction"] == "🔥"
    hid = alice.post(f"/stories/{sid}/highlight", json={"title": "Лето"}, headers=J).json()["highlight_id"]
    assert bob.get(f"/highlights/{hid}").status_code == 200
    assert "alice" in bob.get("/").text
    assert alice.post(f"/stories/{sid}/delete", headers=J).json()["ok"]



def test_follow_and_achievements(alice, bob):
    assert bob.post("/follow/alice", headers=J).json()["state"] == "following"
    create_post(alice, "для подписчиков", visibility="followers")
    assert "для подписчиков" in bob.get("/?tab=following").text
    stranger = register(make_client(), "zed")
    assert "для подписчиков" not in stranger.get("/?tab=latest").text
    s = db()
    b = s.query(models.User).filter_by(username="bob").first()
    codes = {ua.achievement.code for ua in b.achievements}
    assert "first_follow" in codes
    s.close()
    assert bob.post("/follow/alice", headers=J).json()["state"] == "none"


def test_settings_and_2fa(alice):
    alice.post("/settings/profile", data={"name": "Алиса", "bio": "Привет #всем", "website": "example.com", "birthday": "2000-01-02"})
    s = db()
    u = s.query(models.User).filter_by(username="alice").first()
    assert u.name == "Алиса" and u.website == "https://example.com"
    s.close()
    alice.post("/settings/appearance", data={"theme": "dark", "font_size": "large", "accent_color": "#2563eb"})
    page = alice.get("/").text
    assert "#2563eb" in page
    page = alice.get("/settings?section=security")
    secret = page.cookies.get("totp_setup") or alice.cookies.get("totp_setup")
    import auth
    r = alice.post("/settings/2fa/enable", data={"code": auth.totp_now(secret)})
    assert "включена" in r.text
    c = make_client()
    r = c.post("/login", data={"username": "alice", "password": "secret123"})
    assert "Двухфакторная" in r.text
    r = c.post("/login/2fa", data={"code": "000000"})
    assert "Неверный код" in r.text or auth.totp_now(secret) == "000000"
    r = c.post("/login/2fa", data={"code": auth.totp_now(secret)}, follow_redirects=False)
    assert r.status_code == 303
    assert c.get("/settings").status_code == 200
    r = alice.post("/settings/username", data={"username": "alice2", "password": "secret123"})
    assert "@alice2" in r.text
    assert alice.get("/profile/alice2").status_code == 200


def test_promocode_and_admin(owner, alice):
    owner.post("/admin/create_promo", data={"code": "HELLO", "days": "10", "max_uses": "2"})
    r = alice.post("/settings/promocode", data={"code": "hello"})
    assert "активирован" in r.text
    r = alice.post("/settings/promocode", data={"code": "hello"})
    assert "уже активировали" in r.text
    owner.post("/admin/verify/alice")
    owner.post("/admin/block/alice", data={"days": "1", "reason": "тест"})
    assert alice.post("/post/create", data={"content": "x"}, headers=J).status_code in (401, 403)
    owner.post("/admin/unblock/alice")
    alice.post("/login", data={"username": "alice", "password": "secret123"})
    owner.post("/admin/stopwords", data={"word": "плохо"})
    pid = create_post(alice, "это плохо")
    assert "плохо" not in alice.get(f"/post/{pid}").text.split("<article")[1]
    owner.post("/admin/announce", data={"text": "Обновление!", "level": "info"})
    assert "Обновление!" in alice.get("/").text
    owner.post("/admin/challenge", data={"title": "Пиши", "task_type": "post", "target_count": "1", "points": "50"})
    create_post(alice, "челлендж")
    owner.post("/admin/raffle/draw")
    assert owner.get("/admin?tab=logs").status_code == 200


def test_support_and_requests(owner, alice, anon):
    r = alice.post("/support", data={"subject": "Ошибка на сайте", "message": "Помогите"})
    assert "отправлено" in r.text
    r = anon.post("/support", data={"subject": "Другое", "message": "Привет", "email": "x@example.com"})
    assert "отправлено" in r.text
    s = db()
    n = s.query(models.Notification).filter_by(type="support").first()
    s.close()
    owner.post(f"/support/reply/{n.id}", data={"reply": "Решено"})
    r = alice.post("/special-request", data={"type": "verify", "reason": "я известна"})
    assert "отправлена" in r.text
    s = db()
    rq = s.query(models.SpecialRequest).first()
    s.close()
    owner.post(f"/admin/requests/{rq.id}/approve", data={"comment": "ок"})
    s = db()
    assert s.query(models.User).filter_by(username="alice").first().is_verified_badge
    s.close()
    r = alice.post("/report/owner", data={"reason": "Спам", "text": "test"}, files=[("images", ("x.png", png_bytes(), "image/png"))])
    assert "Жалоба отправлена" in r.text



def test_export_and_delete_account(alice, bob):
    pid = create_post(alice, "удаляемый")
    bob.post(f"/post/{pid}/comment", json={"content": "коммент"}, headers=J)
    bob.post("/messages/send", json={"receiver": "alice", "content": "hey"}, headers=J)
    alice.post("/groups/create", data={"name": "G", "members": "bob"})
    alice.post("/stories/create", data={"text_overlay": "s"})
    r = alice.get("/export-data")
    assert r.status_code == 200 and r.json()["profile"]["username"] == "alice"
    r = alice.post("/settings/delete_account", data={"password": "wrong"})
    assert "верный пароль" in r.text
    r = alice.post("/settings/delete_account", data={"password": "secret123"}, follow_redirects=False)
    assert r.status_code == 303
    s = db()
    assert s.query(models.User).filter_by(username="alice").first() is None
    s.close()
    assert bob.get("/messages").status_code == 200
    assert bob.get("/").status_code == 200


def test_api_endpoints(alice):
    assert alice.get("/api/counters").json()["ok"]
    assert alice.get("/api/me").json()["username"] == "alice"
    assert "users" in alice.get("/api/users/suggest?q=al").json()
    create_post(alice, "#питон рулит")
    assert alice.get("/api/hashtags/suggest?q=пит").json()["tags"][0]["tag"] == "питон"
    assert alice.post("/api/push/subscribe", json={"endpoint": "https://push.example/1", "p256dh": "a", "auth": "b"}).json()["ok"]


def test_infinite_feed(alice):
    from services import ratelimit
    for i in range(25):
        ratelimit.reset()
        create_post(alice, f"пост номер {i}")
    page1 = alice.get("/?tab=following").text
    assert "data-more" in page1
    page2 = alice.get("/feed/more?tab=following&page=2").text
    assert "пост номер" in page2
    bob = register(make_client(), "bobby")
    assert "data-more" in bob.get("/?tab=foryou").text  # рекомендации с пагинацией
    p2 = bob.get("/feed/more?tab=foryou&page=2").text
    assert "пост номер" in p2


def test_register_form_keeps_name_and_no_macro_leak(anon):
    r = anon.get("/register")
    assert "Macro" not in r.text
    r = anon.post("/register", data={"username": "ab", "name": "Иван", "email": "x@y.z", "password": "secret123", "confirm_password": "secret123", "agree": "1"})
    assert 'value="Иван"' in r.text and "Macro" not in r.text


def test_login_variants(alice):
    c = make_client()
    r = c.post("/login", data={"username": " @ALICE ", "password": "secret123 "}, follow_redirects=False)
    assert r.status_code == 303, "uppercase login, @ and trailing spaces should be accepted"
    assert "не найден" in make_client().post("/login", data={"username": "Alice Liddell", "password": "x"}).text
    assert "Неверный пароль" in make_client().post("/login", data={"username": "alice", "password": "nope"}).text
    c2 = make_client()
    r = c2.post("/login", data={"username": "alice@example.com", "password": "secret123"}, headers={"Origin": "https://www.testserver"}, follow_redirects=False)
    assert r.status_code == 303, "www-origin must pass CSRF check"
    assert c2.get("/settings").status_code == 200 and alice.get("/settings").status_code == 200


def test_removed_sections(alice):
    assert alice.get("/trends", follow_redirects=False).status_code == 301
    assert alice.get("/reels", follow_redirects=False).status_code == 301
    home = alice.get("/").text
    assert 'href="/reels"' not in home and "Тренды" not in home


def test_email_verification_required(monkeypatch, anon):
    import config
    from services import mailer
    sent = {}
    monkeypatch.setattr(config, "EMAIL_ENABLED", True)
    monkeypatch.setattr(mailer, "send", lambda to, subj, body: sent.setdefault("body", body) or True)
    r = anon.post("/register", data={"username": "veri", "email": "veri@example.com", "password": "secret123", "confirm_password": "secret123", "agree": "1"}, follow_redirects=False)
    assert r.headers["location"] == "/verify"
    assert anon.post("/post/create", data={"content": "hi"}, headers=J).status_code == 403
    code = re.search(r"letter-spacing:8px;\">(\d{6})<", sent["body"]).group(1)
    anon.post("/verify", data={"code": code})
    assert anon.post("/post/create", data={"content": "hi"}, headers=J).status_code == 200
    # сброс пароля по коду
    sent.clear()
    anon.post("/forgot", data={"email": "veri@example.com"})
    code = re.search(r"letter-spacing:8px;\">(\d{6})<", sent["body"]).group(1)
    r = anon.post("/forgot/reset", data={"email": "veri@example.com", "code": code, "password": "newpass123"})
    assert "Пароль изменён" in r.text
    assert make_client().post("/login", data={"username": "veri", "password": "newpass123"}, follow_redirects=False).status_code == 303


def test_admin_reset_password(owner, alice):
    r = owner.post("/admin/reset-password/alice")
    temp = re.search(r"Временный пароль: (\S+) ", r.text).group(1)
    assert make_client().post("/login", data={"username": "alice", "password": temp}, follow_redirects=False).status_code == 303


def test_moderation_model_unit():
    from services import moderation as M
    assert M.toxicity("Ты тупой идиот") > 0.9
    assert M.toxicity("ты т.у.п.о.й д*бил") > 0.7
    assert M.toxicity("иди н а х у й") > 0.9
    for ok in ["Привет! Как дела?", "Блин, проспал", "Офигенный закат, ребята!", "Я убью этот уровень в игре", ""]:
        assert M.toxicity(ok) < 0.5, ok
    assert M.spam("Заработок от 5000 в день! Пиши в лс, переходи t.me/money") > 0.7
    assert M.spam("Кто со мной на концерт?") == 0


def test_moderation_flow(owner, alice, bob):
    clean = create_post(alice, "Сегодня отличная погода")
    r = alice.post("/post/create", data={"content": "Все вокруг тупые уроды и дебилы, идите нахуй"}, headers=J).json()
    assert r["held"] and "проверку" in r["message"]
    bad = r["post_id"]
    assert bob.get(f"/post/{bad}").status_code == 404
    assert alice.get(f"/post/{bad}").status_code == 200
    assert bob.post(f"/post/{clean}/comment", data={"content": "заткнись, дебил"}, headers=J).json()["ok"]
    s = db()
    flags = s.query(models.ModerationFlag).filter_by(status="new").all()
    assert {f.kind for f in flags} == {"post", "comment"}
    assert not s.query(models.ModerationFlag).filter_by(object_id=clean, kind="post").first()
    pf = next(f for f in flags if f.kind == "post")
    cf = next(f for f in flags if f.kind == "comment")
    s.close()
    page = owner.get("/admin?tab=ai").text
    assert "Нейромодерация" in page and "дебил" in page
    owner.post(f"/admin/ai/{pf.id}/approve")
    assert bob.get(f"/post/{bad}").status_code == 200
    owner.post(f"/admin/ai/{cf.id}/remove")
    s = db()
    assert s.get(models.Comment, cf.object_id) is None
    assert s.query(models.ModerationFlag).filter_by(status="new").count() == 0
    s.close()



def test_home_has_two_tabs_and_create_page(alice):
    page = alice.get("/").text
    assert "Рекомендации" in page and "Подписки" in page
    assert "Свежее" not in page and 'id="composer"' not in page
    assert 'id="composer"' in alice.get("/create").text
    assert make_client().get("/create", follow_redirects=False).status_code in (302, 303, 307)


def test_recommendations_learn_interests(alice, bob):
    from services import ratelimit, recommend
    carol = register(make_client(), "carol")
    cats, cars = [], []
    for i in range(6):
        ratelimit.reset()
        cats.append(create_post(bob, f"Мой котик спит на диване #котики {i}"))
        cars.append(create_post(carol, f"Новый двигатель для машины #авто {i}"))
    for pid in cats[:3]:
        alice.post(f"/like/{pid}", headers=J)
    s = db()
    me = s.query(models.User).filter_by(username="alice").first()
    recommend.invalidate(me.id)
    prof = recommend.interest_profile(s, me)
    assert "котики" in prof["tags"]
    s.close()
    page = alice.get("/?tab=foryou").text
    first = re.findall(r'id="post-(\d+)"', page)
    unliked_cats = {str(x) for x in cats[3:]}
    assert first and first[0] in unliked_cats, first[:3]
    assert "Вам нравится #котики" in page or "Вы часто оцениваете" in page
    # «Не интересно» убирает пост из рекомендаций
    alice.post(f"/post/{first[0]}/not-interested", headers=J)
    assert f'id="post-{first[0]}"' not in alice.get("/?tab=foryou").text


def test_likes_tab_private_and_profile_prefs(alice, bob):
    pid = create_post(bob, "лайкни меня")
    alice.post(f"/like/{pid}", headers=J)
    assert "Лайки" in alice.get("/profile/alice").text
    assert "лайкни меня" in alice.get("/profile/alice?tab=likes").text
    other = bob.get("/profile/alice?tab=likes").text
    assert "?tab=likes" not in other
    alice.post("/settings/prefs/privacy", data={"hide_followers_list": "on", "who_can_comment": "nobody", "who_can_mention": "all",
                                                "allow_reposts": "", "read_receipts": "on", "typing_status": "on"})
    assert bob.get("/profile/alice/followers").status_code == 403
    mine = create_post(alice, "мой пост")
    r = bob.post(f"/post/{mine}/comment", data={"content": "привет"}, headers=J)
    assert r.status_code == 403
    assert bob.post(f"/repost/{mine}", headers=J).status_code == 403


def test_settings_prefs_sections(alice):
    from services import prefs
    assert len(prefs.PREFS) >= 60
    for sec in prefs.SECTIONS:
        r = alice.get(f"/settings?section={sec}")
        assert r.status_code == 200 and "/settings/prefs/" + sec in r.text, sec
    alice.post("/settings/prefs/appearance", data={"compact": "on", "corners": "sharp", "avatar_shape": "circle", "font_family": "serif"})
    html = alice.get("/").text
    assert "p-compact" in html and "p-corners-sharp" in html and "p-font-family-serif" in html
    alice.post("/settings/prefs/feed", data={"feed_default_tab": "following", "feed_muted_words": "спойлер", "rec_reasons": "on"})
    bob = register(make_client(), "bobm")
    create_post(bob, "Тут спойлер к фильму")
    create_post(bob, "Обычный пост про погоду")
    alice.post("/follow/bobm", headers=J)
    page = alice.get("/").text
    assert "Обычный пост про погоду" in page and "спойлер к фильму" not in page
