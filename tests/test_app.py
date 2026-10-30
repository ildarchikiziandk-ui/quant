import re
from datetime import datetime, timedelta

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
    r = anon.post("/register", data={"username": "ab", "email": "x@y.z", "password": "secret123", "confirm_password": "secret123", "agree": "1", "consent": "1", "public": "1", "adult": "1"})
    assert "минимум 3" in r.text
    r = anon.post("/register", data={"username": "goodname", "email": "x@y.z", "password": "short", "confirm_password": "short", "agree": "1", "consent": "1", "public": "1", "adult": "1"})
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
    assert bob.post(f"/post/{pid}/react", json={"emoji": "🔥"}, headers=J).status_code == 400  # эмодзи-реакции убраны
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
    assert {"like", "whale", "comment", "mention", "repost"} <= kinds
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
    assert bob.post(f"/stories/{sid}/react", json={"emoji": "🐋"}, headers=J).json()["ok"]
    assert bob.post(f"/stories/{sid}/reply", json={"text": "Класс"}, headers=J).json()["ok"]
    v = alice.get(f"/stories/{sid}/viewers").json()
    assert v["count"] == 1 and v["users"][0]["reaction"] == "🐋"
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
    r = alice.post("/post/create", data={"content": "это плохо"}, headers=J)  # стоп-слово: пост не публикуется
    assert r.status_code == 400 and "Не опубликовано" in r.json()["error"]
    owner.post("/admin/announce", data={"text": "Обновление!", "level": "info"})
    assert "Обновление!" in alice.get("/").text
    owner.post("/admin/challenge", data={"title": "Пиши", "task_type": "post", "target_count": "1", "points": "50"})
    create_post(alice, "челлендж")
    owner.post("/admin/raffle/draw")
    assert owner.get("/admin?tab=logs").status_code == 200


def test_support_and_requests(owner, alice, anon):
    r = alice.post("/support", data={"subject": "Ошибка на сайте", "message": "Помогите"})
    assert "отправлено" in r.text
    r = anon.post("/support", data={"subject": "Другое", "message": "Привет", "email": "x@example.com", "consent": "1"})
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
    r = anon.post("/register", data={"username": "ab", "name": "Иван", "email": "x@y.z", "password": "secret123", "confirm_password": "secret123", "agree": "1", "consent": "1", "public": "1", "adult": "1"})
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
    r = anon.post("/register", data={"username": "veri", "email": "veri@example.com", "password": "secret123", "confirm_password": "secret123", "agree": "1", "consent": "1", "public": "1", "adult": "1"}, follow_redirects=False)
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
    r = alice.post("/post/create", data={"content": "Все вокруг тупые уроды и дебилы, ненавижу вас, идиоты"}, headers=J).json()
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


def test_timezones(alice, bob):
    from datetime import datetime
    from services import timezones
    keys = dict(timezones.options())
    assert "novosibirsk" in keys and "krasnoyarsk" in keys
    assert keys["novosibirsk"].startswith("Новосибирск") and keys["krasnoyarsk"].startswith("Красноярск")
    assert "UTC+7" in keys["novosibirsk"] and "UTC+7" in keys["krasnoyarsk"]
    assert timezones.BY_KEY["novosibirsk"][2] == "Asia/Novosibirsk" and timezones.BY_KEY["krasnoyarsk"][2] == "Asia/Krasnoyarsk"
    page = alice.get("/settings?section=appearance").text
    assert 'value="novosibirsk"' in page and 'value="krasnoyarsk"' in page and "Определить по устройству" in page
    # время в поясе пользователя
    alice.post("/settings/prefs/appearance", data={"timezone": "novosibirsk", "corners": "round", "avatar_shape": "circle", "font_family": "system"})
    s = db()
    me = s.query(models.User).filter_by(username="alice").first()
    assert timezones.to_local(datetime(2026, 1, 1, 12, 0), me).hour == 19
    assert timezones.from_local(datetime(2026, 1, 1, 19, 0), me).hour == 12
    s.close()
    # отложенный пост: время вводится по местному времени
    r = alice.post("/post/create", data={"content": "по расписанию", "scheduled_at": "2030-05-01T10:00"}, headers=J).json()
    s = db()
    assert s.get(models.Post, r["post_id"]).scheduled_at.hour == 3  # 10:00 по Новосибирску = 03:00 UTC
    s.close()
    # пояс определяется при регистрации
    c = make_client()
    c.post("/register", data={"username": "krsk", "email": "krsk@example.com", "password": "secret123", "confirm_password": "secret123",
                              "agree": "1", "consent": "1", "public": "1", "adult": "1", "name": "K", "tz": "Asia/Krasnoyarsk"}, follow_redirects=False)
    s = db()
    from services import prefs
    assert prefs.get(s.query(models.User).filter_by(username="krsk").first(), "timezone") == "krasnoyarsk"
    s.close()


def test_questions_removed(alice, bob):
    # анонимные вопросы убраны из Nuvora 3.1: адреса ведут на главную
    assert bob.post("/ask/alice", data={"text": "Какая твоя любимая книга?"}, headers=J).status_code == 404
    assert alice.get("/questions", follow_redirects=False).status_code == 303


def test_hashtag_follow_feed(alice, bob):
    pid = create_post(bob, "Сегодня собрал новый ПК #железо")
    assert alice.post("/hashtag/железо/follow", headers=J).json()["following"]
    assert "Вы подписаны на тему" in alice.get("/hashtag/железо").text
    assert f'id="post-{pid}"' in alice.get("/?tab=following").text  # тема в «Подписках», хотя на автора не подписан


def test_events(alice, bob):
    r = alice.post("/events/create", data={"title": "Пикник в парке", "starts_at": "2030-06-01T15:00", "place": "Парк Горького",
                                           "description": "Берите пледы"}, follow_redirects=False)
    assert r.status_code == 303
    eid = int(r.headers["location"].rsplit("/", 1)[1])
    assert "Пикник в парке" in bob.get("/events").text
    bob.post(f"/events/{eid}/rsvp/going", headers=J)
    page = bob.get(f"/events/{eid}").text
    assert "Я иду" in page and "Идут · 2" in page
    assert "Пикник" in alice.get("/events?tab=mine").text


def test_gifts(alice, bob):
    s = db()
    a = s.query(models.User).filter_by(username="alice").first()
    a.total_points = 100
    s.commit()
    s.close()
    r = alice.post("/gifts/bob/send", data={"gift": "rose", "message": "Спасибо!"}, headers=J).json()
    assert r["ok"] and r["balance"] == 90  # −20 за розу, +10 за достижение «Щедрая душа»
    assert alice.post("/gifts/bob/send", data={"gift": "rocket"}, headers=J).status_code == 400  # не хватает очков
    assert "/static/gifts/rose.svg" in alice.get("/profile/bob").text and "Спасибо!" in bob.get("/gifts/bob").text
    s = db()
    a = s.query(models.User).filter_by(username="alice").first()
    assert a.total_points >= 100 and a.spent_points == 20  # уровень не падает от трат
    s.close()


def test_bookmark_collections(alice, bob):
    pid = create_post(bob, "Рецепт борща")
    alice.post(f"/bookmark/{pid}", headers=J)
    alice.post("/collections/create", data={"name": "Рецепты", "emoji": "🍲"})
    s = db()
    c = s.query(models.BookmarkCollection).first()
    s.close()
    alice.post(f"/bookmarks/{pid}/move", data={"collection_id": c.id}, headers=J)
    assert "Рецепт борща" in alice.get(f"/bookmarks?c={c.id}").text
    assert "1f372.svg" in alice.get("/bookmarks").text and "Рецепты" in alice.get("/bookmarks").text


def test_quiz(alice, bob):
    r = bob.post("/post/create", data={"content": "Викторина!", "poll_question": "Столица Франции?", "poll_options": ["Берлин", "Париж", "Рим"],
                                       "quiz": "1", "quiz_correct": "2"}, headers=J).json()
    s = db()
    poll = s.query(models.Poll).filter_by(post_id=r["post_id"]).first()
    paris = next(o for o in poll.options if o.text == "Париж")
    rome = next(o for o in poll.options if o.text == "Рим")
    s.close()
    pts = lambda: db().query(models.User).filter_by(username="alice").first().total_points
    before = pts()
    v = alice.post(f"/poll/vote/{paris.id}", headers=J).json()
    assert v["right"] is True and v["correct"] == paris.id and pts() == before + 5
    carol = register(make_client(), "carolq")
    assert carol.post(f"/poll/vote/{rome.id}", headers=J).json()["right"] is False
    assert "Викторина" in alice.get(f"/post/{r['post_id']}").text


def test_invite_and_interests(alice, bob):
    assert "/invite/alice" in alice.get("/invite").text
    c = make_client()
    r = c.get("/invite/alice", follow_redirects=False)
    assert r.headers["location"].startswith("/register?ref=alice")
    before = db().query(models.User).filter_by(username="alice").first().total_points
    c.post("/register", data={"username": "newbie", "email": "newbie@example.com", "password": "secret123", "confirm_password": "secret123",
                              "agree": "1", "consent": "1", "public": "1", "adult": "1", "name": "N", "ref": "alice"}, follow_redirects=False)
    s = db()
    nb = s.query(models.User).filter_by(username="newbie").first()
    me = s.query(models.User).filter_by(username="alice").first()
    assert nb.referred_by == me.id and me.total_points >= before + 20
    s.close()
    assert "newbie" in alice.get("/invite").text
    alice.post("/settings/profile", data={"name": "Alice", "interests": "Музыка, #футбол, аниме"})
    assert "#футбол" in bob.get("/profile/alice").text
    assert "Alice" in bob.get("/interests/футбол").text


def test_people_you_may_know_search_filters_memories(alice, bob):
    from datetime import datetime, timedelta
    carol = register(make_client(), "carolk")
    alice.post("/follow/bob", headers=J)
    bob.post("/follow/carolk", headers=J)
    assert "Возможно, вы знакомы" in alice.get("/explore").text and "carolk" in alice.get("/explore").text
    create_post(bob, "кот на фото")
    assert "кот на фото" in alice.get("/search?q=кот&type=posts&period=day").text
    assert "кот на фото" not in alice.get("/search?q=кот&type=posts&media=1").text
    pid = create_post(alice, "Год назад я был тут")
    s = db()
    p = s.get(models.Post, pid)
    p.created_at = datetime.utcnow().replace(year=datetime.utcnow().year - 1)
    s.commit()
    s.close()
    assert alice.get("/memories", follow_redirects=False).status_code == 303  # раздел «В этот день» убран
    long_id = create_post(alice, "слово " * 600)
    assert "мин" in alice.get(f"/profile/alice").text


def test_rich_formatting_and_post_extras(alice, bob):
    pid = create_post(alice, "**жирно** __курсив__ ~~нет~~ `код` ||спойлер||\n> цитата", mood="happy", location="Казань",
                      content_warning="Спойлеры", expires="24")
    page = bob.get(f"/post/{pid}").text
    for frag in ("<b>жирно</b>", "<i>курсив</i>", "<s>нет</s>", 'class="rt-code"', 'class="spoiler"', 'class="rt-quote"',
                 "чувствует себя радостно", "Казань", "Спойлеры", "пост исчезнет"):
        assert frag in page, frag
    bgp = create_post(alice, "Короткий пост на фоне", bg="sunset")
    assert "bg-sunset" in bob.get(f"/post/{bgp}").text
    # исчезающий пост пропадает после срока
    s = db()
    from datetime import datetime, timedelta
    s.get(models.Post, pid).expires_at = datetime.utcnow() - timedelta(minutes=1)
    s.commit()
    s.close()
    assert bob.get(f"/post/{pid}").status_code == 404


def test_edit_history_archive_qr_send_remind(alice, bob):
    pid = create_post(alice, "первая версия")
    alice.post(f"/post/{pid}/edit", data={"content": "вторая версия"}, headers=J)
    h = bob.get(f"/post/{pid}/history").text
    assert "первая версия" in h and "вторая версия" in h
    assert alice.post(f"/post/{pid}/archive", headers=J).json()["archived"]
    assert bob.get(f"/post/{pid}").status_code == 404 and "вторая версия" in alice.get("/archive").text
    alice.post(f"/post/{pid}/archive", headers=J)
    assert bob.get(f"/post/{pid}/qr.svg").headers["content-type"].startswith("image/svg")
    assert bob.post(f"/post/{pid}/send", data={"username": "alice", "note": "смотри"}, headers=J).json()["ok"]
    assert f"/post/{pid}" in alice.get("/messages/bob").text
    bob.post(f"/post/{pid}/remind", data={"hours": 1}, headers=J)
    s = db()
    from datetime import datetime, timedelta
    r = s.query(models.PostReminder).first()
    r.remind_at = datetime.utcnow() - timedelta(minutes=1)
    s.commit()
    s.close()
    bob.get("/")
    assert "Вы просили напомнить" in bob.get("/notifications").text
    assert "<b>x</b>" in bob.post("/api/preview", data={"content": "**x**"}, headers=J).json()["html"]


def test_comment_features(alice, bob):
    pid = create_post(alice, "обсуждаем")
    bob.post(f"/post/{pid}/comment", data={"content": "первый"}, headers=J)
    s = db()
    c = s.query(models.Comment).first()
    s.close()
    assert bob.post(f"/comment/{c.id}/edit", data={"content": "исправленный"}, headers=J).json()["ok"]
    assert "исправленный" in alice.get(f"/post/{pid}").text and "изм." in alice.get(f"/post/{pid}").text
    alice.post(f"/comment/{c.id}/hide", headers=J)
    carol = register(make_client(), "carolc")
    assert "Комментарий скрыт автором поста" in carol.get(f"/post/{pid}").text
    carol.post(f"/comment/{c.id}/report", headers=J)
    s = db()
    assert s.query(models.ModerationFlag).filter_by(kind="comment", label="report").count() == 1
    s.close()
    bob.post(f"/post/{pid}/comment", data={"content": "второй"}, headers=J)
    assert "Популярные" in alice.get(f"/post/{pid}?sort=top").text


def test_profile_extras(alice, bob):
    alice.post("/settings/links", data={"link_title_0": "Портфолио", "link_url_0": "example.com"})
    alice.post("/settings/profile", data={"name": "Alice", "birthday": "2000-03-25"})
    page = bob.get("/profile/alice").text
    assert "Портфолио" in page and "https://example.com" in page and "25.03" in page
    alice.post("/settings/dnd", data={"hours": "3"}, headers=J)
    assert "не беспокоить" in bob.get("/profile/alice").text
    pid = create_post(alice, "пост до паузы")
    alice.post("/settings/pause")
    assert bob.get(f"/post/{pid}").status_code == 404
    alice.post("/settings/pause")
    assert bob.get(f"/post/{pid}").status_code == 200


def test_shop_wheel_freeze_leaderboard(alice, bob):
    s = db()
    a = s.query(models.User).filter_by(username="alice").first()
    a.total_points = 500
    s.commit()
    s.close()
    alice.post("/shop/frame/gold")
    s = db()
    a = s.query(models.User).filter_by(username="alice").first()
    assert a.avatar_frame == "gold" and "gold" in a.frames_owned
    s.close()
    assert "frame-gold" in bob.get("/profile/alice").text
    alice.post("/shop/freeze")
    assert alice.post("/wheel/spin", headers=J).status_code == 404  # колесо фортуны убрано (есть ежедневный сундук)
    # заморозка спасает стрик
    from datetime import date, timedelta
    from services import gamification
    s = db()
    a = s.query(models.User).filter_by(username="alice").first()
    a.streak_days, a.last_streak_date, a.streak_freezes = 10, (date.today() - timedelta(days=2)).isoformat(), 1
    s.commit()
    gamification.update_streak(a, s)
    assert a.streak_days == 11 and a.streak_freezes == 0
    s.close()
    assert "Среди друзей" in alice.get("/leaderboard?scope=friends").text


def test_discovery_and_utilities(alice, bob):
    pid = create_post(bob, "популярный пост")
    alice.post(f"/like/{pid}", headers=J)
    assert "популярный пост" in alice.get("/top?period=week").text
    assert alice.get("/random", follow_redirects=False).headers["location"] == "/"  # раздел убран
    alice.post("/settings/profile", data={"name": "Alice", "city": "Казань"})
    bob.post("/settings/profile", data={"name": "Bob", "city": "казань"})
    assert "@bob" in alice.get("/people/city").text
    assert alice.post("/notes/save", data={"title": "Идеи", "content": "x"}, headers=J).status_code == 404  # заметки убраны
    st = bob.get("/stats").text
    assert "Активность за полгода" in st and "Лучшее время" in st
    alice.post("/follow/bob", headers=J)
    bob.get("/api/counters")  # bob в сети
    assert "Сейчас онлайн" in alice.get("/").text
    owner = register(make_client(), "owner")
    csvr = owner.get("/admin/export/users.csv")
    assert csvr.status_code == 200 and "alice" in csvr.text


def test_messages_are_encrypted_at_rest(alice, bob):
    from sqlalchemy import text
    from database import engine
    from services import crypto
    bob.post("/follow/alice", headers=J)
    alice.post("/follow/bob", headers=J)
    r = alice.post("/messages/send", json={"receiver": "bob", "content": "секретный пароль от вайфая 12345"}, headers=J)
    assert r.status_code == 200, r.text
    with engine.connect() as c:
        raw = c.execute(text("SELECT content FROM messages ORDER BY id DESC LIMIT 1")).scalar()
    assert raw.startswith("enc1:") and "секретный" not in raw  # в базе — только шифротекст
    assert "секретный пароль от вайфая" in bob.get("/messages/alice").text  # собеседник видит текст
    assert "секретный пароль" in alice.get("/messages/search?q=вайфая").text  # поиск работает после расшифровки
    # старые незашифрованные сообщения шифруются миграцией
    with engine.begin() as c:
        c.execute(text("UPDATE messages SET content = 'старое сообщение'"))
    import migrations
    assert migrations.encrypt_existing_messages() >= 1
    with engine.connect() as c:
        assert c.execute(text("SELECT content FROM messages LIMIT 1")).scalar().startswith("enc1:")
    assert "старое сообщение" in bob.get("/messages/alice").text
    assert crypto.decrypt(crypto.encrypt("тест")) == "тест"


def test_secret_chats_server_sees_only_ciphertext(alice, bob, monkeypatch):
    import config
    monkeypatch.setattr(config, "SECRET_CHATS_ENABLED", True)
    import base64, os
    from datetime import datetime, timedelta
    pa, pb = os.urandom(64).hex(), os.urandom(64).hex()
    assert alice.post("/secret/start", json={"username": "bob", "pub": "zz", "ttl": 0}, headers=J).json()["ok"] is False
    r = alice.post("/secret/start", json={"username": "@Bob", "pub": pa, "ttl": 30}, headers=J).json()
    assert r["ok"] and len(r["ukm"]) == 16
    cid = r["id"]
    assert "Секретные чаты" in alice.get("/secret").text and alice.get(f"/secret/{cid}").status_code == 200
    # пока bob не принял — писать нельзя, и принять может только bob
    payload = base64.b64encode(os.urandom(60)).decode()
    assert alice.post(f"/secret/{cid}/send", json={"payload": payload}, headers=J).json()["ok"] is False
    assert alice.post(f"/secret/{cid}/accept", json={"pub": pb}, headers=J).json()["ok"] is False
    assert bob.post(f"/secret/{cid}/accept", json={"pub": pb}, headers=J).json()["ok"]
    st = bob.get(f"/secret/{cid}/state").json()
    assert st["status"] == "active" and st["a_pub"] == pa and st["b_pub"] == pb
    # посторонний не видит чат
    carol = register(make_client(), "carol")
    assert carol.get(f"/secret/{cid}/state").status_code == 404
    assert carol.post(f"/secret/{cid}/send", json={"payload": payload}, headers=J).status_code == 404
    # мусор и слишком длинное отклоняются, нормальный шифротекст принимается
    assert alice.post(f"/secret/{cid}/send", json={"payload": "не base64!"}, headers=J).json()["ok"] is False
    assert alice.post(f"/secret/{cid}/send", json={"payload": "A" * 70000}, headers=J).json()["ok"] is False
    assert alice.post(f"/secret/{cid}/send", json={"payload": payload}, headers=J).json()["ok"]
    msgs = bob.get(f"/secret/{cid}/messages").json()["messages"]
    assert len(msgs) == 1 and msgs[0]["payload"] == payload and msgs[0]["expires"]
    s = db()
    m = s.query(models.SecretMessage).filter_by(chat_id=cid).one()
    assert m.payload == payload  # сервер хранит только непрозрачный шифротекст
    # таймер самоуничтожения
    m.expires_at = datetime.utcnow() - timedelta(seconds=1)
    s.commit()
    s.close()
    data = bob.get(f"/secret/{cid}/messages").json()
    assert data["messages"] == [] and data["alive"] == []
    s = db()
    assert s.query(models.SecretMessage).filter_by(chat_id=cid).count() == 0
    s.close()
    # удаление — у обоих
    assert bob.post(f"/secret/{cid}/ttl", json={"ttl": 7}, headers=J).json()["ok"] is False
    assert bob.post(f"/secret/{cid}/ttl", json={"ttl": 300}, headers=J).json()["ttl"] == 300
    bob.post(f"/secret/{cid}/delete", headers=J)
    assert alice.get(f"/secret/{cid}/state").status_code == 404


def test_russian_law_compliance(anon, owner):
    base = {"username": "kid", "email": "kid@example.com", "password": "secret123", "confirm_password": "secret123", "agree": "1"}
    assert "согласие на обработку" in anon.post("/register", data=base).text
    assert "Регистрация доступна с 14" in anon.post("/register", data={**base, "consent": "1", "public": "1"}).text
    for url in ["/privacy", "/consent"]:
        r = anon.get(url)
        assert r.status_code == 200 and "152-ФЗ" in r.text
    assert "/privacy" in anon.get("/").text and "cookie-bar" in anon.get("/").text
    reg = anon.get("/register").text
    assert 'name="consent"' in reg and 'name="adult"' in reg
    assert 'id="secret"' in anon.get("/terms").text and "15.1" in anon.get("/terms").text
    s = db()
    u = s.query(models.User).filter_by(username="owner").one()
    assert u.pd_consent_at and u.age_confirmed
    u.pd_consent_at = None  # как у старых пользователей и вошедших через Яндекс
    s.commit()
    s.close()
    assert "Даю согласие" in owner.get("/").text
    owner.post("/consent/accept")
    assert "Даю согласие" not in owner.get("/").text
    r = owner.get("/admin?tab=legal")
    assert "152-ФЗ" in r.text and "ОРИ" in r.text and "Секретные чаты" in r.text and "физическое лицо" in r.text


def test_chat_streaks_and_deleted_messages(alice, bob):
    from datetime import datetime, timedelta
    from services import streaks
    s = db()
    a = s.query(models.User).filter_by(username="alice").one()
    b = s.query(models.User).filter_by(username="bob").one()
    now = datetime.utcnow()
    for d in range(4):  # четыре дня подряд оба пишут друг другу
        t = now - timedelta(days=d)
        s.add(models.Message(sender_id=a.id, receiver_id=b.id, content="привет", created_at=t))
        s.add(models.Message(sender_id=b.id, receiver_id=a.id, content="и тебе", created_at=t))
    s.commit()
    days, risk = streaks.chat_streaks(s, a, [b.id])[b.id]
    assert days >= 3 and risk is False
    s.close()
    assert 'class="fire' in alice.get("/messages").text
    # удалённое сообщение исчезает, без надписи «удалено»
    mid = alice.post("/messages/send", json={"receiver": "bob", "content": "секрет"}, headers=J).json()["id"]
    alice.post(f"/messages/{mid}/delete", headers=J)
    page = bob.get("/messages/alice").text
    assert "Сообщение удалено" not in page and "секрет" not in page


def test_signup_timezone_and_finish(anon):
    r = anon.post("/register", data={"username": "nsk", "email": "nsk@example.com", "password": "secret123", "confirm_password": "secret123",
                                     "agree": "1", "consent": "1", "public": "1", "adult": "1", "tz_key": "novosibirsk"}, follow_redirects=False)
    assert r.status_code == 303
    s = db()
    u = s.query(models.User).filter_by(username="nsk").one()
    assert '"timezone": "novosibirsk"' in u.prefs
    u.pd_consent_at = None
    s.commit()
    s.close()
    assert "Почти готово" in anon.get("/signup/finish").text
    assert "согласие" in anon.post("/signup/finish", data={"username": "nsk", "tz_key": "krasnoyarsk"}).text
    r = anon.post("/signup/finish", data={"username": "nsk2", "tz_key": "krasnoyarsk", "consent": "1", "public": "1", "adult": "1"}, follow_redirects=False)
    assert r.status_code == 303
    s = db()
    u = s.query(models.User).filter_by(email="nsk@example.com").one()
    assert u.username == "nsk2" and u.pd_consent_at and '"timezone": "krasnoyarsk"' in u.prefs
    s.close()


def test_plus_features(alice, bob, owner):
    from datetime import datetime
    from services import plus
    # без Plus: эксклюзивный подарок недоступен, лимит поста 5000 («Гости профиля» убраны)
    assert alice.get("/guests", follow_redirects=False).status_code == 303
    s = db()
    a = s.query(models.User).filter_by(username="alice").one()
    a.total_points = 1000
    s.commit()
    s.close()
    assert alice.post("/gifts/bob/send", data={"gift": "whale"}, headers=J).json()["ok"] is False
    # выдаём Plus
    owner.post("/admin/plus/alice", data={"days": "30"})
    s = db()
    a = s.query(models.User).filter_by(username="alice").one()
    assert plus.active(a) and plus.limit(a, "post_length") == 15000 and plus.limit(a, "voice") == 900
    before = a.spent_points or 0
    s.close()
    r = alice.post("/gifts/bob/send", data={"gift": "rocket"}, headers=J).json()  # 500 со скидкой 30% = 350
    assert r["ok"]
    s = db()
    assert s.query(models.User).filter_by(username="alice").one().spent_points - before == 350
    s.close()
    assert alice.post("/gifts/bob/send", data={"gift": "whale"}, headers=J).json()["ok"]
    # очки ×1,5
    s = db()
    a = s.query(models.User).filter_by(username="alice").one()
    pts = a.total_points
    from services import gamification
    gamification.add_points(a, s, 10)
    assert a.total_points - pts == 15
    s.close()
    # цвет значка из палитры и имя с градиентом
    alice.post("/settings/plus-color", data={"preset": "aurora"})
    prof = bob.get("/profile/alice").text
    assert "plus-name" in prof and "#22d3ee" in prof
    assert "Длинные посты" in alice.get("/plus").text
    # длинный пост
    pid = create_post(alice, "а" * 9000)
    s = db()
    assert len(s.get(models.Post, pid).content) == 9000
    s.close()


def test_secret_chats_disabled_by_default(alice, bob):
    import os
    assert alice.post("/secret/start", json={"username": "bob", "pub": os.urandom(64).hex()}, headers=J).json()["ok"] is False
    assert alice.get("/static/js/gost.js").status_code == 404
    page = alice.get("/secret").text
    assert "временно отключены" in page and "gost.js" not in page
    assert 'href="/secret' not in alice.get("/messages").text


def test_latin_profanity_posts_not_chats(alice, bob):
    from services import profanity
    assert profanity.has_bad("ty cyka blyat") and not profanity.has_bad("небо и хлеб, колебание, hello")
    # личная переписка не цензурируется
    alice.post("/messages/send", json={"receiver": "bob", "content": "ну ты и cyka blyat, xyi"}, headers=J)
    assert "cyka blyat" in bob.get("/messages/alice").text
    # а пост с матом латиницей не публикуется
    assert alice.post("/post/create", data={"content": "ну ты и cyka blyat"}, headers=J).status_code == 400


def test_chat_features(alice, bob):
    from datetime import datetime, timedelta
    from routers import chatx
    # своё имя контакта — видно только мне
    assert alice.post("/contacts/bob/name", json={"name": "Бобёр с работы"}, headers=J).json()["ok"]
    assert "Бобёр с работы" in alice.get("/messages/bob").text
    assert "Бобёр с работы" not in bob.get("/profile/bob").text
    # оформление чата
    r = alice.post("/chats/bob/look", data={"wallpaper": "whales", "bubble": "violet", "font": "l"}, headers=J).json()
    assert r["look"]["wallpaper"] == "whales" and r["look"]["bubble_color"] == "#7c3aed"
    page = alice.get("/messages/bob").text
    assert "has-wp" in page and "--mine:#7c3aed" in page and "cf-l" in page
    # отложенное сообщение: собеседник не видит до времени доставки
    mid = alice.post("/messages/send", json={"receiver": "bob", "content": "с днём рождения!", "schedule": "30"}, headers=J).json()["id"]
    assert "с днём рождения" not in bob.get("/messages/alice").text
    assert "будет отправлено" in alice.get("/messages/bob").text
    s = db()
    m = s.get(models.Message, mid)
    m.deliver_at = datetime.utcnow() - timedelta(seconds=1)
    s.commit()
    assert chatx.deliver_scheduled(s) == 1
    s.close()
    assert "с днём рождения" in bob.get("/messages/alice").text
    # «удалить у меня»
    mid2 = alice.post("/messages/send", json={"receiver": "bob", "content": "секретик"}, headers=J).json()["id"]
    bob.post(f"/messages/{mid2}/hide", headers=J)
    assert "секретик" not in bob.get("/messages/alice").text and "секретик" in alice.get("/messages/bob").text
    # архив и «непрочитано»
    assert bob.post("/chats/alice/archive", headers=J).json()["archived"]
    assert 'href="/messages/alice"' not in bob.get("/messages").text and "Архив" in bob.get("/messages").text
    assert 'href="/messages/alice"' in bob.get("/messages?archived=1").text
    alice.post("/messages/send", json={"receiver": "bob", "content": "вернись"}, headers=J)
    assert 'href="/messages/alice"' in bob.get("/messages").text  # новое сообщение возвращает из архива
    assert bob.post("/chats/alice/unread", headers=J).json()["marked"]
    assert "chat marked" in bob.get("/messages").text
    # медиа, статистика, экспорт
    assert alice.get("/messages/bob/media?tab=link").status_code == 200
    st = alice.get("/messages/bob/stats").json()
    assert st["total"] >= 3
    ex = alice.get("/messages/bob/export")
    assert ex.status_code == 200 and "attachment" in ex.headers["content-disposition"] and "вернись" in ex.text


def test_stream_long_poll(alice, bob):
    first = bob.get("/api/stream").json()
    assert first["ok"] and first["events"] == []
    alice.post("/messages/send", json={"receiver": "bob", "content": "привет из фона"}, headers=J)
    r = bob.get(f"/api/stream?since_notif={first['notif']}&since_msg={first['msg']}&wait=1").json()
    ev = [e for e in r["events"] if e["kind"] == "message"]
    assert ev and ev[0]["chat"] == "alice" and "привет из фона" in ev[0]["text"] and r["msg"] == ev[0]["id"]
    # повторный запрос с новым id — пусто
    r2 = bob.get(f"/api/stream?since_notif={r['notif']}&since_msg={r['msg']}&wait=1").json()
    assert not [e for e in r2["events"] if e["kind"] == "message"]
    assert make_client().get("/api/stream").status_code == 401


def test_starred_reminders_birthdays_similar(alice, bob):
    from datetime import datetime, timedelta
    from routers import features
    mid = alice.post("/messages/send", json={"receiver": "bob", "content": "адрес: Ленина 5"}, headers=J).json()["id"]
    # избранное
    assert bob.post(f"/messages/{mid}/star", headers=J).json()["starred"]
    assert "Ленина 5" in bob.get("/messages/starred").text
    assert "Ленина 5" not in alice.get("/messages/starred").text
    assert make_client().post(f"/messages/{mid}/star").status_code in (401, 303)
    # чужое сообщение отметить нельзя
    carol = register(make_client(), "carol")
    assert carol.post(f"/messages/{mid}/star", headers=J).status_code == 404
    # напоминание
    assert bob.post(f"/messages/{mid}/remind", json={"minutes": 20}, headers=J).json()["ok"]
    s = db()
    r = s.query(models.MessageReminder).first()
    r.remind_at = datetime.utcnow() - timedelta(seconds=1)
    s.commit()
    assert features.deliver_reminders(s) == 1 and features.deliver_reminders(s) == 0
    s.close()
    assert "напоминание о сообщении" in bob.get("/notifications").text
    # дни рождения
    bob.post("/follow/alice", headers=J)
    s = db()
    a = s.query(models.User).filter_by(username="alice").first()
    a.birthday = "2000" + datetime.utcnow().strftime("-%m-%d")
    s.commit()
    assert features.notify_birthdays(s) >= 1 and features.notify_birthdays(s) == 0
    s.close()
    page = bob.get("/birthdays").text
    assert "сегодня" in page and "Поздравить" in page
    # похожие посты по хэштегу
    p1 = alice.post("/post/create", data={"content": "Закат на море #море"}, headers=J, follow_redirects=False)
    alice.post("/post/create", data={"content": "Ещё волны #море"}, headers=J, follow_redirects=False)
    s = db()
    first = s.query(models.Post).filter(models.Post.content.like("Закат%")).first()
    s.close()
    assert "Похожие посты" in bob.get(f"/post/{first.id}").text and "Ещё волны" in bob.get(f"/post/{first.id}").text
    # вкладки чатов
    assert 'id="chat-tabs"' in bob.get("/messages").text


def test_v2_server_features(alice, bob):
    # «Что нового» открывается и в нём больше 100 пунктов
    page = alice.get("/whats-new")
    assert page.status_code == 200 and "функци" in page.text and "в Nuvora 3.1" in page.text
    from services.whatsnew import GROUPS
    assert sum(len(i) for _, _, i in GROUPS) >= 100
    # плашка «новые посты»
    bob.post("/follow/alice", headers=J)
    alice.post("/post/create", data={"content": "первый"}, headers=J)
    s = db()
    first = s.query(models.Post).order_by(models.Post.id.desc()).first().id
    s.close()
    alice.post("/post/create", data={"content": "второй"}, headers=J)
    assert bob.get(f"/api/feed/new?after={first}").json()["count"] == 1
    # прочитать все
    alice.post("/messages/send", json={"receiver": "bob", "content": "раз"}, headers=J)
    assert bob.post("/messages/read-all", headers=J).json()["count"] == 1
    # без звука на время
    assert bob.post("/chats/alice/mute-for", json={"hours": 8}, headers=J).json()["muted"]
    s = db()
    m = s.query(models.MutedChat).first()
    assert m.until is not None
    m.until = datetime.utcnow() - timedelta(minutes=1)
    s.commit()
    from routers import features
    features.cleanup(s)
    assert s.query(models.MutedChat).count() == 0
    s.close()
    # перенос настроек
    alice.post("/settings/prefs/feed", data={"feed_hide_polls": "on"})
    exported = alice.get("/settings/backup/export").content
    assert b"feed_hide_polls" in exported
    r = bob.post("/settings/backup/import", files={"file": ("s.json", exported, "application/json")}, headers=J).json()
    assert r["count"] > 10
    assert bob.post("/settings/backup/reset", headers=J).json()["ok"]
    # работа в профиле, календарь
    alice.post("/settings/profile", data={"name": "Alice", "work": "Дизайнер в студии"})
    assert "Дизайнер в студии" not in bob.get("/profile/alice").text  # поле «Работа или учёба» убрано
    assert bob.get("/calendar/birthdays.ics").text.startswith("BEGIN:VCALENDAR")


def test_v2_security_fixes(alice, bob):
    import auth
    # токен ожидания 2FA не даёт войти
    s = db()
    a = s.query(models.User).filter_by(username="alice").first()
    pending = auth.create_token({"uid": a.id, "purpose": "2fa", "exp": datetime.utcnow() + timedelta(minutes=5)})
    s.close()
    c = make_client()
    c.cookies.set("token", pending)
    assert c.get("/api/me").status_code in (401, 403) or not c.get("/api/me").json().get("ok", False)
    # нулевой байт в посте не роняет страницы
    alice.post("/post/create", data={"content": "hi \x000\x00 `x`"}, headers=J)
    assert alice.get("/").status_code == 200 and make_client().get("/explore").status_code == 200
    # отложенное сообщение не видно получателю ни в поиске, ни через fragment
    mid = alice.post("/messages/send", json={"receiver": "bob", "content": "сюрприз-секрет", "schedule": "60"}, headers=J).json()["id"]
    assert "сюрприз-секрет" not in bob.get("/messages/search?q=сюрприз").text
    assert bob.get(f"/messages/fragment/{mid}").status_code == 404
    assert bob.post(f"/messages/{mid}/star", headers=J).status_code == 404
    # нечисловой получатель не роняет сервер
    assert alice.post("/messages/send", json={"receiver": 5, "content": ["x"]}, headers=J).status_code < 500
    # мат: обычные слова не трогаем
    from services import profanity
    assert not profanity.is_bad("мандарин") and not profanity.is_bad("Себастьян") and profanity.is_bad("blyat")


def test_pack_slots_render(alice, bob):
    """Слоты модулей 3.0 видят нужные переменные (в том числе внутри макросов)."""
    import packs
    names = ["post_menu", "post_after_text", "profile_menu", "profile_after_bio", "chat_menu", "message_extra", "home_top",
             "chat_list_top", "settings_bottom", "explore_top", "notifications_top", "post_page", "composer_tools", "body_end"]
    for n in names:
        packs.SLOTS[n].append(f"packs/_selftest/{n}.html")
    try:
        alice.post("/post/create", data={"content": "слоты"}, headers=J)
        alice.post("/messages/send", json={"receiver": "bob", "content": "привет"}, headers=J)
        s = db()
        pid = s.query(models.Post).order_by(models.Post.id.desc()).first().id
        mid = s.query(models.Message).order_by(models.Message.id.desc()).first().id
        s.close()
        home = alice.get("/").text
        assert "SLOT-home_top" in home and "SLOT-body_end" in home
        page = bob.get(f"/post/{pid}").text
        assert "SLOT-post_after_text" in page and f'data-menu-src="/post/{pid}/menu"' in page
        assert f"SLOT-post_menu-{pid}" in bob.get(f"/post/{pid}/menu").text  # меню «⋯» подгружается по нажатию
        prof = bob.get("/profile/alice").text
        assert "SLOT-profile_menu" in prof and "-alice" in prof and "SLOT-profile_after_bio" in prof
        chat = bob.get("/messages/alice").text
        assert "SLOT-chat_menu" in chat and f"SLOT-message_extra-m{mid}" in chat
        assert "SLOT-chat_list_top" in bob.get("/messages").text
        assert "SLOT-settings_bottom" in bob.get("/settings?section=feed").text
        assert "SLOT-explore_top" in bob.get("/explore").text and "SLOT-notifications_top" in bob.get("/notifications").text
        assert "SLOT-post_page" in bob.get(f"/post/{pid}").text and "SLOT-composer_tools" in alice.get("/create").text
    finally:
        for n in names:
            packs.SLOTS[n].remove(f"packs/_selftest/{n}.html")


def test_bot_account_without_email():
    c = make_client()
    r = c.post("/register", data={"username": "claude_ai", "email": "-", "password": "secret123", "confirm_password": "secret123",
                                  "agree": "1", "consent": "1", "public": "1", "adult": "1"}, follow_redirects=False)
    assert r.status_code == 303
    u = db().query(models.User).filter_by(username="claude_ai").one()
    assert u.email == "claude_ai@bot.invalid" and u.email_verified and "ИИ" in u.name
    # обычным логинам почта по-прежнему нужна
    r = make_client().post("/register", data={"username": "someone1", "email": "-", "password": "secret123", "confirm_password": "secret123",
                                             "agree": "1", "consent": "1", "public": "1", "adult": "1"})
    assert "Некорректный email" in r.text


def test_liked_posts_sink_in_feed(alice, bob):
    from datetime import datetime, timedelta
    ids = [create_post(bob, f"пост {i}") for i in range(3)]
    bob.post("/follow/alice", headers=J); alice.post("/follow/bob", headers=J)
    alice.post(f"/like/{ids[-1]}", headers=J)  # самый новый
    s = db()
    for lk in s.query(models.Like).all():
        lk.created_at = datetime.utcnow() - timedelta(hours=2)
    s.commit(); s.close()
    page = alice.get("/?tab=following").text
    order = [int(x) for x in __import__("re").findall(r'id="post-(\d+)"', page) if int(x) in ids]
    assert order[-1] == ids[-1] and len(order) == 3  # лайкнутый на месте, но в конце


def test_compliance_pages_and_accessibility(alice, anon):
    for url, text in (("/refund", "Автопродления нет"), ("/licenses", "CC BY 4.0"), ("/privacy", "GigaChat")):
        r = anon.get(url)
        assert r.status_code == 200 and text.lower() in r.text.lower(), url
    assert "ЮKassa" in anon.get("/privacy").text and "<code>ref</code>" in anon.get("/privacy").text
    page = alice.get("/")
    assert 'class="skip-link" href="#main"' in page.text and 'id="main"' in page.text
    assert 'href="/refund"' in page.text
    # гость в поддержке без согласия — нельзя
    r = anon.post("/support", data={"email": "g@example.com", "subject": "Другое", "message": "Помогите"})
    assert "согласие" in r.text.lower()
    # у фото в посте есть описание для экранных дикторов
    pid = create_post(alice, "Закат над морем", files=[("media", ("a.png", png_bytes(), "image/png"))])
    assert 'alt="Закат над морем"' in alice.get(f"/post/{pid}").text


def test_public_consent_separate(alice, anon):
    page = anon.get("/consent/public").text
    assert "ст. 10.1" in page and "Настройки → Приватность" in page
    base = {"username": "nopublic", "email": "np@example.com", "password": "secret123", "confirm_password": "secret123",
            "agree": "1", "consent": "1", "adult": "1"}
    assert "согласие на распространение" in anon.post("/register", data=base).text
    assert db().query(models.User).filter_by(username="nopublic").first() is None
    # старые аккаунты видят просьбу дать согласие, пока не согласятся
    s = db(); u = s.query(models.User).filter_by(username="alice").one(); u.public_consent_at = None; s.commit(); s.close()
    assert "/consent/public/accept" in alice.get("/").text
    alice.post("/consent/public/accept")
    assert "/consent/public/accept" not in alice.get("/").text
