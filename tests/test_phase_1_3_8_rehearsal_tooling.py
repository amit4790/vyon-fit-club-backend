"""Tests for Phase 1.3.8 rehearsal execution tooling (no Neon)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from core.membership_lifecycle import remaining_days_from_today
from models import Invoice, Member, MembershipPlan, MembershipSubscription
from rehearsal_lifecycle_execution.constants import REHEARSAL_DB_HOST, REVIEWED_SUBSCRIPTION_SNAPSHOT
from rehearsal_lifecycle_execution.device_inspect import assert_access_sync_commands
from rehearsal_lifecycle_execution.device_sync import run_device_access_sync_idempotent
from rehearsal_lifecycle_execution.errors import DatabaseSafetyError, DeviceSyncError, SnapshotMismatchError
from rehearsal_lifecycle_execution.migrations import MigrationStateError, planned_migration_steps, require_alembic_version
from rehearsal_lifecycle_execution.reconcile import (
    compute_pause_remaining_days,
    reconcile_member_98_pause,
    reconcile_stale_member,
)
from rehearsal_lifecycle_execution.safety import resolve_database_url, validate_database_hostname
from rehearsal_lifecycle_execution.snapshot import invoice_rows_unchanged, subscription_matches_snapshot


def test_exact_hostname_accepted():
    url = f"postgresql+psycopg://user:secret@{REHEARSAL_DB_HOST}/neondb?sslmode=require"
    validate_database_hostname(url)


def test_substring_hostname_rejected():
    almost = REHEARSAL_DB_HOST + ".evil.example"
    url = f"postgresql://user:pass@{almost}/db"
    with pytest.raises(DatabaseSafetyError, match="does not exactly match"):
        validate_database_hostname(url)


def test_database_url_prod_equals_active_rejected():
    url = f"postgresql://u:p@{REHEARSAL_DB_HOST}/db"
    env = {"DATABASE_URL": url, "DATABASE_URL_PROD": url}
    with pytest.raises(DatabaseSafetyError, match="DATABASE_URL_PROD equals"):
        resolve_database_url(env)


def test_remaining_days_zero_aborts():
    with pytest.raises(Exception):
        compute_pause_remaining_days(
            start_date=date(2026, 8, 4),
            end_date=date(2026, 12, 3),
            today=date(2026, 12, 4),
        )


def test_snapshot_mismatch_wrong_status():
    row = {
        "id": 92,
        "member_id": 98,
        "status": "expired",
        "payment_status": "paid",
        "start_date": date(2026, 8, 4),
        "end_date": date(2026, 12, 3),
    }
    with pytest.raises(SnapshotMismatchError, match="status"):
        subscription_matches_snapshot(row)


def test_unexpected_alembic_revision():
    with pytest.raises(MigrationStateError, match="Unsupported"):
        planned_migration_steps("unknown_revision_xyz")


def test_require_alembic_version_mismatch():
    engine = MagicMock()
    with patch(
        "rehearsal_lifecycle_execution.migrations.read_alembic_version",
        return_value="wrong",
    ):
        with pytest.raises(MigrationStateError, match="expected"):
            require_alembic_version("postgresql:///", "l7m8n9o0p1q2", context="test")


def test_reviewed_snapshot_sub_92_remaining_on_2026_11_27():
    snap = REVIEWED_SUBSCRIPTION_SNAPSHOT[92]
    assert (
        remaining_days_from_today(
            start_date=snap.start_date,
            end_date=snap.end_date,
            today=date(2026, 11, 27),
        )
        == 7
    )


def test_device_command_inspection_rejects_biophoto():
    with pytest.raises(DeviceSyncError, match="BIOPHOTO"):
        assert_access_sync_commands(["C:1:DATA UPDATE BIOPHOTO PIN=98"])


def test_device_command_inspection_accepts_userinfo_pri():
    pri = assert_access_sync_commands(["C:1:DATA UPDATE USERINFO PIN=98\tName=Test\tPri=0\tPasswd="])
    assert pri == [0]


def test_invoice_unchanged_guard():
    before = [{"id": 1, "amount": 100.0, "status": "paid"}]
    after = [{"id": 1, "amount": 99.0, "status": "paid"}]
    with pytest.raises(SnapshotMismatchError, match="amount"):
        invoice_rows_unchanged(before, after)


def _seed_basic_plan_member(db: Session):
    plan = MembershipPlan(
        name="VYON BASIC",
        family_name="VYON BASIC",
        duration_months=3,
        duration_label="3M",
        duration_days=90,
        base_price=1000,
        tax_percent=5,
        total_price=1050,
        price=1050,
        is_active=True,
    )
    member = Member(
        full_name="Test",
        mobile_number="9311111100",
        joined_at=date(2026, 1, 1),
        status="active",
    )
    db.add_all([plan, member])
    db.commit()
    return plan, member


def test_stale_reconcile_rollback_on_failure(db: Session):
    plan, _ = _seed_basic_plan_member(db)
    row = REVIEWED_SUBSCRIPTION_SNAPSHOT[125]
    member = Member(
        id=126,
        full_name="Stale",
        mobile_number="9311111126",
        joined_at=date(2026, 1, 1),
        status="active",
    )
    db.add(member)
    db.commit()
    sub = MembershipSubscription(
        id=125,
        member_id=126,
        plan_id=plan.id,
        start_date=row.start_date,
        end_date=row.end_date,
        base_price=1,
        tax_percent=5,
        tax_amount=0,
        total_amount=1,
        payment_status=row.payment_status,
        status=row.status,
    )
    db.add(sub)
    db.commit()

    with patch(
        "rehearsal_lifecycle_execution.reconcile.SubscriptionService._sync_expired_subscriptions_for_member",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(RuntimeError):
            reconcile_stale_member(
                db,
                member_id=126,
                subscription_id=125,
                today=date(2026, 11, 27),
            )
    db.refresh(sub)
    assert sub.status == "active"


def test_pause_remaining_matches_helper_not_hardcoded():
    """Regression: remaining at execution time, not a fixed rehearsal date constant."""
    snap = REVIEWED_SUBSCRIPTION_SNAPSHOT[92]
    today = date.today()
    expected = remaining_days_from_today(
        start_date=snap.start_date,
        end_date=snap.end_date,
        today=today,
    )
    if expected <= 0:
        pytest.skip("today is past sub 92 end in test environment")
    assert compute_pause_remaining_days(
        start_date=snap.start_date,
        end_date=snap.end_date,
        today=today,
    ) == expected


def test_device_sync_rejects_delete_userinfo():
    with pytest.raises(DeviceSyncError):
        assert_access_sync_commands(["C:1:DATA DELETE USERINFO PIN=1"])