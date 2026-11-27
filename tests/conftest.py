"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import Invoice, Member, MembershipPlan, MembershipSubscription

_SUBSCRIPTION_TABLES = [
    Member.__table__,
    MembershipPlan.__table__,
    MembershipSubscription.__table__,
    Invoice.__table__,
]


@pytest.fixture()
def db() -> Session:
    """In-memory SQLite DB with only tables needed for membership/subscription tests."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=_SUBSCRIPTION_TABLES)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()