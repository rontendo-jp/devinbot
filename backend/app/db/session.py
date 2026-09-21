from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings
from app.models.database import Base

# Create database engine
engine = create_engine(settings.database_url, pool_pre_ping=True)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """
    Dependency function to get database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize database tables.
    """
    Base.metadata.create_all(bind=engine)
    # create_all does not alter existing tables; add columns introduced after the initial schema.
    with engine.begin() as conn:
        for column, ddl in (
            ("devin_status", "VARCHAR(50)"),
            ("devin_status_detail", "VARCHAR(100)"),
        ):
            conn.execute(text(f"ALTER TABLE sessions ADD COLUMN IF NOT EXISTS {column} {ddl}"))