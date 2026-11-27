"""Phase 1.3.8.4 device retry idempotency, dry-run preflight, exit codes."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from core.device_pins import DEVICE_PRIVILEGE_INACTIVE, DEVICE_PRIVILEGE_NORMAL
from database import Base
from models import DeviceCommand, Member, MembershipPlan, MembershipSubscription, PushDevice
from rehearsal_lifecycle_execution.constants import REHEARSAL_DB_HOST
from rehearsal_lifecycle_execution.device_command_dedup import (
    has_equivalent_pending_access,
    load_pending_userinfo_access,
    parse_userinfo_access,
)
from rehearsal_lifecycle_execution.device_sync import run_device_access_sync_idempotent
from rehearsal_lifecycle_execution.errors import DeviceSyncError, PreflightError
from rehearsal_lifecycle_execution.runner import (
    EXIT_DEVICE_SYNC_FAILED,
    EXIT_DEVICE_SYNC_SKIPPED,
    run_dry_run,
    run_execute,
)
from services.push_device_service import UserSyncCommand

_DEVICE_TABLES = [
    Member.__table__,
    MembershipPlan.__table__,
    MembershipSubscription.__table__,
    PushDevice.__table__,
    DeviceCommand.__table__,
]


@pytest.fixture()
def device_db() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=_DEVICE_TABLES)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _seed_active_member(device_db: Session) -> Member:
    plan = MembershipPlan(
        name="P",
        family_name="P",
        duration_months=1,
        duration_label="1M",
        duration_days=30,
        base_price=1,
        tax_percent=5,
        total_price=1,
        price=1,
        is_active=True,
    )
    member = Member(
        full_name="Sync Member",
        mobile_number="9000000001",
        joined_at=date.today(),
        status="active",
    )
    device = PushDevice(serial_number="DEV-A", is_active=True)
    device_db.add_all([plan, member, device])
    device_db.flush()
    sub = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=date.today(),
        end_date=date(2099, 1, 1),
        base_price=1,
        tax_percent=5,
        tax_amount=0,
        total_amount=1,
        payment_status="paid",
        status="active",
    )
    device_db.add(sub)
    device_db.commit()
    device_db.refresh(member)
    return member


def test_parse_userinfo_access():
    cmd = UserSyncCommand.build_update_userinfo_command(
        command_id=1,
        pin="42",
        name="N",
        privilege=0,
    )
    assert parse_userinfo_access(cmd) == (42, 0)


def test_first_run_queues_second_run_deduplicates(device_db: Session, monkeypatch):
    member = _seed_active_member(device_db)
    monkeypatch.setattr(
        "rehearsal_lifecycle_execution.device_readiness.settings.device_push_enabled",
        True,
    )

    report1 = run_device_access_sync_idempotent(device_db, member_ids=(member.id,))
    assert report1.commands_newly_queued == 1
    assert report1.commands_satisfied_by_existing == 0

    report2 = run_device_access_sync_idempotent(device_db, member_ids=(member.id,))
    assert report2.commands_newly_queued == 0
    assert report2.commands_satisfied_by_existing == 1
    assert report2.command_strings == []


def test_existing_pending_not_duplicated(device_db: Session, monkeypatch):
    member = _seed_active_member(device_db)
    cmd = UserSyncCommand.build_update_userinfo_command(
        command_id=99,
        pin=str(member.id),
        name=member.full_name,
        privilege=DEVICE_PRIVILEGE_NORMAL,
    )
    device_db.add(
        DeviceCommand(
            command_id="existing-99",
            device_serial="DEV-A",
            command=cmd,
            status="pending",
        )
    )
    device_db.commit()
    monkeypatch.setattr(
        "rehearsal_lifecycle_execution.device_readiness.settings.device_push_enabled",
        True,
    )

    report = run_device_access_sync_idempotent(device_db, member_ids=(member.id,))
    assert report.commands_newly_queued == 0
    assert report.commands_satisfied_by_existing == 1


def test_changed_access_with_conflicting_pending_fails_closed(device_db: Session, monkeypatch):
    member = _seed_active_member(device_db)
    old = UserSyncCommand.build_update_userinfo_command(
        command_id=1,
        pin=str(member.id),
        name=member.full_name,
        privilege=DEVICE_PRIVILEGE_NORMAL,
    )
    device_db.add(
        DeviceCommand(
            command_id="old-pri0",
            device_serial="DEV-A",
            command=old,
            status="pending",
        )
    )
    device_db.commit()
    monkeypatch.setattr(
        "rehearsal_lifecycle_execution.device_readiness.settings.device_push_enabled",
        True,
    )
    with patch(
        "rehearsal_lifecycle_execution.device_sync.SubscriptionRepository.member_has_active_membership",
        return_value=False,
    ):
        with pytest.raises(DeviceSyncError, match="conflict"):
            run_device_access_sync_idempotent(device_db, member_ids=(member.id,))


def test_changed_access_after_completed_older_pri_allows_new_queue(device_db: Session, monkeypatch):
    member = _seed_active_member(device_db)
    old = UserSyncCommand.build_update_userinfo_command(
        command_id=1,
        pin=str(member.id),
        name=member.full_name,
        privilege=DEVICE_PRIVILEGE_NORMAL,
    )
    device_db.add(
        DeviceCommand(
            command_id="old-pri0",
            device_serial="DEV-A",
            command=old,
            status="completed",
        )
    )
    device_db.commit()
    monkeypatch.setattr(
        "rehearsal_lifecycle_execution.device_readiness.settings.device_push_enabled",
        True,
    )
    with patch(
        "rehearsal_lifecycle_execution.device_sync.SubscriptionRepository.member_has_active_membership",
        return_value=False,
    ):
        report = run_device_access_sync_idempotent(device_db, member_ids=(member.id,))
    assert report.commands_newly_queued == 1
    assert "Pri=1" in report.command_strings[0]


def test_unrelated_pending_preserved(device_db: Session, monkeypatch):
    member = _seed_active_member(device_db)
    device_db.add(
        DeviceCommand(
            command_id="trainer-cmd",
            device_serial="DEV-A",
            command="C:1:DATA UPDATE USERINFO PIN=50001\tName=T\tPri=0\tPasswd=",
            status="pending",
        )
    )
    device_db.commit()
    before = [r.id for r in device_db.query(DeviceCommand).all()]
    monkeypatch.setattr(
        "rehearsal_lifecycle_execution.device_readiness.settings.device_push_enabled",
        True,
    )
    run_device_access_sync_idempotent(device_db, member_ids=(member.id,))
    after = [r.id for r in device_db.query(DeviceCommand).all()]
    assert before[0] in after


def test_device_sync_only_skip_returns_4_not_0(monkeypatch):
    validated = f"postgresql://u:p@{REHEARSAL_DB_HOST}/db"
    skip_report = MagicMock(
        device_sync_skipped=True,
        commands_newly_queued=0,
        commands_satisfied_by_existing=0,
        eligible_device_serials=[],
        command_strings=[],
    )
    with patch("rehearsal_lifecycle_execution.runner.rehearsal_run_lock") as _rl:
        _rl.return_value.__enter__ = lambda s: None
        _rl.return_value.__exit__ = lambda s, *a: None
        with patch("rehearsal_lifecycle_execution.runner.resolve_database_url", return_value=validated):
            with patch("rehearsal_lifecycle_execution.runner.assert_engine_uses_validated_url"):
                with patch("rehearsal_lifecycle_execution.runner.create_engine_for_url"):
                    with patch("rehearsal_lifecycle_execution.runner.sessionmaker") as sm:
                        sm.return_value = MagicMock()
                        with patch(
                            "rehearsal_lifecycle_execution.runner.run_device_access_sync_idempotent",
                            return_value=skip_report,
                        ):
                            code = run_execute(
                                device_sync_only=True,
                                allow_zero_push_devices=True,
                            )
    assert code == EXIT_DEVICE_SYNC_SKIPPED


def test_device_sync_only_failure_returns_3(monkeypatch):
    validated = f"postgresql://u:p@{REHEARSAL_DB_HOST}/db"
    with patch("rehearsal_lifecycle_execution.runner.rehearsal_run_lock") as _rl:
        _rl.return_value.__enter__ = lambda s: None
        _rl.return_value.__exit__ = lambda s, *a: None
        with patch("rehearsal_lifecycle_execution.runner.resolve_database_url", return_value=validated):
            with patch("rehearsal_lifecycle_execution.runner.assert_engine_uses_validated_url"):
                with patch("rehearsal_lifecycle_execution.runner.create_engine_for_url"):
                    with patch("rehearsal_lifecycle_execution.runner.sessionmaker") as sm:
                        sm.return_value = MagicMock()
                        with patch(
                            "rehearsal_lifecycle_execution.runner.run_device_access_sync_idempotent",
                            side_effect=DeviceSyncError("boom"),
                        ):
                            code = run_execute(device_sync_only=True)
    assert code == EXIT_DEVICE_SYNC_FAILED


def test_dry_run_preflight_failure_nonzero():
    validated = f"postgresql://u:p@{REHEARSAL_DB_HOST}/db"
    with patch("rehearsal_lifecycle_execution.runner.resolve_database_url", return_value=validated):
        with patch("rehearsal_lifecycle_execution.runner.create_engine_for_url"):
            with patch("rehearsal_lifecycle_execution.runner.assert_engine_uses_validated_url"):
                with patch(
                    "rehearsal_lifecycle_execution.runner.build_dry_run_plan",
                    return_value=MagicMock(snapshot_ok=True, remaining_days_sub_92=7),
                ):
                    with patch(
                        "rehearsal_lifecycle_execution.runner.read_alembic_version",
                        return_value="n9o0p1q2r3s4",
                    ):
                        with patch(
                            "rehearsal_lifecycle_execution.runner.run_preflight_checks",
                            side_effect=PreflightError("check 3 failed"),
                        ):
                            code = run_dry_run()
    assert code == 2


def test_dry_run_n9a_notes_pre_n9b_inconclusive(capsys):
    validated = f"postgresql://u:p@{REHEARSAL_DB_HOST}/db"
    with patch("rehearsal_lifecycle_execution.runner.resolve_database_url", return_value=validated):
        with patch("rehearsal_lifecycle_execution.runner.create_engine_for_url"):
            with patch("rehearsal_lifecycle_execution.runner.assert_engine_uses_validated_url"):
                with patch(
                    "rehearsal_lifecycle_execution.runner.build_dry_run_plan",
                    return_value=MagicMock(snapshot_ok=True, remaining_days_sub_92=7),
                ):
                    with patch(
                        "rehearsal_lifecycle_execution.runner.read_alembic_version",
                        return_value="n9o0p1q2r3s4",
                    ):
                        with patch(
                            "rehearsal_lifecycle_execution.runner.run_preflight_checks",
                            return_value=MagicMock(as_dict=lambda: {"ok": True}),
                        ):
                            code = run_dry_run()
    err = capsys.readouterr().err
    assert "INCONCLUSIVE" in err
    assert code == 0


def test_dry_run_missing_lifecycle_columns_fails():
    validated = f"postgresql://u:p@{REHEARSAL_DB_HOST}/db"
    with patch("rehearsal_lifecycle_execution.runner.resolve_database_url", return_value=validated):
        with patch("rehearsal_lifecycle_execution.runner.create_engine_for_url"):
            with patch("rehearsal_lifecycle_execution.runner.assert_engine_uses_validated_url"):
                with patch(
                    "rehearsal_lifecycle_execution.runner.build_dry_run_plan",
                    return_value=MagicMock(snapshot_ok=True, remaining_days_sub_92=7),
                ):
                    with patch(
                        "rehearsal_lifecycle_execution.runner.read_alembic_version",
                        return_value="n9o0p1q2r3s4",
                    ):
                        with patch(
                            "rehearsal_lifecycle_execution.runner.run_preflight_checks",
                            side_effect=PreflightError("Lifecycle columns missing"),
                        ):
                            code = run_dry_run()
    assert code == 2


def test_dry_run_clean_at_n9b_runs_pre_n9b():
    validated = f"postgresql://u:p@{REHEARSAL_DB_HOST}/db"
    with patch("rehearsal_lifecycle_execution.runner.resolve_database_url", return_value=validated):
        with patch("rehearsal_lifecycle_execution.runner.create_engine_for_url"):
            with patch("rehearsal_lifecycle_execution.runner.assert_engine_uses_validated_url"):
                with patch(
                    "rehearsal_lifecycle_execution.runner.build_dry_run_plan",
                    return_value=MagicMock(snapshot_ok=True, remaining_days_sub_92=7),
                ):
                    with patch(
                        "rehearsal_lifecycle_execution.runner.read_alembic_version",
                        return_value="o0p1q2r3s4t5",
                    ):
                        mock_pf = MagicMock(as_dict=lambda: {})
                        with patch(
                            "rehearsal_lifecycle_execution.runner.run_preflight_checks",
                            return_value=mock_pf,
                        ) as pf:
                            code = run_dry_run()
                            assert pf.call_count == 2
    assert code == 0


def test_load_pending_userinfo_access_sqlite(device_db: Session):
    member = _seed_active_member(device_db)
    cmd = UserSyncCommand.build_update_userinfo_command(
        1, str(member.id), member.full_name, DEVICE_PRIVILEGE_NORMAL
    )
    device_db.add(
        DeviceCommand(
            command_id="x",
            device_serial="DEV-A",
            command=cmd,
            status="pending",
        )
    )
    device_db.commit()
    rows = load_pending_userinfo_access(device_db, device_serials=["DEV-A"], member_ids=(member.id,))
    assert len(rows) == 1
    assert has_equivalent_pending_access(
        rows,
        device_serial="DEV-A",
        member_id=member.id,
        required_privilege=DEVICE_PRIVILEGE_NORMAL,
    )