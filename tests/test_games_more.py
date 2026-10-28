"""Морской бой в переписке и раздел «Игры без интернета»."""
import json
import os
import shutil
import subprocess

import pytest

from database import SessionLocal
from packs.v3 import chat_games, models as m
from tests.conftest import ROOT, make_client
from tests.test_app import J
from tests.test_pack_v3 import _uid, last_msg


def _game(gid):
    s = SessionLocal()
    try:
        g = s.get(m.ChatGame, int(gid))
        return g, json.loads(g.state)
    finally:
        s.close()


def _view(gid, username):
    import models
    s = SessionLocal()
    try:
        g = s.get(m.ChatGame, int(gid))
        return chat_games.view(s, g, s.query(models.User).filter_by(username=username).first())
    finally:
        s.close()


def test_sea_battle(alice, bob):
    mv = lambda c, gid, v: c.post(f"/v3/game/{gid}/move", json={"v": str(v)}, headers=J)
    assert alice.post("/v3/chat/bob/game", json={"kind": "sea"}, headers=J).json()["ok"]
    gid = last_msg().content[5:-2].split(":")[1]
    g, st = _game(gid)
    assert g.turn == _uid("alice") and g.winner is None
    ships_b = [x for ship in st["ships"]["b"] for x in ship]
    ships_a = [x for ship in st["ships"]["a"] for x in ship]
    assert len(ships_a) == len(ships_b) == sum(chat_games.SEA_FLEET)
    # координаты кораблей соперника не уходят клиенту: ни в данных карточки, ни в HTML
    v = _view(gid, "alice")
    assert "o" not in v["enemy"] and v["mine"].count("o") == len(ships_a)
    html = alice.get(f"/messages/fragment/{last_msg().id}").json()["html"]
    assert "Морской бой" in html and html.count('class="o') == len(ships_a)  # видны только свои корабли
    assert bob.get(f"/messages/fragment/{last_msg().id}").json()["html"].count('class="o') == len(ships_b)
    # не свой ход
    assert mv(bob, gid, ships_a[0]).status_code >= 400
    # промах — ход переходит
    miss = next(i for i in range(64) if i not in ships_b)
    r = mv(alice, gid, miss).json()
    assert r["ok"] and r["hit"] is False and _game(gid)[0].turn == _uid("bob")
    assert mv(alice, gid, ships_b[0]).status_code >= 400  # уже не её ход
    # попадание — тот же игрок стреляет ещё
    r = mv(bob, gid, ships_a[0]).json()
    assert r["hit"] is True and _game(gid)[0].turn == _uid("bob")
    assert mv(bob, gid, ships_a[0]).status_code >= 400  # в ту же клетку второй раз нельзя
    assert "o" not in _view(gid, "bob")["enemy"] and "h" in _view(gid, "bob")["enemy"]
    bob_miss = next(i for i in range(64) if i not in ships_a)
    assert mv(bob, gid, bob_miss).json()["hit"] is False
    # Алиса топит весь флот подряд (каждое попадание — ещё ход) и побеждает
    for i, x in enumerate(ships_b):
        r = mv(alice, gid, x).json()
        assert r["ok"] and r["hit"]
        assert r["winner"] == (_uid("alice") if i == len(ships_b) - 1 else None)
    assert mv(bob, gid, bob_miss + 1 if bob_miss + 1 not in ships_a else 63).status_code >= 400  # игра окончена
    v = _view(gid, "bob")
    assert v["done"] and v["enemy"].count("o") == len(ships_a) - 1  # после конца видны и чужие корабли
    assert "Вы победили" in alice.get(f"/messages/fragment/{last_msg().id}").json()["html"]
    assert bob.post(f"/v3/game/{gid}/rematch", headers=J).json()["ok"]
    assert _game(last_msg("bob").content[5:-2].split(":")[1])[0].turn == _uid("bob")


def test_sea_fleet_rules():
    for _ in range(300):
        ships = chat_games.sea_fleet()
        assert sorted(len(s) for s in ships) == sorted(chat_games.SEA_FLEET)
        for i, a in enumerate(ships):
            for b in ships[i + 1:]:
                assert not chat_games._halo(a) & set(b)  # не касаются даже углами


def test_offline_games_page(alice, anon):
    r = alice.get("/games/offline")
    assert r.status_code == 200 and "Игры без интернета" in r.text and "offline/core.js" in r.text
    assert 'href="/games/offline"' in alice.get("/games").text
    assert anon.get("/games/offline").status_code == 200  # без входа тоже: играть можно и без аккаунта
    sw = anon.get("/sw.js").text
    assert "/games/offline" in sw and "offline/core.js" in sw and "__OFFLINE__" not in sw
    for url in json.loads(sw.split("const OFFLINE = ", 1)[1].split(";\n", 1)[0]):
        assert anon.get(url).status_code == 200, url  # всё, что сервис-воркер кладёт в кэш, существует
    assert make_client().get("/i18n/en/static/packs/v3/offline/core.js").status_code == 200


@pytest.mark.skipif(not shutil.which("node"), reason="нужен node")
def test_offline_bots_node():
    """Логика игр и ботов на чистом JS: крестики-нолики 3×3 непобедимы, генератор судоку даёт одно решение и т. д."""
    r = subprocess.run(["node", os.path.join(ROOT, "tests", "offline_games_check.js")], capture_output=True, text=True, timeout=240)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
