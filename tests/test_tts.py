"""Встроенная озвучка (7.11.2026): голос сервера для «Прослушать», выбор голоса, студия записи своего голоса."""
import math
import os
import struct

import pytest

import models
from database import SessionLocal
from services import tts
from tests.conftest import make_client, register
from tests.test_app import J, create_post


class FakeVoice:
    def synthesize_wav(self, text, w):
        w.setframerate(16000); w.setsampwidth(2); w.setnchannels(1)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 8))) for i in range(1600)))


@pytest.fixture
def voice(tmp_path, monkeypatch):
    vdir = tmp_path / "voices"
    vdir.mkdir()
    for name, lic in (("ru_RU-irina-medium", "MIT"), ("ru_RU-ruslan-medium", "CC BY-NC-SA 4.0")):
        (vdir / f"{name}.onnx").write_bytes(b"x")
        (vdir / f"{name}.onnx.json").write_text("{}")
        (vdir / f"{name}.MODEL_CARD").write_text(f"# Model card\n\n* License: {lic}\n")
    monkeypatch.setattr(tts, "VOICES", str(vdir))
    monkeypatch.setattr(tts, "CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(tts, "_voice", lambda vid: FakeVoice())
    from packs.v3 import tts as ptts
    monkeypatch.setattr(ptts, "STUDIO", str(tmp_path / "studio"))
    return vdir


def test_clean_text():
    assert tts.clean("Привет **мир** #тег https://x.ru 🐋 @bob") == "Привет мир тег ссылка bob"


def test_post_tts(voice):
    alice = register(make_client(), "alice")
    pid = create_post(alice, "Привет! Это проверка озвучки.")
    assert tts.current() == "ru_RU-irina-medium" and tts.noncommercial("ru_RU-ruslan-medium")
    page = alice.get(f"/post/{pid}").text
    assert f'data-tts-url="/tts/post/{pid}"' in page
    r = alice.get(f"/tts/post/{pid}")
    assert r.status_code == 200 and r.headers["content-type"].startswith("audio/") and len(r.content) > 1000
    assert make_client().get(f"/tts/post/{pid}").status_code == 401


def test_admin_tts_and_studio(voice):
    owner = register(make_client(), "zara")
    s = SessionLocal()
    s.query(models.User).filter_by(username="zara").first().is_owner = True
    s.commit()
    s.close()
    page = owner.get("/admin/tts").text
    assert "Ирина" in page and "некоммерческих" in page and "Свой голос" in page
    owner.post("/admin/tts", data={"voice": "ru_RU-ruslan-medium", "on": "1"})
    assert tts.current() == "ru_RU-ruslan-medium"
    assert owner.get("/admin/tts/sample/ru_RU-irina-medium").headers["content-type"].startswith("audio/")
    assert "Фраза" in owner.get("/admin/voice").text
    r = owner.post("/admin/voice/rec/0", files={"audio": ("rec", b"\x1a\x45\xdf\xa3" + b"0" * 3000, "audio/webm")}, headers=J).json()
    assert r["ok"] and r["done"] == 1
    assert owner.get("/admin/voice/rec/0").status_code == 200
    z = owner.get("/admin/voice/dataset.zip")
    assert z.status_code == 200 and z.content[:2] == b"PK"
    eve = register(make_client(), "eve")
    assert eve.post("/admin/voice/rec/1", files={"audio": ("rec", b"0" * 3000, "audio/webm")}, headers=J).status_code == 403
    owner.post("/admin/tts", data={"voice": "ru_RU-irina-medium"})  # выключить
    assert not tts.enabled()


def test_voice_api_for_colab(voice, monkeypatch):
    import config
    monkeypatch.setattr(config, "NUVA_UPLOAD_CODE", "k" * 24)
    owner = register(make_client(), "zara")
    s = SessionLocal()
    s.query(models.User).filter_by(username="zara").first().is_owner = True
    s.commit()
    s.close()
    owner.post("/admin/voice/rec/3", files={"audio": ("rec", b"\x1a\x45\xdf\xa3" + b"0" * 3000, "audio/webm")}, headers=J)
    c = make_client()
    assert c.get("/api/voice/dataset", headers={"x-upload-code": "wrong"}).status_code == 403
    z = c.get("/api/voice/dataset", headers={"x-upload-code": "k" * 24})
    assert z.status_code == 200 and z.content[:2] == b"PK"
    H = {"x-upload-code": "k" * 24}
    assert c.post("/api/voice-model/upload?kind=json", content=b'{"audio": {"sample_rate": 22050}}', headers=H).json()["ok"]
    assert c.post("/api/voice-model/upload?kind=onnx&part=0&total=2", content=b"\x08\x07" + b"m" * 100, headers=H).json()["done"] is False
    r = c.post("/api/voice-model/upload?kind=onnx&part=1&total=2", content=b"m" * 100, headers=H).json()
    assert r["done"] and os.path.exists(os.path.join(tts.VOICES, "nuvora-custom.onnx"))
    assert tts.current() == "nuvora-custom"
    assert c.post("/api/voice-model/upload?kind=onnx&part=0&total=1", content=b"<html>", headers=H).status_code == 400
