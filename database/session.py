"""
Database session and SQLAlchemy base configuration.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from core.config import settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session for request-scoped usage."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
