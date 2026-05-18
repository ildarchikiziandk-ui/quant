from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

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
    author = relationship("User", back_populates="posts")
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
    author = relationship("User")
    post = relationship("Post", back_populates="comments")
    replies = relationship("Comment", foreign_keys=[parent_id])

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"))
    receiver_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    group_id = Column(Integer, ForeignKey("group_chats.id"), nullable=True)
    content = Column(Text, default="")
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
    disappear_at = Column(DateTime, nullable=True)
    is_pinned = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_read = Column(Boolean, default=False)
    is_delivered = Column(Boolean, default=False)
    forwarded_from_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_deleted = Column(Boolean, default=False)
    is_muted = Column(Boolean, default=False)
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
    content = Column(Text, default="")
    image = Column(String, default="")
    voice = Column(String, default="")
    file_url = Column(String, default="")
    file_name = Column(String, default="")
    sticker_id = Column(Integer, ForeignKey("stickers.id"), nullable=True)
    gif_url = Column(String, default="")
    reply_to_id = Column(Integer, ForeignKey("group_messages.id"), nullable=True)
    is_deleted = Column(Boolean, default=False)
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
    stickers = relationship("Sticker", foreign_keys="Sticker.pack_id")

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
    emoji = Column(String, default="⚡")
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
    prize = Column(String, default="Quant Plus 30 дней")
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
    emoji = Column(String, default="🏆")
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