import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TEST")
os.environ.setdefault("TELEGRAM_CHAT_ID", "1000")
os.environ.setdefault("DATABASE_URL", "postgresql://user:password@localhost/devinbot")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import Base

# The models use the PostgreSQL UUID type; render it as CHAR(32) for SQLite test DBs.
SQLiteTypeCompiler.visit_UUID = lambda self, type_, **kw: "CHAR(32)"


@pytest.fixture
def db_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
