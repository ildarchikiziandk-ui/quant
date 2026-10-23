"""Особые правила для аккаунтов.

1. Все подписаны на владельца по умолчанию: новый аккаунт сразу подписывается, а существующие
   подписываются один раз (фоновая задача). Отписаться потом можно, как от любого человека.
2. Аккаунты «только чаты и профиль»: человек не публикует посты и не видит чужие посты
   (лента, поиск, хэштеги, чужие профили) — остаются переписка, свой профиль, игры, Нува и остальное.
   Включается в админ-панели в карточке пользователя; для @svetlana — сразу.
"""
from . import site

PRESET_LOCKED = ("svetlana",)  # для этих логинов режим включается сам, как только аккаунт появится


def follow_owner(db, user):
    """Подписать человека на владельца (без уведомления — владельцу не нужен поток «на вас подписались»)."""
    import models
    owner = db.query(models.User).filter_by(is_owner=True).first()
    if not owner or not user or owner.id == user.id:
        return
    if not db.query(models.Follow.id).filter_by(follower_id=user.id, following_id=owner.id).first():
        db.add(models.Follow(follower_id=user.id, following_id=owner.id))
        db.commit()


def posts_locked(user):
    if not user:
        return False
    if user.id in set(site.get("posts_locked") or ()):
        return True
    return not site.get("locks_seeded") and (user.username or "").lower() in PRESET_LOCKED


def set_locked(db, user, on):
    ids = set(site.get("posts_locked") or ())
    ids = ids | {user.id} if on else ids - {user.id}
    site.put(db, "posts_locked", sorted(ids))


def seed_job(db):
    """Раз в минуту: один раз подписать всех на владельца; включить режим «только чаты» для заданных логинов."""
    import models
    if not site.get("owner_follow_seeded"):
        owner = db.query(models.User).filter_by(is_owner=True).first()
        if owner:
            have = {f for (f,) in db.query(models.Follow.follower_id).filter_by(following_id=owner.id)}
            new = [u for (u,) in db.query(models.User.id).filter(models.User.id != owner.id) if u not in have]
            db.bulk_save_objects([models.Follow(follower_id=u, following_id=owner.id) for u in new])
            site.put(db, "owner_follow_seeded", True)
            db.commit()
    if not site.get("locks_seeded"):
        from sqlalchemy import func
        found = db.query(models.User).filter(func.lower(models.User.username).in_(PRESET_LOCKED)).all()
        for u in found:
            set_locked(db, u, True)
        if len(found) == len(PRESET_LOCKED):  # все нашлись — дальше управляется только из админки
            site.put(db, "locks_seeded", True)
        db.commit()
