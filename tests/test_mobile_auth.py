"""Unit tests for mobile auth helpers and PIN/OTP happy path (in-memory SQLite)."""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import Member, User
from services.mobile_auth_service import (
    MobileAuthService,
    MobileAuthValidationError,
)


@pytest.fixture()
def db() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_normalize_mobile_strips_country_code():
    assert MobileAuthService.normalize_mobile("+91 98765 43210") == "9876543210"
    assert MobileAuthService.normalize_mobile("9876543210") == "9876543210"


def test_member_activate_set_pin_and_login(db: Session, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    from core.config import settings

    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "jwt_secret_key", "test-secret-key-for-mobile-auth")

    member = Member(
        full_name="Test Member",
        mobile_number="9876543210",
        joined_at=date.today(),
        status="active",
    )
    db.add(member)
    db.commit()
    db.refresh(member)

    service = MobileAuthService(db)
    otp_response = service.request_otp(mobile_number="9876543210", purpose="activate", role="MEMBER")
    assert otp_response.debug_otp
    assert otp_response.role == "MEMBER"

    verified = service.verify_otp(
        mobile_number="9876543210",
        purpose="activate",
        otp=otp_response.debug_otp,
        role="MEMBER",
    )
    assert verified.otp_session_token

    login = service.set_pin(otp_session_token=verified.otp_session_token, pin="1234")
    assert login.token
    assert login.user.role == "MEMBER"
    assert login.user.member_id == member.id

    db.refresh(member)
    assert member.user_id is not None

    again = service.login_with_pin(mobile_number="9876543210", pin="1234", role="MEMBER")
    assert again.user.member_id == member.id

    with pytest.raises(MobileAuthValidationError):
        service.login_with_pin(mobile_number="9876543210", pin="9999", role="MEMBER")
