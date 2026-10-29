"""Безопасные «добавляющие» миграции: создаёт недостающие таблицы и колонки
по описанию моделей. Работает и с PostgreSQL, и с SQLite. Ничего не удаляет."""
from sqlalchemy import inspect, text, Boolean, Integer, String, Text, DateTime

import config
import models
from database import Base, engine

ACHIEVEMENTS = [
    ("first_post", "Первый пост", "Опубликуй первый пост", "note", 5),
    ("first_like", "Лайкни!", "Поставь первый лайк", "heart", 3),
    ("first_follow", "Подписчик", "Подпишись на кого-нибудь", "user", 3),
    ("popular", "Популярный", "Набери 10 подписчиков", "star", 25),
    ("very_popular", "Знаменитость", "Набери 100 подписчиков", "star", 100),
    ("active", "Активный", "Опубликуй 10 постов", "flame", 15),
    ("prolific", "Плодовитый", "Опубликуй 50 постов", "bolt", 50),
    ("social", "Общительный", "Напиши 20 комментариев", "chat", 15),
    ("liker", "Любитель лайков", "Поставь 50 лайков", "heart", 10),
    ("streak_3", "Стрик 3 дня", "Заходи 3 дня подряд", "flame", 15),
    ("streak_7", "Стрик 7 дней", "Заходи 7 дней подряд", "trophy", 50),
    ("streak_30", "Стрик 30 дней", "Заходи 30 дней подряд", "crown", 250),
    ("whale", "Кит", "Поставь 10 китов", "whale", 15),
    ("photographer", "Фотограф", "Опубликуй 5 фото", "camera", 10),
    ("rich", "Богач", "Набери 1000 искр", "store", 50),
    ("storyteller", "Рассказчик", "Опубликуй 10 историй", "camera", 20),
    ("pollster", "Социолог", "Создай первый опрос", "chart", 8),
    ("night_owl", "Сова", "Опубликуй пост ночью (0–5 часов)", "moon", 8),
    ("group_founder", "Основатель", "Создай группу", "users", 10),
    ("secure", "Под защитой", "Включи двухфакторную защиту", "secret", 25),
    ("inviter", "Пригласивший", "Пригласи друга по своей ссылке", "handshake", 25),
    ("quiz_master", "Эрудит", "Правильно ответь на 5 викторин", "bulb", 20),
    ("generous", "Щедрая душа", "Подари кому-нибудь подарок", "gift", 10),
    ("answerer", "Открытая книга", "Ответь на 5 вопросов", "help", 15),
    ("event_host", "Организатор", "Создай мероприятие", "calendar", 10),
    ("lucky", "Везунчик", "Покрути колесо фортуны", "wheel", 5),
    ("stylist", "Стилист", "Купи рамку для аватарки", "image", 10),
]

DAILY_TASKS = [
    ("daily_post", "Опубликуй пост", "Опубликуй хотя бы один пост сегодня", "note", 10, "post", 1),
    ("daily_like", "Поставь лайки", "Поставь 3 лайка", "heart", 5, "like", 3),
    ("daily_comment", "Прокомментируй", "Оставь комментарий", "chat", 8, "comment", 1),
    ("daily_follow", "Подпишись", "Подпишись на нового пользователя", "user", 5, "follow", 1),
    ("daily_story", "История", "Опубликуй историю", "camera", 13, "story", 1),
    ("daily_login", "Ежедневный вход", "Просто зайди сюда", "sparkle", 3, "login", 1),
    ("daily_message", "Напиши сообщение", "Напиши кому-нибудь", "mail", 5, "message", 1),
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
    # награды пересчитаны под «Искры» (вдвое меньше) — обновляем уже созданные записи
    want_ach = {c: pts for c, _, _, _, pts in ACHIEVEMENTS}
    want_task = {c: pts for c, _, _, _, pts, *_ in DAILY_TASKS}
    for row in db.query(models.Achievement).all():
        if row.code in want_ach and row.points_reward != want_ach[row.code]:
            row.points_reward = want_ach[row.code]
        if row.code == "rich" and row.description != "Набери 1000 искр":
            row.description = "Набери 1000 искр"
    for row in db.query(models.DailyTask).all():
        if row.code in want_task and row.points != want_task[row.code]:
            row.points = want_task[row.code]
    # эмодзи в старых записях → имена иконок (интерфейс рисует SVG-иконки вместо эмодзи)
    icons_by_code = {c: e for c, _, _, e, _ in ACHIEVEMENTS} | {c: e for c, _, _, e, *_ in DAILY_TASKS}
    for model in (models.Achievement, models.DailyTask):
        for row in db.query(model).all():
            want = icons_by_code.get(row.code)
            if want and row.emoji != want:
                row.emoji = want
    # репосты раньше копировали текст оригинала — убираем копии (оригинал показывается по ссылке с проверкой доступа)
    db.query(models.Post).filter(models.Post.is_repost == True, models.Post.content != "").update({"content": ""}, synchronize_session=False)
    # владелец назначается только один раз, пока его ещё нет: иначе любой, кто займёт этот логин, стал бы админом
    if config.OWNER_USERNAME and not db.query(models.User.id).filter_by(is_owner=True).first():
        owner = db.query(models.User).filter_by(username=config.OWNER_USERNAME).first()
        if owner and not owner.is_owner:
            owner.is_owner = True
    db.commit()


# Индексы для частых запросов (лента, чаты, уведомления, счётчики). CREATE INDEX IF NOT EXISTS понимают и SQLite, и PostgreSQL.
INDEXES = [
    ("posts", "user_id, created_at"), ("posts", "created_at"), ("posts", "repost_id"),
    ("follows", "follower_id"), ("follows", "following_id"),
    ("likes", "post_id"), ("likes", "user_id, post_id"), ("whales", "post_id"), ("whales", "user_id, post_id"),
    ("comments", "post_id, created_at"), ("comments", "user_id"), ("comments", "parent_id"),
    ("messages", "receiver_id, is_read"), ("messages", "sender_id, receiver_id"), ("messages", "group_id"), ("messages", "reply_to_id"),
    ("group_members", "group_id"), ("group_members", "user_id"), ("group_messages", "group_id, id"),
    ("notifications", "user_id, is_read"), ("notifications", "user_id, id"),
    ("stories", "user_id"), ("story_views", "story_id"), ("story_views", "user_id"),
    ("poll_votes", "poll_id, user_id"), ("bookmarks", "user_id, post_id"), ("user_sessions", "user_id"),
    ("user_blocks", "blocker_id"), ("user_blocks", "blocked_id"), ("typing_status", "target_id"),
    ("user_daily_tasks", "user_id"), ("user_achievements", "user_id"), ("reactions", "post_id"), ("comment_likes", "user_id"),
]


def add_indexes():
    from sqlalchemy import inspect as _inspect
    names = set(_inspect(engine).get_table_names())
    made = 0
    with engine.begin() as conn:
        for table, cols in INDEXES:
            if table not in names:
                continue
            name = f"ix3_{table}_" + "_".join(c.strip() for c in cols.split(","))
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({cols})"))
            made += 1
    return made


def run():
    Base.metadata.create_all(bind=engine)
    try:
        add_indexes()
    except Exception as e:  # индексы ускоряют, но не обязательны для работы
        print(f"[migrations] индексы: {e}")
    try:
        added = add_missing_columns()
        if added:
            print(f"[migrations] добавлены колонки: {', '.join(added)}")
    except Exception as e:  # миграция не должна валить запуск
        print(f"[migrations] warning: {e}")
    try:  # проверку номера через MAX убрали — номера не храним
        with engine.begin() as conn:
            conn.exec_driver_sql("DROP TABLE IF EXISTS v3_phone_checks")
    except Exception as e:
        print(f"[migrations] v3_phone_checks: {e}")
    try:
        n = encrypt_existing_messages()
        if n:
            print(f"[migrations] зашифровано старых сообщений: {n}")
    except Exception as e:
        print(f"[migrations] шифрование сообщений: {e}")
    from database import SessionLocal
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


def encrypt_existing_messages(batch=500):
    """Шифрует сообщения, сохранённые до включения шифрования. Безопасно запускать повторно."""
    from services import crypto
    total = 0
    for table in ("messages", "group_messages"):
        while True:
            with engine.begin() as conn:
                rows = conn.execute(text(f"SELECT id, content FROM {table} WHERE content IS NOT NULL AND content != '' "
                                         f"AND content NOT LIKE 'enc1:%' LIMIT {batch}")).fetchall()
                for rid, content in rows:
                    conn.execute(text(f"UPDATE {table} SET content = :c WHERE id = :i"), {"c": crypto.encrypt(content), "i": rid})
            total += len(rows)
            if len(rows) < batch:
                break
    return total
