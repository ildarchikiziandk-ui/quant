"""Nuvora 3.0: 20 новых функций (packs/v3)."""
import re
from datetime import datetime, timedelta

import models
from database import SessionLocal
from packs.v3 import account, capsule, games, models as m
from tests.conftest import make_client, png_bytes, register
from tests.test_app import J, create_post


def db():
    return SessionLocal()


def friends(a, b):
    a.post("/follow/bob", headers=J)
    b.post("/follow/alice", headers=J)


def last_msg(sender="alice"):
    s = db()
    u = s.query(models.User).filter_by(username=sender).first()
    msg = s.query(models.Message).filter_by(sender_id=u.id).order_by(models.Message.id.desc()).first()
    s.close()
    return msg


def test_chat_poll(alice, bob):
    r = alice.post("/v3/chat/bob/poll", json={"question": "Куда идём?", "options": ["Кино", "Парк", ""], "multi": ""}, headers=J)
    assert r.json()["ok"], r.text
    msg = last_msg()
    kind, pid = msg.content[5:-2].split(":")
    assert kind == "poll"
    html = bob.get(f"/messages/fragment/{msg.id}").json()["html"]
    assert "Куда идём?" in html and "data-v3-vote" in html and "[[v3:" not in re.sub(r'data-[a-z]+="[^"]*"', "", html)
    assert bob.post(f"/v3/poll/{pid}/vote", json={"option": "1"}, headers=J).json()["ok"]
    assert bob.post(f"/v3/poll/{pid}/vote", json={"option": "0"}, headers=J).json()["ok"]  # один ответ: заменяет
    s = db()
    votes = s.query(m.ChatPollVote).filter_by(poll_id=int(pid)).all()
    assert [v.option for v in votes] == [0]
    s.close()
    assert "100%" in alice.get(f"/messages/fragment/{msg.id}").json()["html"]
    assert bob.post(f"/v3/poll/{pid}/close", headers=J).status_code in (403, 404)
    assert alice.post(f"/v3/poll/{pid}/close", headers=J).json()["ok"]
    assert bob.post(f"/v3/poll/{pid}/vote", json={"option": "1"}, headers=J).status_code >= 400
    eve = register(make_client(), "eve")
    assert eve.post(f"/v3/poll/{pid}/vote", json={"option": "1"}, headers=J).status_code == 404
    assert alice.post("/v3/chat/bob/poll", json={"question": "?", "options": ["один"]}, headers=J).status_code == 400
    # в списке чатов — понятная подпись, а не служебная разметка
    assert "Опрос" in bob.get("/messages").text


def test_chat_tictactoe(alice, bob):
    assert alice.post("/v3/chat/bob/ttt", headers=J).json()["ok"]
    gid = last_msg().content[5:-2].split(":")[1]
    assert bob.post(f"/v3/ttt/{gid}/move", json={"cell": "0"}, headers=J).status_code >= 400  # не его ход
    for who, cell in [(alice, 0), (bob, 3), (alice, 1), (bob, 4)]:
        assert who.post(f"/v3/ttt/{gid}/move", json={"cell": str(cell)}, headers=J).json()["ok"]
    assert alice.post(f"/v3/ttt/{gid}/move", json={"cell": "1"}, headers=J).status_code >= 400  # занято
    s = db()
    a_id = s.query(models.User).filter_by(username="alice").first().id
    s.close()
    assert alice.post(f"/v3/ttt/{gid}/move", json={"cell": "2"}, headers=J).json()["winner"] == a_id
    assert bob.post(f"/v3/ttt/{gid}/move", json={"cell": "8"}, headers=J).status_code >= 400
    assert bob.post(f"/v3/ttt/{gid}/rematch", headers=J).json()["ok"]
    assert last_msg("bob").content.startswith("[[v3:ttt:")
    eve = register(make_client(), "eve")
    assert eve.post(f"/v3/ttt/{gid}/move", json={"cell": "5"}, headers=J).status_code == 404


def test_message_effects(alice, bob):
    r = alice.post("/messages/send", json={"receiver": "bob", "content": "С днём рождения!", "effect": "confetti"}, headers=J)
    mid = r.json()["id"]
    assert 'data-effect="confetti"' in bob.get(f"/messages/fragment/{mid}").json()["html"]
    mid = alice.post("/messages/send", json={"receiver": "bob", "content": "x", "effect": "<script>"}, headers=J).json()["id"]
    assert "data-effect" not in bob.get(f"/messages/fragment/{mid}").json()["html"]


def test_chat_folders(alice, bob):
    r = alice.post("/v3/folders", json={"name": "Семья", "members": ["Bob", "bob"]}, headers=J)
    fid = r.json()["id"]
    f = alice.get("/v3/folders").json()["folders"]
    assert f == [{"id": fid, "name": "Семья", "members": ["bob"]}]
    alice.post("/v3/folders", json={"id": str(fid), "name": "Родные", "members": []}, headers=J)
    assert alice.get("/v3/folders").json()["folders"][0]["name"] == "Родные"
    assert bob.get("/v3/folders").json()["folders"] == []
    bob.post(f"/v3/folders/{fid}/delete", headers=J)
    assert len(alice.get("/v3/folders").json()["folders"]) == 1  # чужую папку удалить нельзя
    assert alice.post(f"/v3/folders/{fid}/delete", headers=J).json()["ok"]
    assert 'id="v3-folders"' in alice.get("/messages").text


def test_hide_author_30_days(alice, bob):
    from packs.v3 import feed
    pid = create_post(alice, "Пост")
    assert "Не показывать 30 дней" in bob.get(f"/post/{pid}/menu").text
    assert bob.post("/v3/hide/alice", headers=J).json()["ok"]
    s = db()
    tm = s.query(m.TempMute).one()
    assert tm.until > datetime.utcnow() + timedelta(days=29)
    tm.until = datetime.utcnow() - timedelta(minutes=1)
    s.commit()
    feed.unmute_expired(s)
    assert s.query(m.TempMute).count() == 0 and s.query(models.UserMute).count() == 0
    s.close()
    assert bob.post("/v3/hide/bob", headers=J).status_code >= 400



def test_daily_chest(alice):
    assert "data-v3-chest" in alice.get("/").text
    r = alice.post("/v3/chest", headers=J).json()
    assert r["reward"] == 3 and r["streak"] == 1
    assert alice.post("/v3/chest", headers=J).status_code == 400
    assert "data-v3-chest" not in alice.get("/").text
    s = db()
    row = s.query(m.DailyChest).one()
    row.last_day = (datetime.strptime(row.last_day, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    s.commit()
    s.close()
    assert alice.post("/v3/chest", headers=J).json() == {"ok": True, "reward": 5, "streak": 2}


def test_capsule(alice, bob):
    assert alice.post("/capsule", json={"text": "Привет из прошлого", "period": "1m"}, headers=J).json()["ok"]
    assert alice.post("/capsule", json={"text": "Привет", "period": "date", "date": "2000-01-01"}, headers=J).status_code == 400
    page = alice.get("/capsule").text
    assert "Запечатаны · 1" in page and "Привет из прошлого" not in page
    s = db()
    c = s.query(m.Capsule).one()
    c.open_at = datetime.utcnow() - timedelta(minutes=1)
    s.commit()
    capsule.capsules_due(s)
    assert s.query(models.Notification).filter_by(type="capsule").count() == 1
    capsule.capsules_due(s)
    assert s.query(models.Notification).filter_by(type="capsule").count() == 1
    cid = c.id
    s.close()
    assert "Привет из прошлого" in alice.get("/capsule").text
    assert "Привет из прошлого" not in bob.get("/capsule").text
    bob.post(f"/capsule/{cid}/delete", headers=J)
    assert "Привет из прошлого" in alice.get("/capsule").text


def test_word_game(alice):
    assert games.score("абвгд", "абвгд") == "ggggg"
    assert games.score("ааабв", "бааав") == "yggyg"
    assert len(games.WORDS) > 100 and all(len(w) == 5 for w in games.WORDS)
    assert alice.post("/games/word/guess", json={"word": "abc"}, headers=J).status_code == 400
    s = db()
    u = s.query(models.User).filter_by(username="alice").first()
    from packs.v3.common import today
    answer = games.word_of(today(u))
    s.close()
    wrong = next(w for w in games.WORDS if w != answer)
    r = alice.post("/games/word/guess", json={"word": wrong}, headers=J).json()
    assert len(r["rows"]) == 1 and not r["over"] and r["answer"] is None
    r = alice.post("/games/word/guess", json={"word": answer.upper()}, headers=J).json()
    assert r["solved"] and r["answer"] == answer
    assert alice.post("/games/word/guess", json={"word": wrong}, headers=J).status_code == 400
    assert "побед: 1 из 1" in alice.get("/games/word").text
    assert "Сыграно сегодня" in alice.get("/games").text


def test_2048_scores(alice, bob):
    assert alice.post("/games/2048/score", json={"score": "1200"}, headers=J).json() == {"ok": True, "best": 1200, "record": True}
    assert alice.post("/games/2048/score", json={"score": "800"}, headers=J).json()["best"] == 1200
    assert alice.post("/games/2048/score", json={"score": "-5"}, headers=J).status_code == 400
    bob.post("/follow/alice", headers=J)
    page = bob.get("/games/2048").text
    assert "Рекорды друзей" in page and "1200" in page


def test_backup_codes(alice):
    assert alice.post("/v3/backup-codes", headers=J).status_code == 400  # без 2FA нельзя
    page = alice.get("/settings?section=security")
    secret = page.cookies.get("totp_setup") or alice.cookies.get("totp_setup")
    import auth
    alice.post("/settings/2fa/enable", data={"code": auth.totp_now(secret)})
    codes = alice.post("/v3/backup-codes", headers=J).json()["codes"]
    assert len(codes) == 10 and all(re.fullmatch(r"\d{4}-\d{4}", c) for c in codes)
    c = make_client()
    c.post("/login", data={"username": "alice", "password": "secret123"})
    r = c.post("/login/2fa", data={"code": codes[0]}, follow_redirects=False)
    assert r.status_code == 303
    c2 = make_client()
    c2.post("/login", data={"username": "alice", "password": "secret123"})
    assert "Неверный код" in c2.post("/login/2fa", data={"code": codes[0]}).text  # код одноразовый
    s = db()
    u = s.query(models.User).filter_by(username="alice").first()
    assert account.backup_left(u) == 9
    assert s.query(models.Notification).filter_by(user_id=u.id, type="security").count() >= 1
    s.close()


def test_new_device_alert(alice):
    s = db()
    account.new_device_alerts(s)  # первый запуск запоминает уже известные устройства
    before = s.query(models.Notification).filter_by(type="security").count()
    s.close()
    c = make_client()
    c.headers["User-Agent"] = "Mozilla/5.0 (Linux; Android 14; Pixel 8) Chrome/120"
    c.post("/login", data={"username": "alice", "password": "secret123"})
    s = db()
    account.new_device_alerts(s)
    assert s.query(models.Notification).filter_by(type="security").count() == before + 1
    account.new_device_alerts(s)
    assert s.query(models.Notification).filter_by(type="security").count() == before + 1
    s.close()


def test_pages_render(alice):
    for url in ["/capsule", "/games", "/games/word", "/games/2048", "/help", "/help?q=пароль", "/handles", "/ai",
                "/whats-new", "/notifications"]:
        r = alice.get(url)
        assert r.status_code == 200, url
        assert "Traceback" not in r.text
    assert "Центр помощи" in alice.get("/help").text
    assert "v3.js" in alice.get("/").text
    anon = make_client()
    for url in ["/capsule", "/games", "/handles"]:
        r = anon.get(url, follow_redirects=False)
        assert r.status_code in (200, 303), url


def test_fathers_day_card():
    r = make_client().get("/dayyot")
    assert r.status_code == 200 and "С Днём" in r.text and "Ильдар" in r.text



def test_nuva_answers(alice):
    from packs.v3 import ai
    assert "Нува" in alice.get("/ai").text
    ask = lambda q: alice.post("/ai/chat", json={"question": q}, headers=J).json()
    assert "Привет" in ask("привет")["text"]
    r = ask("как поставить двухфакторку?")
    assert "двухфакторную" in r["text"].lower()
    assert "Забыл пароль" in ask("я забыл пароль, что делать")["text"]
    assert "опрос" in ask("как сделать голосование в переписке")["text"].lower()
    assert "подписи" in ask("придумай подпись к фото с моря")["text"]
    assert "рожд" in ask("поздравление с днём рождения")["text"]
    r = ask("какая столица Монголии")
    assert "не знаю" in r["text"] and r["tips"]
    assert alice.post("/ai/chat", json={"question": ""}, headers=J).status_code == 400
    assert make_client().post("/ai/chat", json={"question": "привет"}, headers=J).status_code == 401
    assert ask("как удалить акаунт")["text"].startswith("Как удалить аккаунт?")
    assert ai.enabled()


def test_nuva_fix_text_and_tags(alice):
    from packs.v3 import ai
    assert ai.fix_text("севодня атличный день но я незнаю куда пойти") == "Сегодня отличный день, но я не знаю куда пойти."
    assert ai.fix_text("привет ,как дела?кто то идёт гулять") == "Привет, как дела? Кто-то идёт гулять."
    assert ai.fix_text("Всё хорошо.") == "Всё хорошо."
    tags = ai.hashtags("Вечер на море, красивый закат #фото")
    assert "море" in tags and "закат" in tags and "фото" not in tags
    assert "data-ai-rewrite" in alice.get("/create").text
    r = alice.post("/ai/rewrite", json={"text": "превет мир как дела", "mode": "fix"}, headers=J).json()
    assert r["text"] == "Привет мир как дела."
    r = alice.post("/ai/rewrite", json={"text": "Гуляли в парке с собакой", "mode": "tags"}, headers=J).json()
    assert "#парк" in r["text"] and "#собака" in r["text"]
    assert alice.post("/ai/rewrite", json={"text": "привет", "mode": "hack"}, headers=J).status_code == 400


def test_nuva_understands_russian(alice):
    from packs.v3 import nuva_lang as lang
    assert lang.stem("паролем") == lang.stem("пароля") == lang.stem("пароль")
    assert lang.from_layout("rfr cvtybnm gfhjkm") == "как сменить пароль"
    assert lang.squeeze("приииивет") == "привет"
    ask = lambda q, prev="": alice.post("/ai/chat", json={"question": q, "prev": prev}, headers=J).json()
    assert ask("забыл пороль")["text"].startswith("Забыл пароль")              # опечатка
    r = ask("rfr cvtybnm gfhjkm")                                              # английская раскладка
    assert "раскладке" in r["text"] and "Как сменить пароль?" in r["text"]
    assert r["links"] == [{"url": "/settings?section=account", "title": "Сменить пароль"}]
    assert ask("у меня украли аккаунт")["text"].startswith("Аккаунт взломали")  # синонимы
    assert ask("а где это найти", prev="что такое резервные коды")["text"].startswith("Что такое резервные коды")  # уточнение
    assert "Из нового" in ask("что нового?")["text"]


def test_nuva_admin_teaching(alice, owner):
    q = "как запустить прямой эфир"
    r = alice.post("/ai/chat", json={"question": q}, headers=J).json()
    assert not r["found"]
    alice.post("/ai/chat", json={"question": "Как запустить прямой эфир?"}, headers=J)
    from packs.v3 import models as pm
    s = db()
    miss = s.query(pm.NuvaMiss).one()
    assert miss.count == 2
    mid = miss.id
    s.close()
    assert alice.get("/ai/admin").status_code == 403
    assert alice.post("/ai/admin/answer", json={"question": "x", "answer": "y"}, headers=J).status_code == 403
    page = owner.get("/ai/admin").text
    assert "прямой эфир" in page
    assert owner.post("/ai/admin/answer", json={"question": "Обложка", "answer": "Ответ", "link_url": "javascript:alert(1)"}, headers=J).status_code == 400
    r = owner.post("/ai/admin/answer", json={"question": "Как запустить прямой эфир?", "keywords": "стрим трансляция",
                                             "answer": "Прямых эфиров пока нет — мы над ними работаем.", "link_url": "/whats-new",
                                             "link_title": "Что нового", "miss_id": str(mid)}, headers=J).json()
    assert r["ok"]
    s = db()
    assert s.query(pm.NuvaMiss).count() == 0
    s.close()
    r = alice.post("/ai/chat", json={"question": "можно начать стрим?"}, headers=J).json()
    assert r["found"] and "мы над ними работаем" in r["text"] and r["links"][0]["url"] == "/whats-new"
    assert owner.post(f"/ai/admin/answer/{r and 1}/delete", headers=J).json()["ok"]
    assert "Обучить" in owner.get("/ai").text and "Обучить" not in alice.get("/ai").text


def test_app_offline_and_static_version(alice):
    import os
    import config
    from services import assets
    v = assets.static_version(os.path.join(config.BASE_DIR, "static"))
    assert v == config.STATIC_V == assets.static_version(os.path.join(config.BASE_DIR, "static"))  # не меняется при перезапуске
    assert f"/static/css/app.css?v={v}" in alice.get("/").text
    page = make_client().get("/offline").text
    assert "Нет подключения" in page and "2048" in page
    sw = make_client().get("/sw.js").text
    assert "pages-v1" in sw and f"app-{v}" in sw


def test_ui_declutter(alice):
    home = alice.get("/").text
    assert 'id="today-card"' in home and "v3-quick" not in home and 'href="/market"' not in home
    prof = alice.get("/profile/alice").text
    assert "profile-more" in prof and "profile-stats tiles" in prof and "/ask/" not in prof
    sett = alice.get("/settings?section=profile").text
    assert sett.count("link-extra") >= 1 and "Ещё ссылка" in sett
    notes = alice.get("/notifications").text
    assert "v3-group-chip" in notes and "@ Упоминания" not in notes


def test_beautiful_handles(alice, owner):
    from services import handles
    c = make_client()
    form = {"email": "x@example.com", "password": "secret123", "confirm_password": "secret123", "agree": "1", "consent": "1", "public": "1", "adult": "1", "name": "X"}
    r = c.post("/register", data={**form, "username": "Love"}, follow_redirects=False)
    assert r.status_code != 303 and "зарезервирован" in r.text
    r = c.post("/register", data={**form, "username": "fox"}, follow_redirects=False)
    assert r.status_code != 303 and "искр" in r.text
    r = alice.post("/settings/username", data={"username": "lucky", "password": "secret123"})
    assert "Магазине логинов" in r.text
    page = alice.get("/handles").text
    assert 'data-v3-handle="lucky"' in page and 'data-v3-handle="love"' not in page and "заповедных" in page
    assert alice.post("/handles/buy", json={"username": "lucky", "password": "secret123"}, headers=J).status_code == 400  # нет баллов
    s = db()
    u = s.query(models.User).filter_by(username="alice").first()
    u.total_points = (u.total_points or 0) + 5000
    s.commit()
    s.close()
    assert alice.post("/handles/buy", json={"username": "lucky", "password": "wrong"}, headers=J).status_code == 400
    assert alice.post("/handles/buy", json={"username": "love", "password": "secret123"}, headers=J).status_code == 400  # заповедный
    r = alice.post("/handles/buy", json={"username": "Lucky", "password": "secret123"}, headers=J).json()
    assert r["username"] == "lucky"
    s = db()
    u = s.query(models.User).filter_by(username="lucky").first()
    assert u and u.spent_points == handles.PREMIUM["lucky"]
    s.close()
    assert 'data-v3-handle="lucky"' not in alice.get("/handles").text  # проданный исчез из витрины
    assert alice.get("/profile/lucky").status_code == 200
    # владелец может занять заповедный логин
    r = owner.post("/settings/username", data={"username": "star", "password": "secret123"})
    assert "@star" in r.text



def test_removed_sections(alice):
    for url in ["/market", "/habits", "/mood", "/links", "/friends", "/random", "/guests", "/notes", "/memories", "/wheel", "/questions"]:
        r = alice.get(url, follow_redirects=False)
        assert r.status_code in (303, 404), url
    assert alice.post("/wheel/spin", headers=J).status_code == 404
    menu = alice.get("/").text
    for word in ["Барахолка", "Привычки", "Дневник настроения", "Колесо фортуны", "Гости профиля", "Заметки"]:
        assert word not in menu, word
    assert "Капсула времени" in menu  # капсулу оставили


def test_up_to_three_logins(alice, bob, owner):
    from packs.v3 import handles_shop
    r = alice.post("/settings/aliases/add", json={"handle": "alice_two", "password": "secret123"}, headers=J).json()
    assert r["handle"] == "alice_two"
    assert alice.post("/settings/aliases/add", json={"handle": "bob", "password": "secret123"}, headers=J).status_code == 400  # занят
    assert alice.post("/settings/aliases/add", json={"handle": "lucky", "password": "secret123"}, headers=J).status_code == 400  # за баллы
    assert alice.post("/settings/aliases/add", json={"handle": "x3_alice", "password": "nope"}, headers=J).status_code == 400
    assert alice.post("/settings/aliases/add", json={"handle": "x3_alice", "password": "secret123"}, headers=J).json()["ok"]
    r = alice.post("/settings/aliases/add", json={"handle": "x4_alice", "password": "secret123"}, headers=J)
    assert r.status_code == 400 and "не больше 3" in r.json()["error"]
    # занятый дополнительный логин нельзя взять при регистрации и смене логина
    assert "уже занят" in bob.post("/settings/username", data={"username": "alice_two", "password": "secret123"}).text
    # профиль и переписка по дополнительному логину ведут к основному
    assert bob.get("/profile/alice_two", follow_redirects=False).headers["location"] == "/profile/alice"
    assert "@alice_two" in bob.get("/profile/alice").text
    # вход по дополнительному логину
    c = make_client()
    assert c.post("/login", data={"username": "alice_two", "password": "secret123"}, follow_redirects=False).status_code == 303
    # сделать основным
    assert alice.post("/settings/aliases/alice_two/primary", headers=J).json()["username"] == "alice_two"
    assert bob.get("/profile/alice", follow_redirects=False).headers["location"] == "/profile/alice_two"
    assert alice.post("/settings/aliases/alice/delete", headers=J).json()["ok"]
    assert bob.get("/profile/alice").status_code == 404
    # покупка красивого логина дополнительным
    s = db()
    u = s.query(models.User).filter_by(username="alice_two").first()
    u.total_points = 10000
    s.commit()
    s.close()
    r = alice.post("/handles/buy", json={"username": "lucky", "password": "secret123", "mode": "alias"}, headers=J).json()
    assert r["alias"] and r["username"] == "alice_two"
    assert "data-v3-handle=\"lucky\"" not in alice.get("/handles").text
    # владелец получает свои логины автоматически
    handles_shop._seeded.clear()
    s = db()
    handles_shop.seed_owner_aliases(s)
    own = s.query(models.User).filter_by(username="owner").first()
    assert sorted(a.handle for a in s.query(m.UserAlias).filter_by(user_id=own.id)) == ["ildar", "mint"]
    s.close()
    assert "зарезервирован" in bob.post("/settings/username", data={"username": "rubl", "password": "secret123"}).text


def test_owner_admin_powers(owner, alice, bob):
    assert alice.get("/admin/u/bob", follow_redirects=False).status_code == 303  # не админ
    page = owner.get("/admin/u/alice").text
    assert "Переписку администратор не видит" in page and "alice@example.com" in page
    alice.post("/messages/send", json={"receiver": "bob", "content": "секретный текст"}, headers=J)
    assert "секретный текст" not in owner.get("/admin/u/alice").text  # переписка не видна
    r = owner.post("/admin/u/alice/save", data={"name": "Алиса", "username": "love", "email": "a2@example.com", "bio": "", "city": "Казань"}, follow_redirects=False)
    assert "/admin/u/love" in r.headers["location"]
    s = db()
    u = s.query(models.User).filter_by(username="love").one()
    assert u.email == "a2@example.com" and u.city == "Казань"
    s.close()
    owner.post("/admin/u/love/alias-add", data={"handle": "star"})
    assert bob.get("/profile/star", follow_redirects=False).headers["location"] == "/profile/love"
    owner.post("/admin/u/love/balance", data={"balance": "777"})
    s = db()
    from services import extras
    assert extras.balance(s.query(models.User).filter_by(username="love").one()) == 777
    s.close()
    owner.post("/admin/u/love/notify", data={"text": "Привет от администрации"})
    assert "Привет от администрации" in alice.get("/notifications").text
    owner.post("/admin/u/love/logout-all")
    assert alice.get("/settings", follow_redirects=False).status_code in (302, 303)  # разлогинен
    owner.post("/admin/u/love/block", data={"days": "3", "reason": "спам"})
    s = db()
    assert s.query(models.User).filter_by(username="love").one().is_blocked
    s.close()
    owner.post("/admin/u/love/unblock")
    # сайт: выключить раздел, закрыть регистрацию, тех. работы
    assert owner.post("/admin/site/save", data={"on": ["/games", "/capsule"], "registration": "", "maintenance": "", "maintenance_text": "x"},
                      follow_redirects=False).status_code == 303
    from packs.v3 import site
    site._cache["t"] = 0
    assert bob.get("/handles", follow_redirects=False).status_code == 303 and bob.get("/games").status_code == 200
    c = make_client()
    r = c.post("/register", data={"username": "newbie", "email": "n@example.com", "password": "secret123", "confirm_password": "secret123",
                                  "agree": "1", "consent": "1", "public": "1", "adult": "1", "name": "N"}, follow_redirects=False)
    assert r.status_code != 303 and "закрыта" in r.text
    owner.post("/admin/site/save", data={"on": [p for p, _ in site.SECTIONS], "registration": "1", "maintenance": "1", "maintenance_text": "Чиним"})
    site._cache["t"] = 0
    r = bob.get("/")
    assert r.status_code == 503 and "Чиним" in r.text
    assert owner.get("/").status_code == 200  # владелец видит сайт
    owner.post("/admin/site/save", data={"on": [p for p, _ in site.SECTIONS], "registration": "1", "maintenance": "", "maintenance_text": "x"})
    site._cache["t"] = 0
    # рассылка всем
    owner.post("/admin/site/notify-all", data={"text": "Вышло обновление"})
    assert "Вышло обновление" in bob.get("/notifications").text


def test_calls(alice, bob):
    from packs.v3 import calls
    sdp = "v=0\r\no=- 1 2 IN IP4 127.0.0.1\r\ns=-\r\n"
    # кнопки звонка в шапке переписки
    html = alice.get("/messages/bob").text
    assert 'data-call="bob"' in html and 'data-video' not in html  # только голосовые звонки
    # первый долгий запрос bob: только курсор и адреса STUN
    first = bob.get("/v3/call/poll?since=-1").json()
    assert first["ok"] and first["events"] == [] and first["ice"]
    # плохой запрос и звонок самому себе
    assert alice.post("/v3/call/bob/start", json={"video": 1}, headers=J).status_code == 400
    assert alice.post("/v3/call/alice/start", json={"video": 1, "offer": {"type": "offer", "sdp": sdp}}, headers=J).status_code == 404
    r = alice.post("/v3/call/bob/start", json={"video": 1, "offer": {"type": "offer", "sdp": sdp}}, headers=J).json()
    assert r["ok"] and r["peer"]["username"] == "bob"
    cid = r["call"]
    # второй звонок, пока идёт первый, — нельзя
    assert not alice.post("/v3/call/bob/start", json={"video": 0, "offer": {"type": "offer", "sdp": sdp}}, headers=J).json()["ok"]
    ev = bob.get(f"/v3/call/poll?since={first['last']}&wait=1").json()["events"]
    ring = [e for e in ev if e["kind"] == "ring"][0]
    assert ring["call"] == cid and not ring["video"] and ring["offer"]["sdp"] == sdp and ring["from"]["username"] == "alice"
    # открытая заново страница тоже видит идущий звонок
    assert any(e["kind"] == "ring" for e in bob.get("/v3/call/poll?since=-1").json()["events"])
    s = db()
    n = s.query(models.Notification).filter_by(type="call").first()
    assert n and "звонит вам" in n.text
    s.close()
    # постороннему звонок не виден
    carol = make_client()
    register(carol, "carol")
    assert carol.post(f"/v3/call/{cid}/signal", json={"kind": "hangup"}, headers=J).status_code == 404
    # адреса, ответ, сигналы доходят до собеседника
    alice.post(f"/v3/call/{cid}/signal", json={"kind": "ice", "candidates": [{"candidate": "candidate:1 1 udp 1 1.2.3.4 5 typ host", "sdpMid": "0"}]}, headers=J)
    assert not alice.post(f"/v3/call/{cid}/signal", json={"kind": "answer", "answer": {"type": "answer", "sdp": sdp}}, headers=J).json()["ok"]
    assert bob.post(f"/v3/call/{cid}/signal", json={"kind": "answer", "answer": {"type": "answer", "sdp": sdp}, "tab": "t1"}, headers=J).json()["ok"]
    ev = alice.get("/v3/call/poll?since=0&wait=1").json()["events"]
    assert [e["kind"] for e in ev] == ["answer"]
    bev = bob.get(f"/v3/call/poll?since={ring['id']}&wait=1").json()["events"]
    assert {"ice", "taken"} <= {e["kind"] for e in bev}
    s = db()
    assert s.get(m.Call, cid).status == "active" and not s.query(models.Notification).filter_by(type="call").first()
    s.close()
    # завершение: «конец» обоим и запись в переписке
    assert bob.post(f"/v3/call/{cid}/signal", json={"kind": "hangup"}, headers=J).json()["ok"]
    assert any(e["kind"] == "end" and e["status"] == "ended" for e in alice.get("/v3/call/poll?since=0&wait=1").json()["events"])
    msg = last_msg("alice")
    assert msg.content == f"[[v3:call:{cid}]]"
    page = bob.get("/messages/alice").text
    assert "Входящий звонок" in page and "Перезвонить" in page and "[[v3:call" not in re.sub(r'data-[a-z]+="[^"]*"', "", page)
    assert "Исходящий звонок" in alice.get("/messages/bob").text
    # без ответа: звонок становится пропущенным, уведомление остаётся
    r2 = alice.post("/v3/call/bob/start", json={"video": 0, "offer": {"type": "offer", "sdp": sdp}}, headers=J).json()
    s = db()
    c2 = s.get(m.Call, r2["call"])
    c2.created_at = datetime.utcnow() - timedelta(minutes=5)
    s.commit()
    calls.expire_job(s)
    assert s.get(m.Call, r2["call"]).status == "missed"
    assert s.query(models.Notification).filter_by(type="call").first().text == "пропущенный звонок"
    s.close()
    assert "Пропущенный" in bob.get("/messages/alice").text
    # отклонение
    r3 = alice.post("/v3/call/bob/start", json={"video": 1, "offer": {"type": "offer", "sdp": sdp}}, headers=J).json()
    assert bob.post(f"/v3/call/{r3['call']}/signal", json={"kind": "decline"}, headers=J).json()["ok"]
    s = db()
    assert s.get(m.Call, r3["call"]).status == "declined"
    s.close()


def test_turn_credentials(alice, monkeypatch):
    import base64, hashlib, hmac
    import config
    monkeypatch.setattr(config, "TURN_SECRET", "s3cret")
    monkeypatch.setattr(config, "TURN_HOST", "turn.example")
    ice = alice.get("/v3/call/ice").json()["ice"]
    turn = [x for x in ice if "username" in x][0]
    assert turn["urls"][0] == "turn:turn.example:3478?transport=udp"
    exp = base64.b64encode(hmac.new(b"s3cret", turn["username"].encode(), hashlib.sha1).digest()).decode()
    assert turn["credential"] == exp and int(turn["username"].split(":")[0]) > datetime.utcnow().timestamp()


def test_moderation_posts_only(alice, bob):
    # пост и комментарий с матом не публикуются
    r = alice.post("/post/create", data={"content": "ну ты и xyйня"}, headers=J)
    assert r.status_code == 400 and "Не опубликовано" in r.json()["error"]
    pid = create_post(alice, "Нормальный пост")
    r = bob.post(f"/post/{pid}/comment", json={"content": "блять"}, headers=J)
    assert r.status_code == 400
    # в личной переписке текст не меняется
    friends(alice, bob)
    assert alice.post("/messages/send", json={"receiver": "bob", "content": "блять, опоздал"}, headers=J).json()["ok"]
    assert last_msg("alice").content == "блять, опоздал"


def test_stickers(alice, bob):
    friends(alice, bob)
    packs = alice.get("/v3/stickers").json()["packs"]
    assert [p["id"] for p in packs] == ["nuvi", "mur", "kapi"] and sum(len(p["stickers"]) for p in packs) == 41
    assert alice.post("/messages/send", json={"receiver": "bob", "content": "[[v3:st:privet]]"}, headers=J).json()["ok"]
    html = bob.get("/messages/alice").text
    assert "/static/stickers/nuvi/privet.webp" in html and 'title="Стикеры"' in html
    # подделать служебную карточку (чужой опрос, звонок) нельзя
    assert alice.post("/messages/send", json={"receiver": "bob", "content": "[[v3:poll:1]]"}, headers=J).status_code == 400
    assert alice.post("/messages/send", json={"receiver": "bob", "content": "[[v3:st:nope]]"}, headers=J).status_code == 400


def test_chat_media_expire(alice, bob, tmp_path):
    import os
    import config
    from packs.v3 import media
    friends(alice, bob)
    r = alice.post("/messages/send-media", data={"receiver": "bob"}, files={"file": ("clip.mp4", b"\x00\x00\x00\x18ftypmp42" + b"0" * 2000, "video/mp4")}, headers=J)
    assert r.json()["ok"]
    msg = last_msg("alice")
    assert msg.image.endswith(".mp4") and not msg.file_url  # видео — плеером, не файлом
    assert "att-video" in bob.get("/messages/alice").text
    path = os.path.join(config.UPLOAD_DIR, os.path.basename(msg.image))
    assert os.path.exists(path)
    s = db()
    row = s.get(models.Message, msg.id)
    row.created_at = datetime.utcnow() - timedelta(days=8)
    s.commit()
    assert media.expire_chat_media(s) >= 1
    row = s.get(models.Message, msg.id)
    assert row.image == "" and row.media_expired == "video" and not os.path.exists(path)
    s.close()
    assert "Видео удалено" in bob.get("/messages/alice").text


def test_app_update(alice, monkeypatch, tmp_path):
    import config
    from packs.v3 import appupdate
    monkeypatch.setattr(config, "APP_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(appupdate, "latest", lambda: {"version_code": 42, "version": "1.0.42", "apk": "https://example.com/Nuvora.apk", "size": 3})
    monkeypatch.setattr(appupdate, "_mirror", lambda info: None)
    j = alice.get("/api/app/latest").json()
    assert j["version_code"] == 42 and j["url"].endswith("/download/android.apk?v=42")
    r = alice.get("/download/android.apk", follow_redirects=False)  # копии ещё нет — пока отдаём с GitHub
    assert r.status_code == 302 and r.headers["location"] == "https://example.com/Nuvora.apk"
    (tmp_path / "Nuvora-42.apk").write_bytes(b"apk")
    r = alice.get("/download/android.apk", follow_redirects=False)
    assert r.status_code == 200 and r.content == b"apk"
    page = alice.get("/app").text
    assert "На экран «Домой»" in page and "/download/android.apk" in page


def test_admin_more(owner, alice, bob):
    from packs.v3 import admin_plus, site
    from services import handles
    pid = create_post(alice, "Пост для проверки админки")
    assert alice.get("/admin/posts", follow_redirects=False).status_code in (302, 303)
    page = owner.get("/admin/posts?q=админки").text
    assert "Пост для проверки админки" in page
    assert "Пост для проверки админки" in owner.get("/admin/posts?q=@alice").text
    owner.post(f"/admin/posts/{pid}/hide")
    assert bob.get(f"/post/{pid}").status_code == 404 and "Пост для проверки" in owner.get("/admin/posts?f=held").text
    owner.post(f"/admin/posts/{pid}/publish")
    assert bob.get(f"/post/{pid}").status_code == 200
    owner.post(f"/admin/posts/{pid}/delete")
    s = db(); assert s.get(models.Post, pid) is None; s.close()
    # статистика, хранилище, выгрузка
    st = owner.get("/admin/stats").text
    assert "DAU" in st and "Сообщения (только число)" in st and "Звонки за 30 дней" in st
    assert "Вложения в чатах" in owner.get("/admin/storage").text
    assert "Стёрто вложений" in owner.post("/admin/storage/chat-media").text
    csv = owner.get("/admin/export/users.csv")
    assert csv.status_code == 200 and "alice" in csv.text and "attachment" in csv.headers["content-disposition"]
    assert alice.get("/admin/stats", follow_redirects=False).status_code in (302, 303)
    # настройки сайта: звонки, стикеры, логины, IP
    friends(alice, bob)
    owner.post("/admin/site/save", data={"on": [p for p, _ in site.SECTIONS], "registration": "1", "pack": ["nuvi"],
                                         "reserved": "Support @helpdesk", "banned_ips": "203.0.113.7\n10.1.0.0/16\nнеадрес"})
    site._cache["t"] = 0
    assert 'data-call="bob"' not in alice.get("/messages/bob").text  # звонки выключены
    assert alice.post("/v3/call/bob/start", json={"offer": {"type": "offer", "sdp": "v=0"}}, headers=J).status_code == 403
    assert [p["id"] for p in alice.get("/v3/stickers").json()["packs"]] == ["nuvi"]
    assert alice.post("/messages/send", json={"receiver": "bob", "content": "[[v3:st:mur-myau]]"}, headers=J).status_code == 400
    assert handles.check("support") and handles.check("helpdesk") and not handles.check("support2")
    assert admin_plus.ip_banned("203.0.113.7") and admin_plus.ip_banned("10.1.200.3") and not admin_plus.ip_banned("10.2.0.1")
    assert site.get("banned_ips") == ["203.0.113.7", "10.1.0.0/16"]
    site._cache["t"] = 0; site._cache["v"] = dict(site.DEFAULTS)  # не тащим настройки в другие тесты


def test_follow_owner_and_chat_only(owner, alice):
    from packs.v3 import accounts
    s = db()
    o = s.query(models.User).filter_by(username="owner").one()
    a = s.query(models.User).filter_by(username="alice").one()
    assert s.query(models.Follow).filter_by(follower_id=a.id, following_id=o.id).first()  # подписка при регистрации
    s.query(models.Follow).delete(); s.commit()
    accounts.seed_job(s)  # разовая подписка всех существующих
    assert s.query(models.Follow).filter_by(follower_id=a.id, following_id=o.id).count() == 1
    s.close()
    # @svetlana: только чаты и профиль
    pid = create_post(alice, "Пост Алисы для всех")
    sv = make_client()
    register(sv, "sveta_x")  # @svetlana — платный логин: выдаём через админку
    owner.post("/admin/u/sveta_x/save", data={"name": "Светлана", "username": "svetlana", "email": "sveta_x@example.com"})
    assert sv.get("/", follow_redirects=False).headers["location"] == "/messages"
    r = sv.post("/post/create", data={"content": "Хочу опубликовать"}, headers=J)
    assert r.status_code == 403 and "отключена" in r.json()["error"]
    assert sv.get(f"/post/{pid}").status_code == 404
    assert "Пост Алисы для всех" not in sv.get("/profile/alice").text
    assert "Пост Алисы для всех" not in sv.get("/search?q=Алисы").text
    assert sv.get("/messages").status_code == 200 and sv.get("/profile/svetlana").status_code == 200
    assert sv.post("/messages/send", json={"receiver": "alice", "content": "Привет!"}, headers=J).json()["ok"]
    # истории: чужие не видны, свои публиковать нельзя
    alice.post("/stories/create", data={"text_overlay": "История Алисы", "bg": "violet"})
    assert "История Алисы" not in sv.get("/stories/alice").text
    assert sv.get("/stories/create").status_code == 403
    assert sv.post("/stories/create", data={"text_overlay": "Моя"}, headers=J).status_code == 403
    s = db(); accounts.seed_job(s); s.close()
    # владелец может выключить режим в карточке
    owner.post("/admin/u/svetlana/posts-lock")
    assert sv.post("/post/create", data={"content": "Теперь можно"}, headers=J).json()["ok"]
    assert sv.get(f"/post/{pid}").status_code == 200



def test_chat_only_alias(owner):
    from packs.v3 import accounts, site
    c = make_client()
    register(c, "lana_x")
    assert c.get("/", follow_redirects=False).status_code == 200
    owner.post("/admin/u/lana_x/alias-add", data={"handle": "svetlana"})  # @svetlana — дополнительный логин
    s = db(); accounts.seed_job(s); s.close()
    site._cache["t"] = 0
    assert c.get("/", follow_redirects=False).headers["location"] == "/messages"
    owner.post("/admin/u/lana_x/posts-lock")  # выключили вручную — задача не включает снова
    s = db(); accounts.seed_job(s); s.close()
    site._cache["t"] = 0
    assert c.get("/", follow_redirects=False).status_code == 200



def test_owner_perks(owner, alice):
    from services import extras, gamification, social
    s = db()
    o = s.query(models.User).filter_by(username="owner").one()
    assert social.is_plus(o) and extras.balance(o) >= 10 ** 9
    assert "навсегда" in owner.get("/plus").text and "∞" in owner.get("/handles").text
    # покупка не уменьшает бесконечные баллы
    r = owner.post("/handles/buy", json={"name": "fox", "username": "fox", "handle": "fox"}, headers=J)
    assert r.status_code in (200, 400), r.text
    assert extras.balance(s.query(models.User).filter_by(username="owner").one()) >= 10 ** 9
    # розыгрыш: владелец не участвует
    gamification._add_raffle_ticket(o, s)
    raffle = gamification.current_raffle(s)
    assert not s.query(models.RaffleEntry).filter_by(raffle_id=raffle.id, user_id=o.id).first()
    a = s.query(models.User).filter_by(username="alice").one()
    s.add(models.RaffleEntry(raffle_id=raffle.id, user_id=o.id, tickets=50)); s.add(models.RaffleEntry(raffle_id=raffle.id, user_id=a.id, tickets=1)); s.commit()
    assert gamification.draw_raffle(s, raffle).winner_id == a.id
    s.close()


def test_login_without_phone_confirmation(owner, alice):
    """Подтверждение входа на телефоне убрано: владелец входит со второго устройства сразу."""
    c = make_client()
    r = c.post("/login", data={"username": "owner", "password": "secret123"}, follow_redirects=False)
    assert r.status_code == 303 and "/login" not in r.headers["location"]
    assert c.get("/settings").status_code == 200
    assert "Спрашивать подтверждение" not in owner.get("/settings/security").text
    assert "la" not in owner.get("/api/counters").json()


def _uid(name):
    s = db()
    try:
        return s.query(models.User).filter_by(username=name).first().id
    finally:
        s.close()


def test_chat_games(alice, bob):
    mv = lambda c, gid, v: c.post(f"/v3/game/{gid}/move", json={"v": str(v)}, headers=J)
    gid_of = lambda: last_msg().content[5:-2].split(":")[1]
    page = lambda c: c.get("/messages/alice" if c is bob else "/messages/bob").text
    # камень-ножницы-бумага: выбор соперника скрыт, пока оба не выбрали; до двух побед
    assert alice.post("/v3/chat/bob/game", json={"kind": "rps"}, headers=J).json()["ok"]
    g = gid_of()
    assert mv(alice, g, "r").json()["ok"]
    assert mv(alice, g, "p").status_code >= 400  # ждёт соперника
    assert "ждём соперника" in page(alice) and "✊" not in page(bob).split("Камень, ножницы, бумага")[1][:400]
    mv(bob, g, "s")  # 1:0
    mv(alice, g, "p"); mv(bob, g, "p")  # ничья в раунде
    mv(alice, g, "p")
    assert mv(bob, g, "r").json()["winner"] == _uid("alice")  # 2:0
    assert mv(bob, g, "r").status_code >= 400
    assert "Вы победили" in page(alice)
    # кости
    alice.post("/v3/chat/bob/game", json={"kind": "dice"}, headers=J)
    g = gid_of()
    assert mv(alice, g, "roll").json()["winner"] is None
    assert mv(alice, g, "roll").status_code >= 400
    assert mv(bob, g, "roll").json()["winner"] is not None
    assert bob.post(f"/v3/game/{g}/rematch", headers=J).json()["ok"]
    # четыре в ряд: вертикаль из четырёх
    alice.post("/v3/chat/bob/game", json={"kind": "c4"}, headers=J)
    g = gid_of()
    assert mv(bob, g, 0).status_code >= 400  # не его ход
    for who, col in [(alice, 0), (bob, 1), (alice, 0), (bob, 1), (alice, 0), (bob, 1)]:
        assert mv(who, g, col).json()["winner"] is None
    assert mv(alice, g, 0).json()["winner"] == _uid("alice")
    # виселица: слово видно только загадавшему
    assert alice.post("/v3/chat/bob/game", json={"kind": "hang", "word": "x1"}, headers=J).status_code >= 400
    alice.post("/v3/chat/bob/game", json={"kind": "hang", "word": "Ёжик"}, headers=J)
    g = gid_of()
    assert mv(alice, g, "е").status_code >= 400  # загадавший не угадывает
    assert 'class="open">е<' not in page(bob)
    for ch in "ежи":
        assert mv(bob, g, ch).json()["winner"] is None
    assert mv(bob, g, "к").json()["winner"] == _uid("bob")
    assert bob.post(f"/v3/game/{g}/rematch", json={"word": "кот"}, headers=J).json()["ok"]
    # ответ на игру или стикер — понятная подпись, а не служебный код
    gm = last_msg("bob")
    alice.post("/messages/send", json={"receiver": "bob", "content": "ха", "reply_to_id": gm.id}, headers=J)
    html = bob.get("/messages/alice").text
    assert "Виселица" in html and "[[v3:hang" not in html.split('data-raw="[[v3:hang')[0].split("msg-reply")[-1]


def test_admin_tools(owner, alice, bob):
    # предупреждение и запрет публикаций на срок
    assert owner.post("/admin/u/alice/warn", data={"reason": "флуд"}, follow_redirects=False).status_code == 303
    assert "Предупреждения: <b" in owner.get("/admin/u/alice").text
    owner.post("/admin/u/alice/mute", data={"hours": "2", "reason": "спам"})
    r = alice.post("/post/create", data={"content": "привет всем"}, headers=J)
    assert r.status_code == 403 and "запрещено" in r.json()["error"]
    assert alice.post("/messages/send", json={"receiver": "bob", "content": "а чаты работают"}, headers=J).json()["ok"]
    owner.post("/admin/u/alice/unmute")
    pid = alice.post("/post/create", data={"content": "снова можно"}, headers=J).json()
    assert pid.get("ok", True)
    # только чтение — для всех, кроме владельца
    s = db()
    from packs.v3 import site
    site.put(s, "read_only", True); s.commit(); s.close()
    assert bob.post("/post/create", data={"content": "тест"}, headers=J).status_code == 403
    assert owner.post("/post/create", data={"content": "владельцу можно"}, headers=J).status_code == 200
    s = db(); site.put(s, "read_only", False); s.commit(); s.close()
    # журнал, комментарии, входы; модератору/человеку без прав — нельзя
    assert "admin_warn" in owner.get("/admin/log").text
    assert owner.get("/admin/comments").status_code == 200
    page = owner.get("/admin/logins").text
    assert "Несколько аккаунтов с одного адреса" in page and "@alice" in page
    for path in ("/admin/log", "/admin/comments", "/admin/logins"):
        assert alice.get(path, follow_redirects=False).status_code in (302, 303)


def test_feed_default_followers_and_following(owner, alice, bob):
    eve = register(make_client(), "eve")
    # bob подписан на alice; eve ни с кем не связана
    bob.post("/follow/alice", headers=J)
    bob.post("/post/create", data={"content": "пост подписчика"}, headers=J)
    eve.post("/post/create", data={"content": "пост незнакомки"}, headers=J)
    page = alice.get("/").text
    assert 'class="active">Подписки и подписчики' in page
    assert "пост подписчика" in page and "пост незнакомки" not in page
    # старое сохранённое «Рекомендации» один раз переключается
    s = db()
    a = s.query(models.User).filter_by(username="alice").one()
    a.prefs = '{"feed_default_tab": "foryou"}'
    s.commit()
    from packs.v3 import accounts
    accounts.seed_job(s)
    assert '"following"' in s.query(models.User).filter_by(username="alice").one().prefs
    s.close()


def test_gift_in_chat(alice, bob):
    s = db()
    a = s.query(models.User).filter_by(username="alice").one()
    a.total_points = 500
    s.commit(); s.close()
    gl = alice.get("/v3/gifts").json()
    assert gl["ok"] and any(g["code"] == "rose" for g in gl["gifts"])
    assert alice.post("/gifts/bob/send", data={"gift": "rose", "message": "Тебе!"}, headers=J).json()["ok"]
    m = last_msg()
    assert m.content.startswith("[[v3:gift:")
    page = bob.get("/messages/alice").text
    assert "Подарок для вас" in page and "/static/gifts/rose.svg" in page and "Тебе!" in page
    assert "Подарок" in bob.get("/messages").text  # в списке чатов — понятная подпись
    # анонимный подарок в чат не попадает
    alice.post("/gifts/bob/send", data={"gift": "heart", "anonymous": "1"}, headers=J)
    assert last_msg().id == m.id


def test_payments(owner, alice, monkeypatch):
    import config
    from packs.v3 import payments, site
    # выключено: страница открывается, купить нельзя
    assert "скоро" in alice.get("/buy").text
    assert alice.post("/buy", data={"kind": "plus", "amount": "99"}, headers=J).status_code == 400
    monkeypatch.setattr(config, "YOOKASSA_SHOP_ID", "1")
    monkeypatch.setattr(config, "YOOKASSA_SECRET", "x")
    s = db(); site.put(s, "payments_on", True); s.commit(); s.close()
    calls = []

    def fake(method, path, body=None, key=None):
        calls.append((method, path, body))
        if method == "POST":
            return {"id": f"yk-{len(calls)}", "confirmation": {"confirmation_url": "https://yoomoney.ru/pay"}}
        return {"status": "succeeded", "paid": True, "amount": {"value": calls[0][2]["amount"]["value"] if calls[0][2] else "0"}}
    monkeypatch.setattr(payments, "_call", fake)
    assert alice.post("/buy", data={"kind": "plus", "amount": "20"}, headers=J).status_code == 400  # меньше 35 ₽
    r = alice.post("/buy", data={"kind": "plus", "amount": "99"}, headers=J).json()
    assert r["url"].startswith("https://") and calls[-1][2]["amount"]["value"] == "99.00"
    # подтверждение: уведомлению не верим, статус спрашиваем сами
    alice.post("/buy/webhook", json={"object": {"id": "yk-1"}})
    s = db()
    a = s.query(models.User).filter_by(username="alice").one()
    assert a.is_plus and a.plus_until
    p = s.query(payments.m.Payment).one()
    assert p.status == "succeeded" and p.applied
    s.close()
    alice.post("/buy/webhook", json={"object": {"id": "yk-1"}})  # повторное уведомление — второй раз не начисляем
    # Искры: 400 штук = 100 ₽, уровень не растёт
    calls.clear()
    r = alice.post("/buy", data={"kind": "sparks", "sparks": "400"}, headers=J).json()
    assert calls[-1][2]["amount"]["value"] == "100.00"
    s = db()
    before = s.query(models.User).filter_by(username="alice").one()
    lvl, total = before.level, before.total_points
    pid = s.query(payments.m.Payment).order_by(payments.m.Payment.id.desc()).first().id
    s.close()
    alice.get(f"/buy/return/{pid}")
    s = db()
    a = s.query(models.User).filter_by(username="alice").one()
    from services import extras
    assert extras.balance(a) >= 400 and a.total_points == total and a.level == lvl
    s.close()


def test_communities(owner, alice, bob):
    from packs.v3 import communities as C
    s = db()
    C.seed_job(s)
    off = s.query(C.m.Community).filter_by(slug="nuvora").one()
    assert off.is_official and C._count(s, off.id) >= 3  # все подписаны на официальное сообщество
    s.close()
    new = register(make_client(), "newbie")
    s = db()
    nid = s.query(models.User).filter_by(username="newbie").one().id
    assert s.query(C.m.CommunityMember).filter_by(community_id=off.id, user_id=nid).first()
    s.close()
    # в официальном публикует только владелец
    assert alice.post("/post/create", data={"content": "я тоже хочу", "community": "nuvora"}, headers=J).status_code == 403
    assert owner.post("/post/create", data={"content": "Добро пожаловать в Nuvora 3.2!", "community": "nuvora"}, headers=J).json()["ok"]
    assert "Добро пожаловать в Nuvora 3.2" in new.get("/").text  # подписчики видят пост в ленте
    assert "Официальное сообщество" in new.get("/c/nuvora").text
    # alice создаёт канал: пишет только она; bob подписывается
    assert alice.post("/c/new", data={"name": "Котики", "slug": "nuvora", "kind": "channel"}, headers=J).status_code == 400
    r = alice.post("/c/new", data={"name": "Котики", "slug": "cats", "kind": "channel", "description": "про котов"}, headers=J).json()
    assert r["url"] == "/c/cats"
    assert bob.post("/post/create", data={"content": "чужой", "community": "cats"}, headers=J).status_code == 403
    assert bob.post("/c/cats/join", headers=J).json()["joined"]
    pid = alice.post("/post/create", data={"content": "Мурзик спит", "community": "cats"}, headers=J).json()["post_id"]
    page = bob.get("/").text
    assert "Мурзик спит" in page and "/c/cats" in page
    assert "Мурзик спит" not in alice.get("/profile/alice").text  # пост канала — не на личной странице
    # сообщество: публикуют участники
    alice.post("/c/new", data={"name": "Фото", "slug": "photo_club", "kind": "community"}, headers=J)
    assert bob.post("/post/create", data={"content": "до вступления", "community": "photo_club"}, headers=J).status_code == 403
    bob.post("/c/photo_club/join", headers=J)
    assert bob.post("/post/create", data={"content": "мой снимок", "community": "photo_club"}, headers=J).json()["ok"]
    assert "мой снимок" in make_client().get("/c/photo_club").text  # открыто и без входа
    # админ, удаление; официальное удалить нельзя
    assert alice.post("/c/cats/admin-add", data={"username": "bob"}, headers=J).json()["ok"]
    assert bob.post("/post/create", data={"content": "я теперь админ", "community": "cats"}, headers=J).json()["ok"]
    assert owner.post("/c/nuvora/delete", headers=J).status_code >= 400
    assert "Котики" in bob.get("/c").text
    assert alice.post("/c/cats/delete", headers=J).json()["ok"]
    assert bob.get(f"/post/{pid}").status_code in (200, 404)


def test_wall_posts(alice, bob):
    eve = register(make_client(), "eve")
    # по умолчанию — только друзья (взаимная подписка)
    assert bob.post("/post/create", data={"content": "привет на стене", "wall": "alice"}, headers=J).status_code == 403
    alice.post("/follow/bob", headers=J); bob.post("/follow/alice", headers=J)
    assert "Написать на стене" in bob.get("/profile/alice").text
    pid = bob.post("/post/create", data={"content": "привет на стене", "wall": "alice"}, headers=J).json()["post_id"]
    prof = alice.get("/profile/alice").text
    assert "привет на стене" in prof and "на стене у" in prof
    assert "привет на стене" not in bob.get("/profile/bob").text  # у автора на странице её нет
    assert eve.post("/post/create", data={"content": "я чужая", "wall": "alice"}, headers=J).status_code == 403
    # владелица стены может удалить чужую запись у себя
    assert alice.post(f"/post/{pid}/delete", headers=J).json()["ok"]
    # «Никто»
    alice.post("/settings/prefs/privacy", data={"who_can_post_wall": "nobody"})
    assert bob.post("/post/create", data={"content": "ещё", "wall": "alice"}, headers=J).status_code == 403


def test_albums_and_tags(alice, bob):
    eve = register(make_client(), "eve")
    r = alice.post("/albums/new", data={"title": "Лето", "privacy": "all"}, headers=J).json()
    aid = int(r["url"].rsplit("/", 1)[1])
    up = alice.post(f"/albums/{aid}/upload", files=[("photos", ("a.png", png_bytes(), "image/png")), ("photos", ("b.png", png_bytes((10, 200, 30)), "image/png"))], headers=J).json()
    assert up["added"] == 2
    assert bob.post(f"/albums/{aid}/upload", files=[("photos", ("c.png", png_bytes(), "image/png"))], headers=J).status_code == 403
    page = bob.get(f"/albums/{aid}").text
    assert "2 фото" in page
    from packs.v3.models import Photo
    s = db()
    photo_id = s.query(Photo).order_by(Photo.id).first().id
    s.close()
    # отметить можно только того, с кем есть подписка
    assert alice.post(f"/photos/{photo_id}/tag", data={"username": "bob", "x": 30, "y": 40}, headers=J).status_code == 400
    bob.post("/follow/alice", headers=J)
    assert alice.post(f"/photos/{photo_id}/tag", data={"username": "bob", "x": 30, "y": 40}, headers=J).json()["ok"]
    assert "Фото со мной" in bob.get("/profile/bob/photos").text
    assert "Bob" in alice.get(f"/photos/{photo_id}").text
    # отмеченный убирает отметку сам
    assert bob.post(f"/photos/{photo_id}/untag", headers=J).json()["ok"]
    # приватность альбома
    r2 = alice.post("/albums/new", data={"title": "Личное", "privacy": "me"}, headers=J).json()
    assert bob.get(r2["url"]).status_code == 404 and "Личное" not in eve.get("/profile/alice/photos").text
    assert alice.post(f"/albums/{aid}/delete", headers=J).json()["ok"]


def test_recommendations_people_signals(alice, bob):
    from services import recommend
    carol, dan, eve = (register(make_client(), n) for n in ("carol", "dan", "eve"))
    post = lambda c, t: c.post("/post/create", data={"content": t}, headers=J).json()["post_id"]
    x1, x2 = post(dan, "Закат над морем"), post(dan, "Рассвет в горах")
    y = post(eve, "Редкая птица в парке")
    z = post(eve, "Обычный пост про погоду")
    for c in (bob, carol):
        c.post(f"/like/{x1}", headers=J); c.post(f"/like/{x2}", headers=J); c.post(f"/like/{y}", headers=J)
    alice.post(f"/like/{x1}", headers=J); alice.post(f"/like/{x2}", headers=J)
    s = db()
    a = s.query(models.User).filter_by(username="alice").one()
    recommend.invalidate(a.id)
    cf = recommend.similar_taste(s, a)
    assert cf.get(y, 0) > 0 and z not in cf  # «похожие вкусы»: bob и carol лайкают то же, что alice, и ещё «птицу»
    pool = s.query(models.Post).filter(models.Post.id.in_([y, z])).all()
    ranked = [p.id for p, _, _ in recommend.rank(s, a, pool, set())]
    assert ranked.index(y) < ranked.index(z)
    s.close()
    # близость: alice переписывается с eve
    for i in range(5):
        alice.post("/messages/send", json={"receiver": "eve", "content": f"привет {i}"}, headers=J)
    s = db()
    a = s.query(models.User).filter_by(username="alice").one()
    e = s.query(models.User).filter_by(username="eve").one()
    recommend._cache.pop(("aff", a.id), None)
    assert recommend.social_affinity(s, a).get(e.id, 0) > 0
    s.close()


def test_share_trace(alice, bob):
    from services import recommend
    pid = alice.post("/post/create", data={"content": "Мой пост для друзей"}, headers=J).json()["post_id"]
    menu = alice.get(f"/post/{pid}/menu").text
    assert "from%3Dalice" in menu  # ссылки «поделиться» несут логин
    # вошедший человек видит, кто поделился, и предложение добавить в друзья
    page = bob.get(f"/post/{pid}?from=alice").text
    assert "поделился(ась) с вами" in page and 'data-share-follow="alice"' in page
    s = db()
    b = s.query(models.User).filter_by(username="bob").one()
    a = s.query(models.User).filter_by(username="alice").one()
    assert recommend.social_affinity(s, b).get(a.id, 0) > 0  # её посты ближе в рекомендациях
    s.close()
    # без аккаунта: запоминаем, кто позвал; после регистрации — награда и предложение в друзья
    guest = make_client()
    assert "Присоединиться" in guest.get(f"/post/{pid}?from=alice").text
    register(guest, "newcomer")
    home = guest.get("/").text
    assert "позвал(а) вас" in home
    s = db()
    n = s.query(models.User).filter_by(username="newcomer").one()
    assert n.referred_by == a.id
    s.close()
    assert bob.get(f"/post/{pid}?from=nobody_here").status_code == 200


def test_nuva_gigachat(alice, monkeypatch):
    import config
    from packs.v3 import gigachat
    # без ключа — ответ по справке
    r = alice.post("/ai/chat", json={"question": "Как получить искры?"}, headers=J).json()
    assert r["ok"] and not r.get("ai")
    monkeypatch.setattr(config, "GIGACHAT_AUTH_KEY", "test-key")
    sent = []

    def fake(messages, max_tokens=700, temperature=0.7):
        sent.append(messages)
        return "Искры дают за посты и задания дня. А ещё их можно потратить на подарки 🎁"
    monkeypatch.setattr(gigachat, "_post", fake)
    r = alice.post("/ai/chat", json={"question": "Как получить искры?", "history": '[{"role":"user","content":"привет"},{"role":"bot","content":"Привет!"}]'}, headers=J).json()
    assert r["ai"] and "Искры" in r["text"]
    msgs = sent[-1]
    assert msgs[0]["role"] == "system" and "Справка Nuvora" in msgs[0]["content"] and "Как получить искры" in msgs[0]["content"]
    assert [m_["role"] for m_ in msgs[1:]] == ["user", "assistant", "user"]
    # сбой сервиса — снова справка, без ошибки
    monkeypatch.setattr(gigachat, "_post", lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
    r = alice.post("/ai/chat", json={"question": "Как получить искры?"}, headers=J).json()
    assert r["ok"] and not r.get("ai")


def test_growth(alice):
    from packs.v3 import growth
    from datetime import datetime, timedelta
    # приглашение: сразу немного, остальное — когда друг освоится
    guest = make_client()
    guest.get("/invite/alice")
    register(guest, "friend1")
    s = db()
    a = s.query(models.User).filter_by(username="alice").one()
    f = s.query(models.User).filter_by(username="friend1").one()
    before = a.total_points
    assert f.referred_by == a.id and not f.referral_done
    growth.referral_job(s)
    assert not s.get(models.User, f.id).referral_done  # ещё не освоился
    f.created_at = datetime.utcnow() - timedelta(days=2)
    s.add(models.Post(user_id=f.id, content="мой первый пост"))
    s.commit()
    growth.referral_job(s)
    a = s.get(models.User, a.id)
    assert s.get(models.User, f.id).referral_done and a.total_points >= before + growth.INVITE_LATER
    s.close()
    assert "засчитан" in alice.get("/invite").text
    # карта сайта, robots, превью
    pid = alice.post("/post/create", data={"content": "Открытый пост для всех"}, headers=J).json()["post_id"]
    anon = make_client()
    sm = anon.get("/sitemap.xml").text
    assert f"/post/{pid}" in sm and "/profile/alice" in sm
    assert "Sitemap:" in anon.get("/robots.txt").text
    page = anon.get(f"/post/{pid}").text
    assert f"/og/post/{pid}.png" in page and "Присоединиться" in page
    img = anon.get(f"/og/post/{pid}.png")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png" and len(img.content) > 5000
    assert anon.get("/og/profile/alice.png").status_code == 200


def test_chat_pages_older(alice, bob):
    import re
    from services import ratelimit
    for i in range(62):
        ratelimit.reset()
        assert alice.post("/messages/send", json={"receiver": "bob", "content": f"сообщение {i}"}, headers=J).json()["ok"]
    page = alice.get("/messages/bob").text
    ids = [int(x) for x in re.findall(r'id="msg-(\d+)"', page)]
    assert len(ids) == 50 and "hasOlder=true" in page and "сообщение 61" in page
    r = alice.get(f"/messages/older/bob?before={min(ids)}").json()
    assert r["ok"] and not r["more"] and r["html"].count('id="msg-') == 12 and "сообщение 0<" in r["html"].replace("\n", "")
    assert bob.get(f"/messages/older/alice?before={min(ids)}").json()["ok"]
    carol = make_client()
    register(carol, "carol")
    assert carol.get(f"/messages/older/bob?before={min(ids)}").status_code == 404
    # непрочитанные видны все, даже если их больше страницы
    assert len(re.findall(r'id="msg-\d+"', bob.get("/messages/alice").text)) == 62


def test_gift_certificates(owner, alice):
    page = owner.get("/admin/certificates")
    assert page.status_code == 200 and "Новый сертификат" in page.text
    assert alice.get("/admin/certificates", follow_redirects=False).status_code in (302, 303)
    r = owner.post("/admin/certificates/new", data={"days": "35", "recipient": "Ивана"}, follow_redirects=False)
    assert r.status_code in (302, 303)
    pid = int(r.headers["location"].split("made=")[1])
    s = db()
    p = s.get(models.Promocode, pid)
    assert p.days == 35 and p.max_uses == 1 and p.note == "Ивана" and len(p.code) == 8
    png = owner.get(f"/admin/certificates/{pid}.png")
    assert png.status_code == 200 and png.content[:4] == b"\x89PNG"
    assert alice.get(f"/admin/certificates/{pid}.png").status_code == 404
    assert p.code in owner.get(f"/plus?code={p.code}").text  # QR ведёт на страницу с уже вписанным кодом
    s.close()


def test_co_owner(owner, alice):
    r = owner.post("/admin/u/alice/coowner", follow_redirects=False)
    assert r.status_code in (302, 303)
    s = db()
    a = s.query(models.User).filter_by(username="alice").one()
    assert a.is_owner and a.co_owner
    from services.social import main_owner
    assert main_owner(s).username == "owner"  # «лицо» сайта не меняется
    s.close()
    assert "Совладелец" in owner.get("/profile/alice").text and "Основатель" in owner.get("/profile/owner").text
    assert alice.get("/admin/certificates").status_code == 200  # полный доступ
    # совладелец не может снять основателя и назначать других
    alice.post("/admin/u/owner/coowner")
    s = db(); assert not s.query(models.User).filter_by(username="owner").one().co_owner; s.close()
    owner.post("/admin/u/alice/coowner")
    s = db(); a = s.query(models.User).filter_by(username="alice").one(); assert not a.is_owner and not a.co_owner; s.close()


def test_gift_drops(owner, alice, bob):
    s = db()
    a = s.query(models.User).filter_by(username="alice").one()
    a.total_points = 5000
    s.commit()
    s.close()
    # лимитированный не виден и не дарится, пока владелец не выпустил
    assert "snowglobe" not in alice.get("/gifts/bob").text
    assert alice.post("/gifts/bob/send", data={"gift": "snowglobe"}, headers=J).json()["ok"] is False
    assert alice.get("/admin/gifts", follow_redirects=False).status_code in (302, 303)
    assert "Ещё не выпущен" in owner.get("/admin/gifts").text
    owner.post("/admin/gifts/snowglobe", data={"supply": "1", "announce": "1"})
    assert "snowglobe" in alice.get("/gifts/bob").text
    assert alice.post("/gifts/bob/send", data={"gift": "snowglobe"}, headers=J).json()["ok"]
    assert "№1" in bob.get("/gifts/bob").text
    r = alice.post("/gifts/bob/send", data={"gift": "snowglobe"}, headers=J).json()
    assert r["ok"] is False and "Распродан" in r["error"]
    owner.post("/admin/gifts/snowglobe", data={"action": "stop"})
    assert "Снят с продажи" in owner.get("/admin/gifts").text
    # коллекция всегда в продаже
    assert alice.post("/gifts/bob/send", data={"gift": "castle"}, headers=J).json()["ok"]
    # подарок от создателя — только у основателя, не у совладельца и не у обычных людей
    assert alice.post("/gifts/bob/send", data={"gift": "founder"}, headers=J).json()["ok"] is False
    assert "founder" not in alice.get("/gifts/bob").text
    assert owner.post("/gifts/bob/send", data={"gift": "founder"}, headers=J).json()["ok"]
    assert "от создателя" in bob.get("/gifts/bob").text


def test_places(alice, tmp_path, monkeypatch):
    import zipfile
    from services import places
    from tools import build_places
    row = lambda gid, name, alts, cc, a1, pop, code="PPL": "\t".join([str(gid), name, name, alts, "0", "0", "P", code, cc, "", a1, "", "", "", str(pop)] + [""] * 4)
    with zipfile.ZipFile(tmp_path / "allCountries.zip", "w") as z:
        z.writestr("allCountries.txt", "\n".join([row(1, "Perm", "Пермь,Perm", "RU", "90", 1000000), row(2, "Orlovo", "Орлово", "RU", "90", 0),
                                                  row(3, "Minsk", "", "BY", "5", 2000000), row(4, "Perm District", "", "RU", "90", 5, "PPLX")]))
    with zipfile.ZipFile(tmp_path / "alternateNamesV2.zip", "w") as z:
        z.writestr("alternateNamesV2.txt", "1\t3\tru\tМинск\t1\t\t\t\t\t\n2\t20\tru\tПермский край\t\t\t\t\t\t\n3\t30\tru\tБеларусь\t\t\t\t\t\t\n")
    (tmp_path / "admin1.txt").write_text("RU.90\tPerm Krai\tPerm Krai\t20\nBY.5\tMinsk City\tMinsk City\t21\n")
    (tmp_path / "country.txt").write_text("\t".join(["BY", "BLR", "112", "BO", "Belarus"] + [""] * 11 + ["30"]) + "\n")
    out = str(tmp_path / "places.sqlite")
    assert build_places.build(str(tmp_path / "allCountries.zip"), str(tmp_path / "alternateNamesV2.zip"), str(tmp_path / "admin1.txt"),
                              str(tmp_path / "country.txt"), out) == 2  # район города и другие страны не попадают
    monkeypatch.setattr(places, "PLACES_DB", out)
    assert places.search("перм") == ["Пермь, Пермский край"] and places.search("perm") == ["Пермь, Пермский край"]
    assert places.search("Минс") == [] and places.search("орлово") == ["Орлово, Пермский край"]
    assert alice.get("/api/places?q=пер").json()["items"] == ["Пермь, Пермский край"]
    alice.post("/settings/profile", data={"name": "Алиса", "city": "С. Перма"})
    assert "С. Перма" not in alice.get("/settings?section=profile").text  # своё написание не сохраняется
    alice.post("/settings/profile", data={"name": "Алиса", "city": "Орлово, Пермский край"})
    assert "Орлово, Пермский край" in alice.get("/profile/alice").text


def test_short_links(alice, monkeypatch):
    import config
    import main
    monkeypatch.setattr(config, "SHORT_DOMAIN", "nvurl.ru")
    hit = lambda p: alice.get(p, headers={"host": "nvurl.ru"}, follow_redirects=False)
    assert hit("/123?from=bob").headers["location"] == config.SITE_URL + "/post/123?from=bob"
    assert hit("/@rubl").headers["location"] == config.SITE_URL + "/profile/rubl"
    assert hit("/gifts/rubl").headers["location"] == config.SITE_URL + "/gifts/rubl"
    assert alice.get("/settings", follow_redirects=False).status_code == 200  # основной домен работает как раньше
    assert main.short_target("/") == config.SITE_URL + "/"
