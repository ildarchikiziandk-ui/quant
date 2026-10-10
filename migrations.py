"""Безопасные «добавляющие» миграции: создаёт недостающие таблицы и колонки
по описанию моделей. Работает и с PostgreSQL, и с SQLite. Ничего не удаляет."""
from sqlalchemy import inspect, text, Boolean, Integer, String, Text, DateTime

import config
import models
from database import Base, engine

ACHIEVEMENTS = [
    ("first_post", "Первый пост", "Опубликуй первый пост", "📝", 10),
    ("first_like", "Лайкни!", "Поставь первый лайк", "❤️", 5),
    ("first_follow", "Подписчик", "Подпишись на кого-нибудь", "👤", 5),
    ("popular", "Популярный", "Набери 10 подписчиков", "🌟", 50),
    ("very_popular", "Знаменитость", "Набери 100 подписчиков", "⭐", 200),
    ("active", "Активный", "Опубликуй 10 постов", "🔥", 30),
    ("prolific", "Плодовитый", "Опубликуй 50 постов", "💪", 100),
    ("social", "Общительный", "Напиши 20 комментариев", "💬", 30),
    ("liker", "Любитель лайков", "Поставь 50 лайков", "❤️", 20),
    ("streak_3", "Стрик 3 дня", "Заходи 3 дня подряд", "🔥", 30),
    ("streak_7", "Стрик 7 дней", "Заходи 7 дней подряд", "🏆", 100),
    ("streak_30", "Стрик 30 дней", "Заходи 30 дней подряд", "👑", 500),
    ("whale", "Кит", "Поставь 10 китов", "🐋", 30),
    ("photographer", "Фотограф", "Опубликуй 5 фото", "📷", 20),
    ("videographer", "Видеограф", "Загрузи первый рилс", "🎬", 50),
    ("rich", "Богач", "Набери 1000 очков", "💰", 100),
    ("storyteller", "Рассказчик", "Опубликуй 10 историй", "📸", 40),
    ("pollster", "Социолог", "Создай первый опрос", "📊", 15),
    ("night_owl", "Сова", "Опубликуй пост ночью (0–5 часов)", "🦉", 15),
    ("group_founder", "Основатель", "Создай группу", "👥", 20),
    ("secure", "Под защитой", "Включи двухфакторную защиту", "🔐", 50),
]

DAILY_TASKS = [
    ("daily_post", "Опубликуй пост", "Опубликуй хотя бы один пост сегодня", "📝", 20, "post", 1),
    ("daily_like", "Поставь лайки", "Поставь 3 лайка", "❤️", 10, "like", 3),
    ("daily_comment", "Прокомментируй", "Оставь комментарий", "💬", 15, "comment", 1),
    ("daily_follow", "Подпишись", "Подпишись на нового пользователя", "👤", 10, "follow", 1),
    ("daily_story", "История", "Опубликуй историю", "📸", 25, "story", 1),
    ("daily_login", "Ежедневный вход", "Просто зайди сюда", "✨", 5, "login", 1),
    ("daily_message", "Напиши сообщение", "Напиши кому-нибудь", "✉️", 10, "message", 1),
]


def _sql_type(column, dialect):
    t = column.type
    if isinstance(t, Boolean):
        return "BOOLEAN"
    if isinstance(t, Integer):
        return "INTEGER"
    if isinstance(t, DateTime):
        return "TIMESTAMP"
    if isinstance(t, Text):
        return "TEXT"
    if isinstance(t, String):
        return "VARCHAR"
    return t.compile(dialect=dialect)


def _sql_default(column):
    default = column.default
    if default is None or not default.is_scalar:
        return ""
    value = default.arg
    if isinstance(value, bool):
        return " DEFAULT " + ("TRUE" if value else "FALSE")
    if isinstance(value, (int, float)):
        return f" DEFAULT {value}"
    if isinstance(value, str):
        return " DEFAULT '" + value.replace("'", "''") + "'"
    return ""


def add_missing_columns():
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    added = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        cols = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in cols:
                continue
            ddl = f"ALTER TABLE {table.name} ADD COLUMN {column.name} {_sql_type(column, engine.dialect)}{_sql_default(column)}"
            try:
                with engine.begin() as conn:  # отдельная транзакция на каждую колонку
                    conn.execute(text(ddl))
                added.append(f"{table.name}.{column.name}")
            except Exception as e:
                print(f"[migrations] не удалось добавить {table.name}.{column.name}: {e}")
    return added


def seed(db):
    for code, name, desc, emoji, pts in ACHIEVEMENTS:
        if not db.query(models.Achievement).filter_by(code=code).first():
            db.add(models.Achievement(code=code, name=name, description=desc, emoji=emoji, points_reward=pts))
    for code, title, desc, emoji, pts, ttype, target in DAILY_TASKS:
        if not db.query(models.DailyTask).filter_by(code=code).first():
            db.add(models.DailyTask(code=code, title=title, description=desc, emoji=emoji, points=pts,
                                    task_type=ttype, target_count=target))
    if config.OWNER_USERNAME:
        owner = db.query(models.User).filter_by(username=config.OWNER_USERNAME).first()
        if owner and not owner.is_owner:
            owner.is_owner = True
    db.commit()


def run():
    Base.metadata.create_all(bind=engine)
    try:
        added = add_missing_columns()
        if added:
            print(f"[migrations] добавлены колонки: {', '.join(added)}")
    except Exception as e:  # миграция не должна валить запуск
        print(f"[migrations] warning: {e}")
    from database import SessionLocal
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
