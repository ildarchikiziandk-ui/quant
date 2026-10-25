"""База школы: пользователи (учитель и ученики), предметы, расписание, оценки, поведение, ДЗ, переписка."""
from datetime import datetime

from sqlalchemy import (Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
                        create_engine, event)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from . import config

if config.DATABASE_URL.startswith("sqlite:///"):
    import os
    os.makedirs(os.path.dirname(config.DATABASE_URL[len("sqlite:///"):]) or ".", exist_ok=True)
engine = create_engine(config.DATABASE_URL, connect_args={"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {})
if config.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _pragma(conn, _):
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    role = Column(String(8), default="student")  # teacher, student
    login = Column(String(40), unique=True, index=True)
    pw_hash = Column(String(100), default="")
    name = Column(String(80), default="")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, nullable=True)

    @property
    def is_teacher(self):
        return self.role == "teacher"

    @property
    def first_name(self):
        return (self.name or self.login).split(" ")[0]


class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash = Column(String(64), unique=True, index=True)
    device = Column(String(120), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)


class Subject(Base):
    __tablename__ = "subjects"
    id = Column(Integer, primary_key=True)
    name = Column(String(60))
    color = Column(String(9), default="#1f6fb8")
    teacher_note = Column(String(200), default="")  # учебник, кабинет — что угодно
    position = Column(Integer, default=0)
    archived = Column(Boolean, default=False)


class Lesson(Base):
    """Урок в недельном расписании: день недели (0 — понедельник) и номер урока."""
    __tablename__ = "lessons"
    __table_args__ = (UniqueConstraint("weekday", "num"),)
    id = Column(Integer, primary_key=True)
    weekday = Column(Integer)
    num = Column(Integer)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"))
    room = Column(String(30), default="")
    subject = relationship("Subject")


class Grade(Base):
    __tablename__ = "grades"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    value = Column(Integer)  # 1–5
    kind = Column(String(20), default="")  # «», «контрольная», «самостоятельная», «домашняя», «устно»
    comment = Column(String(300), default="")
    date = Column(Date)
    created_at = Column(DateTime, default=datetime.utcnow)
    seen = Column(Boolean, default=False)
    subject = relationship("Subject")


class Behavior(Base):
    __tablename__ = "behavior"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    value = Column(Integer)  # 1–5
    comment = Column(String(300), default="")
    date = Column(Date)
    created_at = Column(DateTime, default=datetime.utcnow)
    seen = Column(Boolean, default=False)


class Homework(Base):
    __tablename__ = "homework"
    id = Column(Integer, primary_key=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)  # None — всем ученикам
    due = Column(Date, index=True)
    text = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    subject = relationship("Subject")


class HomeworkDone(Base):
    __tablename__ = "homework_done"
    __table_args__ = (UniqueConstraint("homework_id", "student_id"),)
    id = Column(Integer, primary_key=True)
    homework_id = Column(Integer, ForeignKey("homework.id", ondelete="CASCADE"), index=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    done_at = Column(DateTime, default=datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)  # переписка учителя с этим учеником
    from_teacher = Column(Boolean, default=False)
    text = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    read = Column(Boolean, default=False)


class Setting(Base):
    __tablename__ = "settings"
    key = Column(String(40), primary_key=True)
    value = Column(Text, default="")


def init():
    Base.metadata.create_all(bind=engine)
