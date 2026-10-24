import io
import os
import sys
import tempfile

import pytest

_tmp = tempfile.mkdtemp(prefix="app-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["UPLOAD_DIR"] = os.path.join(_tmp, "uploads")
os.environ["SECRET_KEY"] = "test-secret"
os.environ["OWNER_USERNAME"] = "owner"
os.environ.setdefault("VAPID_AUTO", "0")
os.environ.setdefault("SMTP_USER", "")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from services import ratelimit  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_state():
    import migrations
    from database import Base, SessionLocal, engine
    ratelimit.reset()
    from packs.v3 import site
    site._cache.update(t=0, v=dict(site.DEFAULTS))  # настройки сайта из прошлого теста не переносятся
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    migrations.seed(s)
    s.close()
    yield


def make_client():
    return TestClient(main.app, base_url="http://testserver")


def register(client, username, password="secret123", private=False):
    r = client.post("/register", data={"username": username, "email": f"{username}@example.com", "password": password,
                                       "confirm_password": password, "agree": "1", "consent": "1", "adult": "1", "name": username.title()},
                    follow_redirects=False)
    assert r.status_code == 303, r.text[:500]
    if private:
        client.post("/settings/privacy", data={"is_private": "on", "who_can_message": "all", "who_can_see_stories": "all"})
    return client


def png_bytes(color=(124, 58, 237)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), color).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def owner():
    return register(make_client(), "owner")


@pytest.fixture
def alice():
    return register(make_client(), "alice")


@pytest.fixture
def bob():
    return register(make_client(), "bob")


@pytest.fixture
def anon():
    return make_client()
