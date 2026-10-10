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
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
