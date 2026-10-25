from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Float
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class EncryptedText(TypeDecorator):
    """Текст, который хранится в базе зашифрованным (AES-256-GCM, см. services/crypto.py)."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        from services import crypto
        return crypto.encrypt(value)

    def process_result_value(self, value, dialect):
        from services import crypto
        return crypto.decrypt(value)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, default="")
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    avatar = Column(String, default="")
    cover = Column(String, default="")
    bio = Column(String, default="")
    website = Column(String, default="")
    work = Column(String(80), default="")  # работа или учёба — показывается в профиле
    birthday = Column(String, default="")
    emoji_status = Column(String, default="")
    city = Column(String, default="")
    telegram_link = Column(String, default="")
    youtube_link = Column(String, default="")
    tiktok_link = Column(String, default="")
    is_verified = Column(Boolean, default=False)
    is_owner = Column(Boolean, default=False)
    is_starred = Column(Boolean, default=False)
    is_verified_badge = Column(Boolean, default=False)
    is_moderator = Column(Boolean, default=False)
    is_blocked = Column(Boolean, default=False)
    blocked_until = Column(DateTime, nullable=True)
    is_plus = Column(Boolean, default=False)
    plus_until = Column(DateTime, nullable=True)
    plus_color = Column(String, default="#a855f7")
    last_seen = Column(DateTime, nullable=True)
    offline_at = Column(DateTime, nullable=True)  # закрыл приложение — сразу «не в сети»
    pinned_post_id = Column(Integer, nullable=True)
    is_private = Column(Boolean, default=False)
    daily_points = Column(Integer, default=0)
    weekly_points = Column(Integer, default=0)
    total_points = Column(Integer, default=0)
    level = Column(Integer, default=1)
    streak_days = Column(Integer, default=0)
    last_streak_date = Column(String, default="")
    two_factor_enabled = Column(Boolean, default=False)
    two_factor_secret = Column(String, default="")
    email_verified = Column(Boolean, default=False)
    theme = Column(String, default="light")
    font_size = Column(String, default="medium")
    who_can_message = Column(String, default="all")
    who_can_see_stories = Column(String, default="all")
    hide_likes = Column(Boolean, default=False)
    language = Column(String, default="ru")
    accent_color = Column(String, default="")
    show_online = Column(Boolean, default=True)
    notify_likes = Column(Boolean, default=True)
    notify_comments = Column(Boolean, default=True)
    notify_follows = Column(Boolean, default=True)
    notify_mentions = Column(Boolean, default=True)
    notify_messages = Column(Boolean, default=True)
    profile_views = Column(Integer, default=0)
    pronouns = Column(String, default="")
    prefs = Column(Text, default="")
    interests = Column(String, default="")
    referred_by = Column(Integer, nullable=True)
    spent_points = Column(Integer, default=0)
    status_text = Column(String, default="")
    status_until = Column(DateTime, nullable=True)
    links = Column(Text, default="")
    avatar_frame = Column(String, default="")
    frames_owned = Column(String, default="")
    streak_freezes = Column(Integer, default=0)
    last_spin = Column(String, default="")
    dnd_until = Column(DateTime, nullable=True)
    is_paused = Column(Boolean, default=False)
    pd_consent_at = Column(DateTime, nullable=True)  # согласие на обработку персональных данных (152-ФЗ ст. 9)
    pd_consent_version = Column(String(20), default="")
    age_confirmed = Column(Boolean, default=False)
    yandex_id = Column(String(32), nullable=True, index=True)  # вход через Яндекс ID
    last_spin2 = Column(String(10), default="")  # второе вращение колеса (Plus)
    plus_shield_date = Column(String(10), default="")  # когда последний раз сработала защита стрика (Plus)  # подтвердил, что ему есть MIN_AGE лет
    created_at = Column(DateTime, default=datetime.utcnow)
    posts = relationship("Post", back_populates="author")
    followers = relationship("Follow", foreign_keys="Follow.following_id", back_populates="following")
    following = relationship("Follow", foreign_keys="Follow.follower_id", back_populates="follower")
    notifications = relationship("Notification", foreign_keys="Notification.user_id", back_populates="user")
    achievements = relationship("UserAchievement", back_populates="user")
    bookmarks = relationship("Bookmark", back_populates="user")
    sessions = relationship("UserSession", back_populates="user")
    special_requests = relationship("SpecialRequest", foreign_keys="SpecialRequest.user_id", back_populates="user")
    blocked_users = relationship("UserBlock", foreign_keys="UserBlock.blocker_id", back_populates="blocker")
    daily_tasks = relationship("UserDailyTask", back_populates="user")
    raffle_entries = relationship("RaffleEntry", back_populates="user")
    stickers = relationship("UserSticker", back_populates="user")

class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text)
    image = Column(String, default="")
    media_type = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))
    is_repost = Column(Boolean, default=False)
    repost_id = Column(Integer, nullable=True)
    original_comment = Column(Text, default="")
    scheduled_at = Column(DateTime, nullable=True)
    is_published = Column(Boolean, default=True)
    is_draft = Column(Boolean, default=False)
    views = Column(Integer, default=0)
    is_exclusive = Column(Boolean, default=False)
    exclusive_until = Column(DateTime, nullable=True)
    is_long = Column(Boolean, default=False)
    pinned_comment_id = Column(Integer, nullable=True)
    edited_at = Column(DateTime, nullable=True)
    comments_disabled = Column(Boolean, default=False)
    visibility = Column(String, default="all")
    content_warning = Column(String, default="")
    mood = Column(String, default="")
    location = Column(String, default="")
    bg = Column(String, default="")
    is_archived = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=True)
    community_id = Column(Integer, nullable=True, index=True)  # пост в канале или сообществе (Nuvora 3.2)
    wall_owner_id = Column(Integer, nullable=True, index=True)  # запись на стене другого человека
    author = relationship("User", back_populates="posts")
    wall_owner = relationship("User", primaryjoin="Post.wall_owner_id == User.id", foreign_keys=[wall_owner_id], viewonly=True)
    likes = relationship("Like", back_populates="post")
    comments = relationship("Comment", back_populates="post")
    whales = relationship("Whale", back_populates="post")
    reactions = relationship("Reaction", back_populates="post")
    poll = relationship("Poll", back_populates="post", uselist=False)
    media_items = relationship("PostMedia", back_populates="post")
    post_reports = relationship("PostReport", back_populates="post")

class PostMedia(Base):
    __tablename__ = "post_media"
    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"))
    media_url = Column(String, default="")
    media_type = Column(String, default="image")
    position = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    post = relationship("Post", back_populates="media_items")

class Reel(Base):
    __tablename__ = "reels"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    video_url = Column(String)
    thumbnail_url = Column(String, default="")
    caption = Column(Text, default="")
    views = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    author = relationship("User")
    likes = relationship("ReelLike", back_populates="reel")
    comments = relationship("ReelComment", back_populates="reel")

class ReelLike(Base):
    __tablename__ = "reel_likes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    reel_id = Column(Integer, ForeignKey("reels.id"))
    reel = relationship("Reel", back_populates="likes")

class ReelComment(Base):
    __tablename__ = "reel_comments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    reel_id = Column(Integer, ForeignKey("reels.id"))
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    author = relationship("User")
    reel = relationship("Reel", back_populates="comments")

class Follow(Base):
    __tablename__ = "follows"
    id = Column(Integer, primary_key=True, index=True)
    follower_id = Column(Integer, ForeignKey("users.id"))
    following_id = Column(Integer, ForeignKey("users.id"))
    follower = relationship("User", foreign_keys=[follower_id], back_populates="following")
    following = relationship("User", foreign_keys=[following_id], back_populates="followers")

class Like(Base):
    __tablename__ = "likes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    post_id = Column(Integer, ForeignKey("posts.id"))
    post = relationship("Post", back_populates="likes")

class Whale(Base):
    __tablename__ = "whales"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    post_id = Column(Integer, ForeignKey("posts.id"))
    post = relationship("Post", back_populates="whales")

class Reaction(Base):
    __tablename__ = "reactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    post_id = Column(Integer, ForeignKey("posts.id"))
    emoji = Column(String, default="")
    post = relationship("Post", back_populates="reactions")

class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))
    post_id = Column(Integer, ForeignKey("posts.id"))
    parent_id = Column(Integer, ForeignKey("comments.id"), nullable=True)
    is_pinned = Column(Boolean, default=False)
    edited_at = Column(DateTime, nullable=True)
    is_hidden = Column(Boolean, default=False)
    author = relationship("User")
    post = relationship("Post", back_populates="comments")
    replies = relationship("Comment", foreign_keys=[parent_id])
    comment_likes = relationship("CommentLike", back_populates="comment")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"))
    receiver_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    group_id = Column(Integer, ForeignKey("group_chats.id"), nullable=True)
    content = Column(EncryptedText, default="")
    content_encrypted = Column(Text, default="")
    image = Column(String, default="")
    voice = Column(String, default="")
    file_url = Column(String, default="")
    file_name = Column(String, default="")
    file_size = Column(Integer, default=0)
    sticker_id = Column(Integer, ForeignKey("stickers.id"), nullable=True)
    gif_url = Column(String, default="")
    is_video_circle = Column(Boolean, default=False)
    reply_to_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    is_edited = Column(Boolean, default=False)
    edited_at = Column(DateTime, nullable=True)
    deliver_at = Column(DateTime, nullable=True, index=True)  # отложенное сообщение
    scheduled_pending = Column(Boolean, default=False)  # ещё не доставлено (нужно отправить push)
    silent = Column(Boolean, default=False)  # без звука: без push-уведомления
    effect = Column(String(12), default="")  # эффект сообщения 3.0: confetti, hearts, snow, fireworks
    deleted_for = Column(Integer, nullable=True)  # «удалить у меня» — скрыто только у этого пользователя
    disappear_at = Column(DateTime, nullable=True)
    is_pinned = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_read = Column(Boolean, default=False)
    is_delivered = Column(Boolean, default=False)
    forwarded_from_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_deleted = Column(Boolean, default=False)
    is_muted = Column(Boolean, default=False)
    media_expired = Column(String(12), default="")  # вложение стёрто с сервера через 7 дней: photo, video, file, voice, circle
    sender = relationship("User", foreign_keys=[sender_id])
    receiver = relationship("User", foreign_keys=[receiver_id])
    forwarded_from = relationship("User", foreign_keys=[forwarded_from_id])
    reply_to = relationship("Message", foreign_keys=[reply_to_id], remote_side="Message.id")
    msg_reactions = relationship("MessageReaction", back_populates="message")
    sticker = relationship("Sticker", foreign_keys=[sticker_id])

class GroupChat(Base):
    __tablename__ = "group_chats"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    avatar = Column(String, default="")
    description = Column(String, default="")
    owner_id = Column(Integer, ForeignKey("users.id"))
    invite_code = Column(String, default="", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = relationship("User", foreign_keys=[owner_id])
    members = relationship("GroupMember", back_populates="group")
    messages = relationship("GroupMessage", back_populates="group")

class GroupMember(Base):
    __tablename__ = "group_members"
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("group_chats.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    is_admin = Column(Boolean, default=False)
    joined_at = Column(DateTime, default=datetime.utcnow)
    group = relationship("GroupChat", back_populates="members")
    user = relationship("User")

class GroupMessage(Base):
    __tablename__ = "group_messages"
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("group_chats.id"))
    sender_id = Column(Integer, ForeignKey("users.id"))
    content = Column(EncryptedText, default="")
    image = Column(String, default="")
    voice = Column(String, default="")
    file_url = Column(String, default="")
    file_name = Column(String, default="")
    sticker_id = Column(Integer, ForeignKey("stickers.id"), nullable=True)
    gif_url = Column(String, default="")
    reply_to_id = Column(Integer, ForeignKey("group_messages.id"), nullable=True)
    is_deleted = Column(Boolean, default=False)
    is_video_circle = Column(Boolean, default=False)
    media_expired = Column(String(12), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    group = relationship("GroupChat", back_populates="messages")
    sender = relationship("User", foreign_keys=[sender_id])
    sticker = relationship("Sticker", foreign_keys=[sticker_id])

class MessageReaction(Base):
    __tablename__ = "message_reactions"
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    emoji = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    message = relationship("Message", back_populates="msg_reactions")

class PinnedChat(Base):
    __tablename__ = "pinned_chats"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    pinned_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    pinned_group_id = Column(Integer, ForeignKey("group_chats.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class MutedChat(Base):
    __tablename__ = "muted_chats"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    muted_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    muted_group_id = Column(Integer, ForeignKey("group_chats.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    until = Column(DateTime, nullable=True)  # «без звука на время»; пусто — навсегда

class Sticker(Base):
    __tablename__ = "stickers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    emoji = Column(String, default="")
    image_url = Column(String, default="")
    pack_id = Column(Integer, ForeignKey("sticker_packs.id"), nullable=True)
    is_animated = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    pack = relationship("StickerPack", foreign_keys=[pack_id])

class StickerPack(Base):
    __tablename__ = "sticker_packs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    description = Column(String, default="")
    cover_url = Column(String, default="")
    is_free = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    stickers = relationship("Sticker", foreign_keys="Sticker.pack_id", overlaps="pack")

class UserSticker(Base):
    __tablename__ = "user_stickers"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    pack_id = Column(Integer, ForeignKey("sticker_packs.id"))
    added_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="stickers")
    pack = relationship("StickerPack")

class StoryReaction(Base):
    __tablename__ = "story_reactions"
    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    emoji = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    type = Column(String)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=True)
    text = Column(String, default="")
    reply_email = Column(String, default="")
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", foreign_keys=[user_id], back_populates="notifications")
    from_user = relationship("User", foreign_keys=[from_user_id])
    post = relationship("Post")

class VerificationCode(Base):
    __tablename__ = "verification_codes"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True)
    code = Column(String)
    purpose = Column(String, default="register")
    created_at = Column(DateTime, default=datetime.utcnow)

class Promocode(Base):
    __tablename__ = "promocodes"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    days = Column(Integer, default=30)
    max_uses = Column(Integer, default=1)
    uses = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Story(Base):
    __tablename__ = "stories"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    media_url = Column(String)
    media_type = Column(String, default="image")
    text_overlay = Column(String, default="")
    music_url = Column(String, default="")
    audience = Column(String, default="all")
    bg_color = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    author = relationship("User")
    views = relationship("StoryView", back_populates="story")
    reactions = relationship("StoryReaction")

class StoryView(Base):
    __tablename__ = "story_views"
    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    viewed_at = Column(DateTime, default=datetime.utcnow)
    story = relationship("Story", back_populates="views")

class Poll(Base):
    __tablename__ = "polls"
    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), unique=True)
    question = Column(String)
    ends_at = Column(DateTime, nullable=True)
    correct_option_id = Column(Integer, nullable=True)  # викторина: правильный ответ
    created_at = Column(DateTime, default=datetime.utcnow)
    post = relationship("Post", back_populates="poll")
    options = relationship("PollOption", back_populates="poll")

class PollOption(Base):
    __tablename__ = "poll_options"
    id = Column(Integer, primary_key=True, index=True)
    poll_id = Column(Integer, ForeignKey("polls.id"))
    text = Column(String)
    poll = relationship("Poll", back_populates="options")
    votes = relationship("PollVote", back_populates="option")

class PollVote(Base):
    __tablename__ = "poll_votes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    option_id = Column(Integer, ForeignKey("poll_options.id"))
    poll_id = Column(Integer, ForeignKey("polls.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    option = relationship("PollOption", back_populates="votes")

class TypingStatus(Base):
    __tablename__ = "typing_status"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    target_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    group_id = Column(Integer, ForeignKey("group_chats.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)
    kind = Column(String(10), default="text")  # text / voice / circle — «печатает», «записывает голосовое»…

class StopWord(Base):
    __tablename__ = "stop_words"
    id = Column(Integer, primary_key=True, index=True)
    word = Column(String, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    endpoint = Column(Text)
    p256dh = Column(Text)
    auth = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class Achievement(Base):
    __tablename__ = "achievements"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True)
    name = Column(String)
    description = Column(String)
    emoji = Column(String)
    points_reward = Column(Integer, default=0)

class UserAchievement(Base):
    __tablename__ = "user_achievements"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    achievement_id = Column(Integer, ForeignKey("achievements.id"))
    earned_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="achievements")
    achievement = relationship("Achievement")

class Bookmark(Base):
    __tablename__ = "bookmarks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    post_id = Column(Integer, ForeignKey("posts.id"))
    collection_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="bookmarks")
    post = relationship("Post")

class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True, index=True)
    reporter_id = Column(Integer, ForeignKey("users.id"))
    target_id = Column(Integer, ForeignKey("users.id"))
    reason = Column(String, default="")
    text = Column(Text, default="")
    image_1 = Column(String, default="")
    image_2 = Column(String, default="")
    image_3 = Column(String, default="")
    image_4 = Column(String, default="")
    image_5 = Column(String, default="")
    status = Column(String, default="new")
    admin_comment = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    reporter = relationship("User", foreign_keys=[reporter_id])
    target = relationship("User", foreign_keys=[target_id])

class PostReport(Base):
    __tablename__ = "post_reports"
    id = Column(Integer, primary_key=True, index=True)
    reporter_id = Column(Integer, ForeignKey("users.id"))
    post_id = Column(Integer, ForeignKey("posts.id"))
    reason = Column(String, default="")
    status = Column(String, default="new")
    created_at = Column(DateTime, default=datetime.utcnow)
    reporter = relationship("User", foreign_keys=[reporter_id])
    post = relationship("Post", back_populates="post_reports")

class UserSession(Base):
    __tablename__ = "user_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    token_hash = Column(String, index=True)
    device = Column(String, default="")
    ip = Column(String, default="")
    user_agent = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    user = relationship("User", back_populates="sessions")

class SpecialRequest(Base):
    __tablename__ = "special_requests"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    type = Column(String)
    reason = Column(Text, default="")
    links = Column(String, default="")
    status = Column(String, default="new")
    admin_comment = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", foreign_keys=[user_id], back_populates="special_requests")

class UserBlock(Base):
    __tablename__ = "user_blocks"
    id = Column(Integer, primary_key=True, index=True)
    blocker_id = Column(Integer, ForeignKey("users.id"))
    blocked_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    blocker = relationship("User", foreign_keys=[blocker_id], back_populates="blocked_users")
    blocked = relationship("User", foreign_keys=[blocked_id])

class DailyTask(Base):
    __tablename__ = "daily_tasks"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True)
    title = Column(String)
    description = Column(String)
    emoji = Column(String, default="bolt")
    points = Column(Integer, default=10)
    task_type = Column(String)
    target_count = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)

class UserDailyTask(Base):
    __tablename__ = "user_daily_tasks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    task_id = Column(Integer, ForeignKey("daily_tasks.id"))
    progress = Column(Integer, default=0)
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    date = Column(String, default="")
    user = relationship("User", back_populates="daily_tasks")
    task = relationship("DailyTask")

class WeeklyRaffle(Base):
    __tablename__ = "weekly_raffles"
    id = Column(Integer, primary_key=True, index=True)
    week_start = Column(DateTime)
    week_end = Column(DateTime)
    prize = Column(String, default="Plus на 30 дней")
    prize_days = Column(Integer, default=30)
    winner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_finished = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    winner = relationship("User", foreign_keys=[winner_id])
    entries = relationship("RaffleEntry", back_populates="raffle")

class RaffleEntry(Base):
    __tablename__ = "raffle_entries"
    id = Column(Integer, primary_key=True, index=True)
    raffle_id = Column(Integer, ForeignKey("weekly_raffles.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    tickets = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    raffle = relationship("WeeklyRaffle", back_populates="entries")
    user = relationship("User", back_populates="raffle_entries")

class Trend(Base):
    __tablename__ = "trends"
    id = Column(Integer, primary_key=True, index=True)
    tag = Column(String, unique=True, index=True)
    count = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow)

class Draft(Base):
    __tablename__ = "drafts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    content = Column(Text, default="")
    image = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

class CallLog(Base):
    __tablename__ = "call_logs"
    id = Column(Integer, primary_key=True, index=True)
    caller_id = Column(Integer, ForeignKey("users.id"))
    receiver_id = Column(Integer, ForeignKey("users.id"))
    call_type = Column(String, default="voice")
    status = Column(String, default="missed")
    duration = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    caller = relationship("User", foreign_keys=[caller_id])
    receiver = relationship("User", foreign_keys=[receiver_id])

class WeeklyChallenge(Base):
    __tablename__ = "weekly_challenges"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(String)
    emoji = Column(String, default="trophy")
    points = Column(Integer, default=100)
    task_type = Column(String)
    target_count = Column(Integer, default=1)
    week_start = Column(DateTime)
    week_end = Column(DateTime)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class UserWeeklyChallenge(Base):
    __tablename__ = "user_weekly_challenges"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    challenge_id = Column(Integer, ForeignKey("weekly_challenges.id"))
    progress = Column(Integer, default=0)
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    user = relationship("User")
    challenge = relationship("WeeklyChallenge")


class CommentLike(Base):
    __tablename__ = "comment_likes"
    id = Column(Integer, primary_key=True, index=True)
    comment_id = Column(Integer, ForeignKey("comments.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    comment = relationship("Comment", back_populates="comment_likes")


class FollowRequest(Base):
    __tablename__ = "follow_requests"
    id = Column(Integer, primary_key=True, index=True)
    requester_id = Column(Integer, ForeignKey("users.id"), index=True)
    target_id = Column(Integer, ForeignKey("users.id"), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    requester = relationship("User", foreign_keys=[requester_id])
    target = relationship("User", foreign_keys=[target_id])


class UserMute(Base):
    __tablename__ = "user_mutes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    muted_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    muted = relationship("User", foreign_keys=[muted_id])


class CloseFriend(Base):
    __tablename__ = "close_friends"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    friend_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    friend = relationship("User", foreign_keys=[friend_id])


class StoryHighlight(Base):
    __tablename__ = "story_highlights"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    title = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    items = relationship("StoryHighlightItem", back_populates="highlight")


class StoryHighlightItem(Base):
    __tablename__ = "story_highlight_items"
    id = Column(Integer, primary_key=True, index=True)
    highlight_id = Column(Integer, ForeignKey("story_highlights.id"), index=True)
    story_id = Column(Integer, ForeignKey("stories.id"))
    highlight = relationship("StoryHighlight", back_populates="items")
    story = relationship("Story")


class Announcement(Base):
    __tablename__ = "announcements"
    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text, default="")
    level = Column(String, default="info")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ModLog(Base):
    __tablename__ = "mod_logs"
    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String, default="")
    target = Column(String, default="")
    details = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    actor = relationship("User", foreign_keys=[actor_id])


class ModerationFlag(Base):
    """Пометка собственной модели модерации: подозрительный пост или комментарий ждёт решения модератора."""
    __tablename__ = "moderation_flags"
    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String, default="post")  # post | comment
    object_id = Column(Integer, index=True)
    post_id = Column(Integer, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    label = Column(String, default="")
    score = Column(Float, default=0.0)
    snippet = Column(Text, default="")
    held = Column(Boolean, default=False)
    status = Column(String, default="new")  # new | approved | removed
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", foreign_keys=[user_id])


class SeenPost(Base):
    """Какие посты пользователь уже видел в рекомендациях — чтобы не показывать одно и то же."""
    __tablename__ = "seen_posts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    post_id = Column(Integer, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class NotInterested(Base):
    """Кнопка «Не интересно»: пост скрывается, а похожее показывается реже."""
    __tablename__ = "not_interested"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    post_id = Column(Integer, index=True)
    author_id = Column(Integer, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Question(Base):
    """Анонимные вопросы в профиль (как на ask.fm)."""
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True, index=True)
    to_user_id = Column(Integer, ForeignKey("users.id"), index=True)
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # хранится и для анонимных — для разбора жалоб
    is_anonymous = Column(Boolean, default=True)
    text = Column(Text, default="")
    answer = Column(Text, default="")
    answered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    to_user = relationship("User", foreign_keys=[to_user_id])
    from_user = relationship("User", foreign_keys=[from_user_id])


class HashtagFollow(Base):
    __tablename__ = "hashtag_follows"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    tag = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String, default="")
    description = Column(Text, default="")
    place = Column(String, default="")
    starts_at = Column(DateTime, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    author = relationship("User")
    rsvps = relationship("EventRSVP", back_populates="event")


class EventRSVP(Base):
    __tablename__ = "event_rsvps"
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String, default="going")  # going | maybe
    created_at = Column(DateTime, default=datetime.utcnow)
    event = relationship("Event", back_populates="rsvps")
    user = relationship("User")


class UserGift(Base):
    """Подарок за искры: виден в профиле получателя."""
    __tablename__ = "user_gifts"
    id = Column(Integer, primary_key=True, index=True)
    gift_code = Column(String)
    from_user_id = Column(Integer, ForeignKey("users.id"))
    to_user_id = Column(Integer, ForeignKey("users.id"), index=True)
    message = Column(String, default="")
    is_anonymous = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    from_user = relationship("User", foreign_keys=[from_user_id])
    to_user = relationship("User", foreign_keys=[to_user_id])


class BookmarkCollection(Base):
    __tablename__ = "bookmark_collections"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    name = Column(String, default="")
    emoji = Column(String, default="📁")
    created_at = Column(DateTime, default=datetime.utcnow)


class PostEdit(Base):
    """История правок поста: предыдущие версии текста."""
    __tablename__ = "post_edits"
    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, index=True)
    content = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class Note(Base):
    """Личные заметки — видны только владельцу."""
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    title = Column(String, default="")
    content = Column(Text, default="")
    is_pinned = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow)


class PostReminder(Base):
    """«Напомнить о посте» — через время придёт уведомление."""
    __tablename__ = "post_reminders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    post_id = Column(Integer)
    remind_at = Column(DateTime, index=True)
    done = Column(Boolean, default=False)


class SecretChat(Base):
    """Секретный чат: сквозное шифрование по ГОСТ в браузере. Сервер хранит только открытые ключи и шифротекст."""
    __tablename__ = "secret_chats"
    id = Column(Integer, primary_key=True, index=True)
    a_id = Column(Integer, index=True)  # кто начал
    b_id = Column(Integer, index=True)  # кого пригласили
    a_pub = Column(String(128), default="")  # открытый ключ ГОСТ Р 34.10-2012 (hex, 64 байта)
    b_pub = Column(String(128), default="")
    ukm = Column(String(16), default="")  # 8 случайных байт для VKO
    ttl = Column(Integer, default=0)  # таймер самоуничтожения сообщений, секунд (0 — выкл.)
    status = Column(String(10), default="pending")  # pending / active / closed
    created_at = Column(DateTime, default=datetime.utcnow)
    last_at = Column(DateTime, default=datetime.utcnow)


class SecretMessage(Base):
    __tablename__ = "secret_messages"
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, index=True)
    sender_id = Column(Integer)
    payload = Column(Text, default="")  # base64(iv ‖ имитовставка ‖ шифротекст) — сервер не может прочитать
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True, index=True)
    hidden = Column(Boolean, default=False)  # истёк таймер: пользователям не показывается


class ProfileVisit(Base):
    """Гости профиля (видны владельцам Nuvora+)."""
    __tablename__ = "profile_visits"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, index=True)
    viewer_id = Column(Integer, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ChatSetting(Base):
    """Личные настройки чата: оформление, архив, «отметить непрочитанным». peer_id=0 — оформление для всех чатов."""
    __tablename__ = "chat_settings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    peer_id = Column(Integer, nullable=True, index=True)
    group_id = Column(Integer, nullable=True, index=True)
    wallpaper = Column(String(300), default="")
    bubble = Column(String(20), default="")
    font = Column(String(10), default="")
    archived = Column(Boolean, default=False)
    marked_unread = Column(Boolean, default=False)


class ContactName(Base):
    """Как пользователь записал контакт у себя — видно только ему."""
    __tablename__ = "contact_names"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, index=True)
    target_id = Column(Integer, index=True)
    name = Column(String(60), default="")


class StarredMessage(Base):
    """Сообщение в «Избранном» — у каждого своё."""
    __tablename__ = "starred_messages"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    message = relationship("Message")


class MessageReminder(Base):
    """«Напомнить позже» о сообщении: в нужное время придёт уведомление."""
    __tablename__ = "message_reminders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"))
    remind_at = Column(DateTime, index=True)
    done = Column(Boolean, default=False)
    message = relationship("Message")
