"""Истории (7.11.2026): оформление, ссылка, опрос, отметки, архив, «поделиться снова», пост в историю; скрытые лайки у поста; админка."""
import models
from database import SessionLocal
from tests.conftest import make_client, png_bytes, register
from tests.test_app import J, create_post


def _story(username):
    s = SessionLocal()
    u = s.query(models.User).filter_by(username=username).first()
    st = s.query(models.Story).filter_by(user_id=u.id).order_by(models.Story.id.desc()).first()
    s.close()
    return st


def test_story_style_link_poll_mention():
    alice = register(make_client(), "alice")
    bob = register(make_client(), "bob")
    bob.post("/follow/alice", headers=J)
    r = alice.post("/stories/create", data={"text_overlay": "Привет, @bob!", "bg_color": "#334155", "tcolor": "#f0c24a", "font": "unb", "tsize": "l",
                                            "tpos": "top", "plate": "1", "link_url": "nvurl.ru/5", "link_label": "Смотри", "poll_q": "Кино?",
                                            "poll_a": "Да", "poll_b": "Нет", "duration": "6"}, follow_redirects=False)
    assert r.status_code == 303
    st = _story("alice")
    assert '"poll"' in st.extra and '"https://nvurl.ru/5"' in st.extra and (st.expires_at - st.created_at).total_seconds() < 7 * 3600
    page = bob.get("/stories/alice").text
    assert "story-poll" in page and "Смотри" in page and "p-top" in page and 'href="/profile/bob"' in page
    r = bob.post(f"/stories/{st.id}/vote", json={"choice": 1}, headers=J).json()
    assert r["b"] == 1 and r["mine"] == 1
    assert bob.post(f"/stories/{st.id}/vote", json={"choice": 0}, headers=J).json()["a"] == 0  # голос один
    s = SessionLocal()
    b = s.query(models.User).filter_by(username="bob").first()
    assert s.query(models.Notification).filter_by(user_id=b.id, type="story_mention").count() == 1
    s.close()
    # плохая ссылка не сохраняется
    alice.post("/stories/create", data={"text_overlay": "x", "link_url": "javascript:alert(1)"})
    assert '"link"' not in (_story("alice").extra or "")


def test_story_archive_again_and_post_to_story():
    alice = register(make_client(), "alice")
    bob = register(make_client(), "bob")
    alice.post("/stories/create", data={"text_overlay": "первая"})
    st = _story("alice")
    assert "первая" in alice.get("/stories/archive").text
    assert bob.post(f"/stories/{st.id}/again", headers=J).status_code == 403
    assert alice.post(f"/stories/{st.id}/again", headers=J).json()["ok"]
    assert _story("alice").id != st.id
    pid = create_post(bob, "пост боба для истории", files=[("media", ("a.png", png_bytes(), "image/png"))])
    r = alice.post(f"/post/{pid}/to-story", headers=J).json()
    assert r["ok"]
    sh = _story("alice")
    assert f'"/post/{pid}"' in sh.extra and "@bob" in sh.text_overlay and sh.media_url
    # удаление истории не стирает фото поста
    alice.post(f"/stories/{sh.id}/delete", headers=J)
    import os, config
    assert os.path.exists(os.path.join(config.UPLOAD_DIR, os.path.basename(sh.media_url)))


def test_post_hide_likes():
    alice = register(make_client(), "alice")
    bob = register(make_client(), "bob")
    pid = create_post(alice, "скрытые лайки", hide_likes="1")
    bob.post(f"/like/{pid}", headers=J)
    assert "Кому понравилось" not in bob.get(f"/post/{pid}").text
    assert "Кому понравилось" in alice.get(f"/post/{pid}").text


def test_admin_stories_and_reset_actions():
    owner = register(make_client(), "zara")
    eve = register(make_client(), "eve")
    s = SessionLocal()
    s.query(models.User).filter_by(username="zara").first().is_owner = True
    e = s.query(models.User).filter_by(username="eve").first()
    e.bio = "плохое описание"
    s.commit()
    s.close()
    eve.post("/stories/create", data={"text_overlay": "история евы"})
    assert "история евы" in owner.get("/admin/stories").text
    assert "Сейчас в сети" in owner.get("/admin").text
    owner.post("/admin/u/eve/reset-bio")
    s = SessionLocal()
    assert s.query(models.User).filter_by(username="eve").first().bio == ""
    s.close()
    assert eve.get("/admin/stories", follow_redirects=False).status_code in (302, 303)
