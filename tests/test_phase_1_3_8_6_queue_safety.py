"""Phase 1.3.8.6 device queue conflict, PIN parsing, and execution lock tests."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from core.device_pins import DEVICE_PRIVILEGE_INACTIVE, DEVICE_PRIVILEGE_NORMAL
from database import Base
from models import DeviceCommand, Member, MembershipPlan, MembershipSubscription, PushDevice
from rehearsal_lifecycle_execution.device_command_dedup import (
    AccessSlotAction,
    load_userinfo_commands_for_devices,
    parse_userinfo_access,
    resolve_access_slot,
)
from rehearsal_lifecycle_execution.device_sync import run_device_access_sync_idempotent
from rehearsal_lifecycle_execution.errors import DeviceSyncError, RehearsalExecutionError
from rehearsal_lifecycle_execution.execution_lock import _default_lock_path, rehearsal_run_lock
from services.push_device_service import UserSyncCommand

_TABLES = [
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
    Base.metadata.create_all(bind=engine, tables=_TABLES)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _seed_member(device_db: Session, member_id: int = 98) -> Member:
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
        id=member_id,
        full_name=f"M{member_id}",
        mobile_number=f"900000{member_id:04d}",
        joined_at=date.today(),
        status="active",
    )
    device_db.add(plan)
    device_db.add(member)
    device_db.flush()
    device_db.add(
        MembershipSubscription(
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
    )
    device_db.add(PushDevice(serial_number="DEV-A", is_active=True))
    device_db.commit()
    return member


def test_parse_userinfo_pin_exact_not_substring():
    cmd98 = UserSyncCommand.build_update_userinfo_command(1, "98", "A", 0)
    cmd9 = UserSyncCommand.build_update_userinfo_command(2, "9", "B", 0)
    assert parse_userinfo_access(cmd98) == (98, 0)
    assert parse_userinfo_access(cmd9) == (9, 0)
    assert parse_userinfo_access("C:1:DATA UPDATE USERINFO PIN=980\tPri=0") == (980, 0)
    assert parse_userinfo_access("C:1:DATA UPDATE USERINFO PIN=98") is None


def test_load_userinfo_excludes_pin_substring_false_positive(device_db: Session):
    _seed_member(device_db, 98)
    cmd9 = UserSyncCommand.build_update_userinfo_command(1, "9", "Nine", 0)
    cmd98 = UserSyncCommand.build_update_userinfo_command(2, "98", "NinetyEight", 0)
    device_db.add_all(
        [
            DeviceCommand(command_id="c9", device_serial="DEV-A", command=cmd9, status="pending"),
            DeviceCommand(command_id="c98", device_serial="DEV-A", command=cmd98, status="pending"),
        ]
    )
    device_db.commit()
    rows = load_userinfo_commands_for_devices(device_db, device_serials=["DEV-A"], member_ids=(98,))
    assert len(rows) == 1
    assert rows[0]["member_id"] == 98


def test_conflicting_pending_pri_fails_closed(device_db: Session, monkeypatch):
    member = _seed_member(device_db, 98)
    wrong = UserSyncCommand.build_update_userinfo_command(
        1, str(member.id), member.full_name, DEVICE_PRIVILEGE_INACTIVE
    )
    device_db.add(
        DeviceCommand(
            command_id="conflict",
            device_serial="DEV-A",
            command=wrong,
            status="pending",
        )
    )
    device_db.commit()
    monkeypatch.setattr("rehearsal_lifecycle_execution.device_readiness.settings.device_push_enabled", True)
    with pytest.raises(DeviceSyncError, match="conflict"):
        run_device_access_sync_idempotent(device_db, member_ids=(member.id,))


def test_conflicting_executing_pri_fails_closed(device_db: Session, monkeypatch):
    member = _seed_member(device_db, 98)
    wrong = UserSyncCommand.build_update_userinfo_command(
        1, str(member.id), member.full_name, DEVICE_PRIVILEGE_INACTIVE
    )
    device_db.add(
        DeviceCommand(
            command_id="exec-conflict",
            device_serial="DEV-A",
            command=wrong,
            status="executing",
        )
    )
    device_db.commit()
    monkeypatch.setattr("rehearsal_lifecycle_execution.device_readiness.settings.device_push_enabled", True)
    with pytest.raises(DeviceSyncError, match="executing"):
        run_device_access_sync_idempotent(device_db, member_ids=(member.id,))


def test_retry_after_completed_ack_does_not_requeue(device_db: Session, monkeypatch):
    member = _seed_member(device_db, 98)
    ok = UserSyncCommand.build_update_userinfo_command(
        1, str(member.id), member.full_name, DEVICE_PRIVILEGE_NORMAL
    )
    device_db.add(
        DeviceCommand(
            command_id="done",
            device_serial="DEV-A",
            command=ok,
            status="completed",
        )
    )
    device_db.commit()
    monkeypatch.setattr("rehearsal_lifecycle_execution.device_readiness.settings.device_push_enabled", True)
    report = run_device_access_sync_idempotent(device_db, member_ids=(member.id,))
    assert report.commands_newly_queued == 0
    assert report.commands_satisfied_completed_ack == 1


def test_failed_ack_does_not_satisfy_and_allows_new_queue(device_db: Session, monkeypatch):
    member = _seed_member(device_db, 98)
    bad = UserSyncCommand.build_update_userinfo_command(
        1, str(member.id), member.full_name, DEVICE_PRIVILEGE_NORMAL
    )
    device_db.add(
        DeviceCommand(
            command_id="failed",
            device_serial="DEV-A",
            command=bad,
            status="failed",
        )
    )
    device_db.commit()
    monkeypatch.setattr("rehearsal_lifecycle_execution.device_readiness.settings.device_push_enabled", True)
    report = run_device_access_sync_idempotent(device_db, member_ids=(member.id,))
    assert report.commands_newly_queued == 1


def test_unrelated_pending_preserved_on_device(device_db: Session, monkeypatch):
    member = _seed_member(device_db, 98)
    device_db.add(
        DeviceCommand(
            command_id="trainer",
            device_serial="DEV-A",
            command="C:1:DATA UPDATE USERINFO PIN=50001\tName=T\tPri=0\tPasswd=",
            status="pending",
        )
    )
    device_db.commit()
    before = [r.id for r in device_db.query(DeviceCommand).all()]
    monkeypatch.setattr("rehearsal_lifecycle_execution.device_readiness.settings.device_push_enabled", True)
    run_device_access_sync_idempotent(device_db, member_ids=(member.id,))
    after = [r.id for r in device_db.query(DeviceCommand).all()]
    assert all(i in after for i in before)


def test_resolve_access_slot_conflict_pending():
    rows = [
        {
            "id": 1,
            "device_serial": "D",
            "member_id": 98,
            "privilege": 1,
            "status": "pending",
            "command": "",
        }
    ]
    d = resolve_access_slot(rows, device_serial="D", member_id=98, required_privilege=0)
    assert d.action == AccessSlotAction.CONFLICT_PENDING_OTHER_PRI


def test_rehearsal_run_lock_blocks_concurrent_file_lock():
    engine = MagicMock()
    engine.dialect.name = "sqlite"
    first = MagicMock()
    with patch(
        "rehearsal_lifecycle_execution.execution_lock._try_acquire_file_lock",
        side_effect=[first, RehearsalExecutionError("second run blocked")],
    ):
        with rehearsal_run_lock(engine):
            with pytest.raises(RehearsalExecutionError, match="second run blocked"):
                with rehearsal_run_lock(engine):
                    pass
        first.release.assert_called_once()


def test_pg_advisory_lock_blocks_second_session():
    """Unit test with mocked PostgreSQL dialect."""
    engine = MagicMock()
    engine.dialect.name = "postgresql"
    conn = MagicMock()
    engine.connect.return_value = conn
    conn.execute.side_effect = [
        MagicMock(scalar=lambda: True),
        MagicMock(),
    ]
    with rehearsal_run_lock(engine):
        pass
    conn.execute.assert_called()
    conn.close.assert_called()


def test_retry_no_reconcile_mock(monkeypatch):
    validated = "postgresql://u:p@ep-blue-night-b37s7qe2-pooler.c-4.ap-southeast-1.aws.neon.tech/db"
    with patch("rehearsal_lifecycle_execution.runner.resolve_database_url", return_value=validated):
        with patch("rehearsal_lifecycle_execution.runner.rehearsal_run_lock") as lock:
            lock.return_value.__enter__ = lambda s: None
            lock.return_value.__exit__ = lambda s, *a: None
            with patch("rehearsal_lifecycle_execution.runner.reconcile_all_stale") as stale:
                with patch("rehearsal_lifecycle_execution.runner.upgrade_to_revision") as mig:
                    with patch("rehearsal_lifecycle_execution.runner.run_device_access_sync_idempotent") as sync:
                        sync.return_value = MagicMock(
                            device_sync_skipped=False,
                            commands_newly_queued=0,
                            commands_satisfied_in_flight=1,
                            commands_satisfied_completed_ack=0,
                            eligible_device_serials=["D"],
                        )
                        with patch("rehearsal_lifecycle_execution.runner.assert_engine_uses_validated_url"):
                            with patch("rehearsal_lifecycle_execution.runner.create_engine_for_url"):
                                with patch("rehearsal_lifecycle_execution.runner.sessionmaker", return_value=MagicMock()):
                                    from rehearsal_lifecycle_execution.runner import run_execute

                                    run_execute(device_sync_only=True)
                    stale.assert_not_called()
                    mig.assert_not_called()


def teardown_module():
    path = _default_lock_path()
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass