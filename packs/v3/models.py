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
    """Покупка красивого логина за искры."""
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


# --- Настройки сайта (меняются из админ-панели без перезапуска) ---------------------------------------------
class SiteSetting(Base):
    __tablename__ = "v3_site_settings"
    key = Column(String(40), primary_key=True)
    value = Column(Text, default="")


# --- Звонки 1 на 1 (видео идёт напрямую между собеседниками, сервер только передаёт сигналы) ----------------
class Call(Base):
    __tablename__ = "v3_calls"
    id = Column(Integer, primary_key=True)
    caller_id = Column(Integer, ForeignKey("users.id"), index=True)
    callee_id = Column(Integer, ForeignKey("users.id"), index=True)
    video = Column(Boolean, default=True)
    status = Column(String(12), default="ringing", index=True)  # ringing, active, ended, missed, declined, busy
    notif_id = Column(Integer, nullable=True)  # уведомление «звонит вам» у собеседника
    created_at = Column(DateTime, default=datetime.utcnow)
    answered_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    alive_at = Column(DateTime, default=datetime.utcnow)  # последний сигнал «я ещё на связи»


class CallSignal(Base):
    """Сигнал звонка для одного получателя: звонок, ответ, сетевые адреса, завершение."""
    __tablename__ = "v3_call_signals"
    id = Column(Integer, primary_key=True)
    call_id = Column(Integer, index=True)
    to_id = Column(Integer, index=True)
    kind = Column(String(12), default="")
    data = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)


# --- Проверка номера телефона (выборочно и при подозрении) --------------------------------------------------
class PhoneCheck(Base):
    __tablename__ = "v3_phone_checks"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, index=True)
    status = Column(String(10), default="pending")  # pending, verified, skipped
    reason = Column(String(80), default="")
    phone = Column(String(16), default="", index=True)
    method = Column(String(6), default="")  # max — номер подтверждён в боте MAX
    code_hash = Column(String(64), default="")  # хэш одноразовой ссылки на бота
    tg_user = Column(String(24), default="", index=True)  # id в мессенджере того, кто поделился номером
    code_sent_at = Column(DateTime, nullable=True)
    attempts = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    done_at = Column(DateTime, nullable=True)


# --- Подтверждение входа на телефоне ----------------------------------------------------------------------
class LoginApproval(Base):
    __tablename__ = "v3_login_approvals"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    token_hash = Column(String(64), index=True)  # хэш секрета из cookie ожидающего устройства
    status = Column(String(10), default="pending")  # pending, approved, denied, used
    device = Column(String(120), default="")
    ip = Column(String(64), default="")
    next_url = Column(String(300), default="/")
    notif_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    decided_at = Column(DateTime, nullable=True)


# --- Игры в переписке: камень-ножницы-бумага, кости, четыре в ряд, виселица ------------------------------------
class ChatGame(Base):
    __tablename__ = "v3_chat_games"
    id = Column(Integer, primary_key=True)
    kind = Column(String(8), index=True)  # rps, dice, c4, hang
    a_id = Column(Integer, ForeignKey("users.id"), index=True)  # кто предложил игру
    b_id = Column(Integer, ForeignKey("users.id"), index=True)
    state = Column(Text, default="{}")
    turn = Column(Integer, nullable=True)  # чей ход (для пошаговых)
    winner = Column(Integer, nullable=True)  # id победителя; 0 — ничья
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


# --- Оплата: Искры и Nuvora+ (ЮKassa) ------------------------------------------------------------------------
class Payment(Base):
    __tablename__ = "v3_payments"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    kind = Column(String(8))  # plus, sparks
    amount = Column(Integer)  # ₽
    sparks = Column(Integer, default=0)
    status = Column(String(12), default="pending")  # pending, succeeded, canceled
    provider_id = Column(String(64), default="", index=True)
    applied = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)


# --- Каналы и сообщества ------------------------------------------------------------------------------------------
class Community(Base):
    """Канал — пишут только админы, остальные читают. Сообщество — писать могут участники (если открыта стена)."""
    __tablename__ = "v3_communities"
    id = Column(Integer, primary_key=True)
    slug = Column(String(40), unique=True, index=True)
    name = Column(String(80))
    kind = Column(String(10), default="community")  # channel, community
    description = Column(Text, default="")
    avatar = Column(String(300), default="")
    cover = Column(String(300), default="")
    owner_id = Column(Integer, ForeignKey("users.id"), index=True)
    is_official = Column(Boolean, default=False)
    open_wall = Column(Boolean, default=True)  # в сообществе участники могут публиковать
    created_at = Column(DateTime, default=datetime.utcnow)


class CommunityMember(Base):
    __tablename__ = "v3_community_members"
    __table_args__ = (UniqueConstraint("community_id", "user_id"),)
    id = Column(Integer, primary_key=True)
    community_id = Column(Integer, ForeignKey("v3_communities.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    role = Column(String(8), default="member")  # owner, admin, member
    joined_at = Column(DateTime, default=datetime.utcnow)
