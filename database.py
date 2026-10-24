from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

import config

SQLALCHEMY_DATABASE_URL = config.DATABASE_URL
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

_kwargs = {"pool_pre_ping": True}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    _kwargs = {"connect_args": {"check_same_thread": False}}

engine = create_engine(SQLALCHEMY_DATABASE_URL, **_kwargs)

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _sqlite_tuning(dbapi_conn, _record):
        """WAL: чтение не ждёт записи (много людей одновременно); остальное — меньше обращений к диску."""
        cur = dbapi_conn.cursor()
        for pragma in ("journal_mode=WAL", "synchronous=NORMAL", "temp_store=MEMORY", "cache_size=-20000", "busy_timeout=5000"):
            try:
                cur.execute(f"PRAGMA {pragma}")
            except Exception:  # noqa: BLE001  например, база только для чтения
                pass
        cur.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
