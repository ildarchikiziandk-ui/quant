"""Таблицы функций Nuvora 3.0. Создаются автоматически при запуске (create_all)."""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from database import Base


# --- Чаты -------------------------------------------------------------------------------------------------
class ChatPoll(Base):
    """Опрос внутри личной переписки (сообщение с меткой [[v3:poll:ID]])."""
    __tablename__ = "v3_chat_polls"
    id = Column(Integer, primary_key=True)
    creator_id = Column(Integer, ForeignKey("users.id"), index=True)
    peer_id = Column(Integer, ForeignKey("users.id"), index=True)
    question = Column(String(200), default="")
    options = Column(Text, default="[]")  # JSON-список вариантов
    multi = Column(Boolean, default=False)
    closed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ChatPollVote(Base):
    __tablename__ = "v3_chat_poll_votes"
    id = Column(Integer, primary_key=True)
    poll_id = Column(Integer, ForeignKey("v3_chat_polls.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    option = Column(Integer, default=0)


class TttGame(Base):
    """Крестики-нолики в переписке: a — крестики (ходит первым), b — нолики."""
    __tablename__ = "v3_ttt_games"
    id = Column(Integer, primary_key=True)
    a_id = Column(Integer, ForeignKey("users.id"), index=True)
    b_id = Column(Integer, ForeignKey("users.id"), index=True)
    board = Column(String(9), default=" " * 9)
    turn = Column(Integer)  # id того, чей ход
    winner = Column(Integer, nullable=True)  # id победителя; 0 — ничья
    line = Column(String(10), default="")  # выигрышная линия, «0,4,8»
    updated_at = Column(DateTime, default=datetime.utcnow)


class ChatFolder(Base):
    """Своя папка чатов («Семья», «Учёба»): список логинов собеседников."""
    __tablename__ = "v3_chat_folders"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    name = Column(String(30), default="")
    members = Column(Text, default="[]")
    pos = Column(Integer, default=0)


# --- Лента ------------------------------------------------------------------------------------------------
class PostCountdown(Base):
    __tablename__ = "v3_post_countdowns"
    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey("posts.id"), unique=True)
    title = Column(String(60), default="")
    at = Column(DateTime)


class TempMute(Base):
    """«Не показывать автора 30 дней»: снимается фоновой задачей."""
    __tablename__ = "v3_temp_mutes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    muted_id = Column(Integer, ForeignKey("users.id"))
    until = Column(DateTime, index=True)


# --- Люди -------------------------------------------------------------------------------------------------
class ProfileLink(Base):
    __tablename__ = "v3_profile_links"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    title = Column(String(40), default="")
    url = Column(String(300), default="")
    clicks = Column(Integer, default=0)
    pos = Column(Integer, default=0)


class DailyChest(Base):
    __tablename__ = "v3_daily_chest"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    last_day = Column(String(10), default="")
    streak = Column(Integer, default=0)
    total = Column(Integer, default=0)


# --- Барахолка --------------------------------------------------------------------------------------------
class MarketItem(Base):
    __tablename__ = "v3_market_items"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    title = Column(String(80), default="")
    description = Column(Text, default="")
    price = Column(Integer, default=0)  # рубли; 0 — «Отдам даром»
    category = Column(String(20), default="other", index=True)
    city = Column(String(60), default="")
    condition = Column(String(10), default="used")
    photos = Column(Text, default="[]")
    sold = Column(Boolean, default=False)
    views = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class MarketFav(Base):
    __tablename__ = "v3_market_favs"
    __table_args__ = (UniqueConstraint("user_id", "item_id"),)
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    item_id = Column(Integer, ForeignKey("v3_market_items.id"))


# --- Личное: привычки, настроение, капсула ----------------------------------------------------------------
class Habit(Base):
    __tablename__ = "v3_habits"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    name = Column(String(50), default="")
    color = Column(String(7), default="#6d5dfc")
    created_at = Column(DateTime, default=datetime.utcnow)


class HabitCheck(Base):
    __tablename__ = "v3_habit_checks"
    __table_args__ = (UniqueConstraint("habit_id", "day"),)
    id = Column(Integer, primary_key=True)
    habit_id = Column(Integer, ForeignKey("v3_habits.id"), index=True)
    day = Column(String(10))


class MoodEntry(Base):
    __tablename__ = "v3_moods"
    __table_args__ = (UniqueConstraint("user_id", "day"),)
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    day = Column(String(10))
    level = Column(Integer, default=3)
    note = Column(String(300), default="")


class Capsule(Base):
    __tablename__ = "v3_capsules"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    text = Column(Text, default="")
    open_at = Column(DateTime, index=True)
    notified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# --- Игры -------------------------------------------------------------------------------------------------
class WordGame(Base):
    __tablename__ = "v3_word_games"
    __table_args__ = (UniqueConstraint("user_id", "day"),)
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    day = Column(String(10))
    guesses = Column(Text, default="[]")
    solved = Column(Boolean, default=False)


class Score2048(Base):
    __tablename__ = "v3_scores_2048"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    best = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow)


# --- Безопасность -----------------------------------------------------------------------------------------
class BackupCode(Base):
    __tablename__ = "v3_backup_codes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    code_hash = Column(String(64))
    used = Column(Boolean, default=False)


class SeenDevice(Base):
    """Устройства, с которых человек уже входил: вход с нового — уведомление."""
    __tablename__ = "v3_seen_devices"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    device = Column(String(120), default="")
    last_session_id = Column(Integer, default=0)


# --- ИИ ---------------------------------------------------------------------------------------------------
class AiUsage(Base):
    """Каждый запрос к ИИ: для дневного лимита на человека и общего бюджета токенов."""
    __tablename__ = "v3_ai_usage"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    day = Column(String(10), index=True)
    kind = Column(String(16), default="")
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
