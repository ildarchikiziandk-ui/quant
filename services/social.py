"""Социальные правила: блокировки, скрытые пользователи, приватные аккаунты, видимость постов,
уведомления (с учётом настроек и push) и упоминания."""
from datetime import datetime

from sqlalchemy import and_, or_

import config
import models
from services import push
from services.text import extract_mentions

NOTIFY_PREF = {"like": "notify_likes", "whale": "notify_likes", "reaction": "notify_likes", "comment_like": "notify_likes",
               "comment": "notify_comments", "reply": "notify_comments", "follow": "notify_follows",
               "follow_request": "notify_follows", "follow_accept": "notify_follows", "mention": "notify_mentions",
               "repost": "notify_likes"}

NOTIFY_TEXT = {"like": "оценил(а) ваш пост", "whale": "отправил(а) кита вашему посту", "comment": "прокомментировал(а) ваш пост",
               "reply": "ответил(а) на ваш комментарий", "follow": "подписался(лась) на вас", "mention": "упомянул(а) вас",
               "follow_request": "хочет подписаться на вас", "follow_accept": "принял(а) вашу заявку", "repost": "репостнул(а) ваш пост",
               "reaction": "отреагировал(а) на ваш пост", "comment_like": "оценил(а) ваш комментарий",
               "group_invite": "добавил(а) вас в группу", "story_reaction": "отреагировал(а) на вашу историю"}


def is_active_block(user):
    if not user or not user.is_blocked:
        return False
    if user.blocked_until and datetime.utcnow() > user.blocked_until:
        return False
    return True


def is_plus(user):
    if user and user.is_owner:  # у владельца Nuvora+ бессрочно
        return True
    if not user or not user.is_plus:
        return False
    if user.plus_until and datetime.utcnow() > user.plus_until:
        return False
    return True


def needs_email(user):
    """Почта настроена, а пользователь ещё не подтвердил email — писать нельзя."""
    return bool(config.EMAIL_ENABLED and user and not user.email_verified and not user.is_owner)


VERIFY_MSG = "Подтвердите email, чтобы писать — код отправлен на вашу почту (страница /verify)"


def can_mod(user):
    return bool(user and (user.is_owner or user.is_moderator))


ONLINE_SECONDS = 120  # «в сети» — если был активен последние 2 минуты и не закрыл приложение


def is_online(user):
    if not (user and user.show_online is not False and user.last_seen):
        return False
    if user.offline_at and user.offline_at >= user.last_seen:
        return False
    return (datetime.utcnow() - user.last_seen).total_seconds() < ONLINE_SECONDS


# --- Связи между людьми. Один запрос на человека за запрос страницы: результат запоминается в сессии БД
#     (session.info) и сбрасывается при любой записи (flush/commit/rollback), так что устаревшим не бывает.
def _memo(db, key, fn):
    cache = db.info.setdefault("social_memo", {})
    if key not in cache:
        cache[key] = frozenset(fn())
    return cache[key]


def _reset_memo(session, *_):
    session.info.pop("social_memo", None)


from sqlalchemy import event as _event  # noqa: E402
from sqlalchemy.orm import Session as _Session  # noqa: E402
for _name in ("after_flush", "after_commit", "after_rollback", "after_soft_rollback"):
    _event.listen(_Session, _name, _reset_memo)


def follower_ids(db, user):
    """Кто подписан на человека."""
    if not user:
        return set()
    return set(_memo(db, ("followers", user.id), lambda: (
        f.follower_id for f in db.query(models.Follow.follower_id).filter(models.Follow.following_id == user.id))))


def wall_allowed(db, owner, actor):
    """Можно ли actor написать на стене owner (настройка «Кто может писать на моей стене»)."""
    from services import prefs
    if not owner or not actor:
        return False
    if owner.id == actor.id:
        return True
    if is_blocked_between(db, owner, actor) or is_active_block(actor):
        return False
    mode = prefs.get(owner, "who_can_post_wall")
    if mode == "nobody":
        return False
    if mode == "all":
        return True
    follows_me = is_following(db, actor, owner)
    if mode == "followers":
        return follows_me
    return follows_me and is_following(db, owner, actor)  # mutual — друзья


def following_ids(db, user):
    if not user:
        return set()
    return set(_memo(db, ("following", user.id), lambda: (
        f.following_id for f in db.query(models.Follow.following_id).filter(models.Follow.follower_id == user.id))))


def is_following(db, a, b):
    if not a or not b:
        return False
    return b.id in _memo(db, ("following", a.id), lambda: (
        f.following_id for f in db.query(models.Follow.following_id).filter(models.Follow.follower_id == a.id)))


def _blocked(db, uid):
    rows = db.query(models.UserBlock.blocker_id, models.UserBlock.blocked_id).filter(
        or_(models.UserBlock.blocker_id == uid, models.UserBlock.blocked_id == uid))
    return (r.blocked_id if r.blocker_id == uid else r.blocker_id for r in rows)


def blocked_ids(db, user):
    """Все, кто заблокировал пользователя или кого заблокировал он."""
    if not user:
        return set()
    return set(_memo(db, ("blocked", user.id), lambda: _blocked(db, user.id)))


def is_blocked_between(db, a, b):
    if not a or not b:
        return False
    return b.id in _memo(db, ("blocked", a.id), lambda: _blocked(db, a.id))


def muted_ids(db, user):
    if not user:
        return set()
    return set(_memo(db, ("muted", user.id), lambda: (
        m.muted_id for m in db.query(models.UserMute.muted_id).filter(models.UserMute.user_id == user.id))))


def can_see_content(db, viewer, owner):
    """Видит ли viewer посты/истории owner (приватность и блокировки)."""
    if viewer and owner and viewer.id == owner.id:
        return True
    if viewer and can_mod(viewer):
        return True
    if is_blocked_between(db, viewer, owner):
        return False
    if owner.is_private:
        return is_following(db, viewer, owner)
    return True


def _locked(user):
    try:
        from packs.v3.accounts import posts_locked
        return posts_locked(user)
    except ImportError:
        return False


def visible_posts(db, viewer, hide_muted=True):
    """Базовый запрос постов, которые viewer имеет право видеть."""
    now = datetime.utcnow()
    from sqlalchemy.orm import selectinload
    q = db.query(models.Post).options(selectinload(models.Post.author)).join(models.User, models.Post.user_id == models.User.id).filter(
        models.Post.is_published == True, models.Post.is_draft == False,
        or_(models.Post.scheduled_at == None, models.Post.scheduled_at <= now),
        or_(models.Post.is_archived == None, models.Post.is_archived == False),
        or_(models.Post.expires_at == None, models.Post.expires_at > now))
    if _locked(viewer):  # аккаунт «только чаты и профиль»: видны только свои посты
        return q.filter(models.Post.user_id == viewer.id)
    if not (viewer and can_mod(viewer)):  # приостановленные аккаунты скрыты (кроме своих постов)
        q = q.filter(or_(models.User.is_paused == None, models.User.is_paused == False, models.User.id == (viewer.id if viewer else -1)))
    if viewer and can_mod(viewer):
        return q
    fids = following_ids(db, viewer)
    own = {viewer.id} if viewer else set()
    allowed = fids | own
    q = q.filter(or_(models.User.is_private == False, models.User.is_private == None, models.Post.user_id.in_(allowed or {-1}),
                     models.Post.community_id != None))
    q = q.filter(or_(models.Post.visibility == None, models.Post.visibility != "followers", models.Post.user_id.in_(allowed or {-1})))
    hidden = blocked_ids(db, viewer)
    if hide_muted:
        hidden |= muted_ids(db, viewer)
    if not viewer:  # «скрыть мои посты от незарегистрированных» — во всех разделах, а не только в ленте
        hidden |= {u.id for u in db.query(models.User.id).filter(models.User.prefs.like('%"guests_hidden": true%'))}
    if hidden:
        q = q.filter(~models.Post.user_id.in_(hidden))
    return q


def can_view_post(db, viewer, post):
    if not post:
        return False
    if viewer and viewer.id == post.user_id:
        return True
    if _locked(viewer):  # «только чаты и профиль»: чужие посты не видны
        return False
    if viewer and can_mod(viewer):
        return True
    if post.is_draft or not post.is_published or post.is_archived:
        return False
    if post.expires_at and post.expires_at <= datetime.utcnow():
        return False
    if post.author and post.author.is_paused:
        return False
    if not viewer:
        from services import prefs
        if post.author and prefs.get(post.author, "guests_hidden"):
            return False
    if post.scheduled_at and post.scheduled_at > datetime.utcnow():
        return False
    if not post.community_id and not can_see_content(db, viewer, post.author):
        return False
    if post.visibility == "followers" and not is_following(db, viewer, post.author):
        return False
    return True


def can_message(db, sender, receiver):
    if not sender or not receiver or sender.id == receiver.id:
        return False, "Нельзя написать этому пользователю"
    if can_mod(sender):
        return True, ""
    if is_blocked_between(db, sender, receiver):
        return False, "Пользователь недоступен"
    mode = receiver.who_can_message or "all"
    if mode == "nobody":
        return False, "Пользователь ограничил входящие сообщения"
    if mode == "followers" and not is_following(db, receiver, sender):  # «те, на кого я подписан»
        # если уже есть переписка — разрешаем отвечать
        had = db.query(models.Message.id).filter(models.Message.sender_id == receiver.id, models.Message.receiver_id == sender.id).first()
        if not had:
            return False, "Писать могут только те, на кого подписан пользователь"
    return True, ""


def notify(db, user_id, ntype, from_user=None, post_id=None, text="", url=None):
    """Создаёт уведомление (если получатель не отключил этот тип) и отправляет push."""
    if from_user and from_user.id == user_id:
        return None
    target = db.get(models.User, user_id)
    if not target:
        return None
    pref = NOTIFY_PREF.get(ntype)
    if pref and getattr(target, pref) is False:
        return None
    from services import prefs
    extra = prefs.NOTIFY_PREFS.get(ntype)
    if extra and not prefs.get(target, extra):
        return None
    if from_user and is_blocked_between(db, from_user, target):
        return None
    n = models.Notification(user_id=user_id, from_user_id=from_user.id if from_user else None, type=ntype, post_id=post_id, text=text or "")
    db.add(n)
    who = (from_user.name or from_user.username) if from_user else config.BRAND_NAME
    body = text or NOTIFY_TEXT.get(ntype, "новое уведомление")
    push.send_push_to_user(user_id, db, config.BRAND_NAME, f"{who} {body}" if from_user else body,
                           url or (f"/post/{post_id}" if post_id else "/notifications"))
    return n


def process_mentions(db, author, text, post_id=None, kind="mention"):
    names = extract_mentions(text)
    if not names:
        return
    users = db.query(models.User).filter(models.User.username.in_(names)).all()
    from services import prefs
    post = db.get(models.Post, post_id) if post_id else None
    for u in users[:20]:
        # не уведомляем о посте, который человек не может открыть (отложенный, только для подписчиков, закрытый профиль)
        if post and not can_view_post(db, u, post):
            continue
        if u.id != author.id and prefs.audience_allows(db, u, author, "who_can_mention"):
            notify(db, u.id, kind, author, post_id=post_id)


def stop_words(db):
    return [w.word for w in db.query(models.StopWord).all()]


def main_owner(db):
    """Основатель сайта (совладельцы имеют те же права, но «лицо» сайта — он)."""
    q = db.query(models.User).filter(models.User.is_owner == True)
    return q.filter(models.User.co_owner != True).first() or q.first()
