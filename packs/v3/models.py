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


class TempMute(Base):
    """«Не показывать автора 30 дней»: снимается фоновой задачей."""
    __tablename__ = "v3_temp_mutes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    muted_id = Column(Integer, ForeignKey("users.id"))
    until = Column(DateTime, index=True)


# --- Люди -------------------------------------------------------------------------------------------------


class DailyChest(Base):
    __tablename__ = "v3_daily_chest"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    last_day = Column(String(10), default="")
    streak = Column(Integer, default=0)
    total = Column(Integer, default=0)


# --- Капсула времени ---------------------------------------------------------------------------------------
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



# --- Помощник Нува ----------------------------------------------------------------------------------------
class NuvaAnswer(Base):
    """Ответ, который модератор добавил помощнику из админки."""
    __tablename__ = "v3_nuva_answers"
    id = Column(Integer, primary_key=True)
    question = Column(String(200), default="")
    keywords = Column(String(300), default="")
    answer = Column(Text, default="")
    link_url = Column(String(300), default="")
    link_title = Column(String(60), default="")
    hits = Column(Integer, default=0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class NuvaMiss(Base):
    """Вопрос, на который Нува не нашла ответа (одинаковые вопросы складываются в счётчик)."""
    __tablename__ = "v3_nuva_misses"
    id = Column(Integer, primary_key=True)
    key = Column(String(200), unique=True, index=True)
    question = Column(String(300), default="")
    count = Column(Integer, default=1)
    last_at = Column(DateTime, default=datetime.utcnow)


# --- Красивые логины ---------------------------------------------------------------------------------------
class HandlePurchase(Base):
    """Покупка красивого логина за баллы."""
    __tablename__ = "v3_handle_purchases"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    username = Column(String(30), default="")
    old_username = Column(String(30), default="")
    price = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserAlias(Base):
    """Дополнительный логин: у человека до трёх логинов — основной (users.username) и два дополнительных."""
    __tablename__ = "v3_user_aliases"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    handle = Column(String(30), unique=True, index=True)  # в нижнем регистре
    created_at = Column(DateTime, default=datetime.utcnow)
