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
    assert "Не показывать 30 дней" in bob.get(f"/post/{pid}").text
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
    assert r["reward"] == 5 and r["streak"] == 1
    assert alice.post("/v3/chest", headers=J).status_code == 400
    assert "data-v3-chest" not in alice.get("/").text
    s = db()
    row = s.query(m.DailyChest).one()
    row.last_day = (datetime.strptime(row.last_day, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    s.commit()
    s.close()
    assert alice.post("/v3/chest", headers=J).json() == {"ok": True, "reward": 10, "streak": 2}


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
    form = {"email": "x@example.com", "password": "secret123", "confirm_password": "secret123", "agree": "1", "consent": "1", "adult": "1", "name": "X"}
    r = c.post("/register", data={**form, "username": "Love"}, follow_redirects=False)
    assert r.status_code != 303 and "зарезервирован" in r.text
    r = c.post("/register", data={**form, "username": "fox"}, follow_redirects=False)
    assert r.status_code != 303 and "баллов" in r.text
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
