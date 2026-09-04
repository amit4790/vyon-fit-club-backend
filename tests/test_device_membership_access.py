"""Tests for membership expiry → device access disable (Pri=1) / enable (Pri=0)."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from core.device_pins import DEVICE_PRIVILEGE_INACTIVE, DEVICE_PRIVILEGE_NORMAL
from database import Base
from models import Member, MembershipPlan, MembershipSubscription, PushDevice
from repositories.subscription_repository import SubscriptionRepository
from services.push_device_service import PushDeviceService, UserSyncCommand
from services.subscription_service import SubscriptionService


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


def _seed_member_and_plan(db: Session) -> tuple[Member, MembershipPlan]:
    member = Member(
        full_name="Test Member",
        mobile_number="9876543210",
        joined_at=date.today() - timedelta(days=30),
        status="active",
    )
    plan = MembershipPlan(
        name="Monthly",
        family_name="MONTHLY",
        variant_name="Standard",
        duration_months=1,
        duration_days=30,
        duration_label="1 Month",
        base_price=1000,
        tax_percent=18,
        total_price=1180,
        price=1180,
        is_active=True,
    )
    db.add_all([member, plan])
    db.commit()
    db.refresh(member)
    db.refresh(plan)
    return member, plan


class TestUserInfoPrivilegeCommands:
    def test_inactive_privilege_command(self):
        cmd = UserSyncCommand.build_update_userinfo_command(
            command_id=42,
            pin="15",
            name="Expired Member",
            privilege=DEVICE_PRIVILEGE_INACTIVE,
        )
        assert "Pri=1" in cmd
        assert cmd.startswith("C:42:DATA UPDATE USERINFO")

    def test_normal_privilege_command(self):
        cmd = UserSyncCommand.build_update_userinfo_command(
            command_id=7,
            pin="15",
            name="Active Member",
            privilege=DEVICE_PRIVILEGE_NORMAL,
        )
        assert "Pri=0" in cmd


class TestSetMemberAccessOnDevices:
    def test_queues_disable_command(self, db: Session):
        member, _plan = _seed_member_and_plan(db)
        db.add(
            PushDevice(
                serial_number="TBS2254700504",
                is_active=True,
            )
        )
        db.commit()

        commands = PushDeviceService(db).set_member_access_on_devices(
            member.id,
            member.full_name,
            enabled=False,
        )
        assert len(commands) == 1
        assert "Pri=1" in commands[0].command
        assert f"PIN={member.id}" in commands[0].command

    def test_queues_enable_command(self, db: Session):
        member, _plan = _seed_member_and_plan(db)
        db.add(PushDevice(serial_number="TBS2254700504", is_active=True))
        db.commit()

        commands = PushDeviceService(db).set_member_access_on_devices(
            member.id,
            member.full_name,
            enabled=True,
        )
        assert len(commands) == 1
        assert "Pri=0" in commands[0].command


class TestExpiredSubscriptionDeviceSync:
    def test_expiry_disables_when_no_other_active_plan(self, db: Session, monkeypatch):
        member, plan = _seed_member_and_plan(db)
        sub = MembershipSubscription(
            member_id=member.id,
            plan_id=plan.id,
            start_date=date.today() - timedelta(days=40),
            end_date=date.today() - timedelta(days=1),
            status="active",
            payment_status="paid",
            base_price=1000,
            tax_percent=18,
            tax_amount=180,
            total_amount=1180,
        )
        db.add(sub)
        db.commit()

        monkeypatch.setattr("services.subscription_service.settings.device_push_enabled", True)
        mock_push = MagicMock()
        with patch("services.push_device_service.PushDeviceService", return_value=mock_push):
            SubscriptionService(db).sync_expired_subscriptions()

        db.refresh(sub)
        assert sub.status == "expired"
        mock_push.set_member_access_on_devices.assert_called_once_with(
            member.id,
            member.full_name,
            enabled=False,
        )

    def test_expiry_keeps_access_when_another_active_plan_exists(self, db: Session, monkeypatch):
        member, plan = _seed_member_and_plan(db)
        expired = MembershipSubscription(
            member_id=member.id,
            plan_id=plan.id,
            start_date=date.today() - timedelta(days=60),
            end_date=date.today() - timedelta(days=1),
            status="active",
            payment_status="paid",
            base_price=1000,
            tax_percent=18,
            tax_amount=180,
            total_amount=1180,
        )
        still_active = MembershipSubscription(
            member_id=member.id,
            plan_id=plan.id,
            start_date=date.today() - timedelta(days=5),
            end_date=date.today() + timedelta(days=25),
            status="active",
            payment_status="paid",
            base_price=1000,
            tax_percent=18,
            tax_amount=180,
            total_amount=1180,
        )
        db.add_all([expired, still_active])
        db.commit()

        monkeypatch.setattr("services.subscription_service.settings.device_push_enabled", True)
        mock_push = MagicMock()
        with patch("services.push_device_service.PushDeviceService", return_value=mock_push):
            SubscriptionService(db).sync_expired_subscriptions()

        db.refresh(expired)
        db.refresh(still_active)
        assert expired.status == "expired"
        assert still_active.status == "active"
        mock_push.set_member_access_on_devices.assert_called_once_with(
            member.id,
            member.full_name,
            enabled=True,
        )

    def test_member_has_active_membership_helper(self, db: Session):
        member, plan = _seed_member_and_plan(db)
        repo = SubscriptionRepository(db)
        assert repo.member_has_active_membership(member.id, date.today()) is False

        db.add(
            MembershipSubscription(
                member_id=member.id,
                plan_id=plan.id,
                start_date=date.today(),
                end_date=date.today() + timedelta(days=10),
                status="active",
                payment_status="pending",
                base_price=1000,
                tax_percent=18,
                tax_amount=180,
                total_amount=1180,
            )
        )
        db.commit()
        assert repo.member_has_active_membership(member.id, date.today()) is True
