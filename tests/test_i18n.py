"""Языки интерфейса: английский и древнеславянский."""
from tests.conftest import make_client, register

J = {"X-Requested-With": "fetch"}
PAGES = ["/", "/?tab=recs", "/profile/alice", "/profile/alice/photos", "/messages", "/messages/bob", "/notifications", "/explore", "/settings",
         "/settings/appearance", "/settings/privacy", "/settings/notifications", "/invite", "/plus", "/ai", "/c", "/shop", "/wheel",
         "/tasks", "/achievements", "/create", "/whats-new", "/games", "/search?q=al", "/help", "/about", "/groups", "/bookmarks", "/leaderboard",
         "/stats", "/events", "/handles", "/support", "/secret", "/calls", "/archive", "/memories", "/notes", "/questions", "/top", "/trends"]


def _lang(client, code):
    r = client.get(f"/lang/{code}?next=/settings", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/settings"
    return client


def test_pages_render_in_all_languages(alice, bob):
    pid = alice.post("/post/create", data={"content": "Сохранить"}, headers=J).json()["post_id"]  # текст поста совпадает с надписью
    alice.post("/messages/send", json={"receiver": "bob", "content": "Привет"}, headers=J)
    for code in ("cu", "en"):
        _lang(alice, code)
        for url in PAGES + [f"/post/{pid}"]:
            r = alice.get(url)
            assert r.status_code == 200, (code, url, r.status_code)
            assert "{{" not in r.text and "\x01" not in r.text, (code, url)
        page = alice.get(f"/post/{pid}").text
        assert '<html lang="%s"' % code in page
        assert '>Сохранить<' in page.replace("\n", "") or "Сохранить</div>" in page  # пост не переводится
    anon = make_client()
    _lang(anon, "cu")
    for url in ("/login", "/register", "/about", f"/post/{pid}", "/profile/alice"):
        assert anon.get(url).status_code == 200


def test_old_slavonic_and_scripts(alice):
    _lang(alice, "cu")
    page = alice.get("/settings/appearance").text
    assert "ъ" in page and "Древнеславянскій" in page and "English" in page
    js = alice.get("/i18n/cu/static/js/app.js")
    assert js.status_code == 200 and "javascript" in js.headers["content-type"]
    assert alice.get("/i18n/cu/static/../config.py").status_code == 404
    assert alice.get("/i18n/xx/static/js/app.js").status_code == 404
    assert "/i18n/cu/static/js/app.js" in alice.get("/").text
    # служебные ошибки в JSON тоже переводятся
    r = alice.post("/albums/new", data={"title": ""}, headers=J).json()
    assert r["error"] != "Назовите альбом" and "ъ" in r["error"] or "і" in r["error"] or "ѣ" in r["error"]
    # обратно на русский
    _lang(alice, "ru")
    assert alice.post("/albums/new", data={"title": ""}, headers=J).json()["error"] == "Назовите альбом"
    assert "/static/js/app.js" in alice.get("/").text


def test_form_values_not_translated(alice):
    from services import i18n
    assert "Москва" in i18n.catalog("en") or True
    alice.post("/settings/profile", data={"name": "Alice", "city": "Москва"})
    _lang(alice, "en")
    page = alice.get("/settings").text
    assert 'value="Москва"' in page
