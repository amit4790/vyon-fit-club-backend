"""Phase 1.3.8.2 execution safety hardening tests (no live DB)."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rehearsal_lifecycle_execution.backup import (
    collect_backup_payload,
    validate_backup_payload,
    verify_backup_checksum,
    write_backup_bundle,
)
from rehearsal_lifecycle_execution.constants import (
    AFFECTED_MEMBER_IDS,
    REHEARSAL_DB_HOST,
    REVIEWED_SUBSCRIPTION_SNAPSHOT,
    SUBSCRIPTION_IDS,
)
from rehearsal_lifecycle_execution.errors import BackupValidationError, DeviceSyncError, PreflightError
from rehearsal_lifecycle_execution.migrations import upgrade_to_revision
from rehearsal_lifecycle_execution.preflight import _filter_check_8_pre_reconcile
from rehearsal_lifecycle_execution.safety import build_alembic_subprocess_env, resolve_database_url
from sqlalchemy import create_engine

from rehearsal_lifecycle_execution.device_sync import run_device_access_sync
from sqlalchemy.orm import Session
from models import Member, MembershipPlan, MembershipSubscription


def test_shell_database_url_does_not_override_dotenv():
    """resolve_database_url uses backend/.env, not os.environ DATABASE_URL."""
    rehearse = f"postgresql://u:p@{REHEARSAL_DB_HOST}/neondb"
    other = "postgresql://evil:evil@evil.example.com/evil"
    env = {"DATABASE_URL": rehearse, "DATABASE_URL_PROD": ""}
    with patch.dict(os.environ, {"DATABASE_URL": other}, clear=False):
        assert resolve_database_url(env) == rehearse


def test_build_alembic_subprocess_env_excludes_shell_database_url():
    validated = f"postgresql://u:p@{REHEARSAL_DB_HOST}/neondb"
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql://wrong/wrong", "DATABASE_URL_PROD": "x"}, clear=False):
        env = build_alembic_subprocess_env(validated)
    assert env["DATABASE_URL"] == validated
    assert "DATABASE_URL_PROD" not in env


def test_alembic_subprocess_receives_validated_url_only():
    validated = f"postgresql://u:p@{REHEARSAL_DB_HOST}/neondb"
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql://wrong/wrong"}, clear=False):
        with patch("rehearsal_lifecycle_execution.migrations.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch(
                "rehearsal_lifecycle_execution.migrations.require_alembic_version",
                return_value="m8n9o0p1q2r3",
            ):
                upgrade_to_revision(validated, "m8n9o0p1q2r3", context="test")
    env = mock_run.call_args.kwargs["env"]
    assert env["DATABASE_URL"] == validated
    assert env.get("DATABASE_URL_PROD") is None


def test_preflight_check8_pre_reconcile_allows_member_98_only():
    rows = [
        {"member_id": 98, "ids": [92, 631]},
        {"member_id": 12, "ids": [1, 2]},
    ]
    unexpected = _filter_check_8_pre_reconcile(rows)
    assert len(unexpected) == 1
    assert int(unexpected[0]["member_id"]) == 12


def test_backup_payload_validation_complete(tmp_path):
    subs = []
    for sid in SUBSCRIPTION_IDS:
        snap = REVIEWED_SUBSCRIPTION_SNAPSHOT[sid]
        subs.append(
            {
                "id": sid,
                "member_id": snap.member_id,
                "status": snap.status,
                "payment_status": snap.payment_status,
                "start_date": snap.start_date.isoformat(),
                "end_date": snap.end_date.isoformat(),
            }
        )
    payload = {
        "exported_at_utc": "2026-11-27T00:00:00+00:00",
        "rehearsal_hostname": REHEARSAL_DB_HOST,
        "alembic_version": "n9o0p1q2r3s4",
        "subscriptions": subs,
        "invoices": [{"id": 1, "subscription_id": 92, "amount": 1.0}],
        "member_device_state": [{"id": mid} for mid in AFFECTED_MEMBER_IDS],
        "member_device_state_schema_notes": {},
        "device_commands": [],
        "push_devices_active": [],
    }
    validate_backup_payload(payload)
    json_path = tmp_path / "backup.json"
    checksum_path = tmp_path / "backup.sha256"
    from rehearsal_lifecycle_execution.serialization import canonical_json_dumps, sha256_hex

    body = canonical_json_dumps(payload)
    digest = sha256_hex(body)
    json_path.write_text(body, encoding="utf-8")
    checksum_path.write_text(f"{digest}  {json_path.name}\n", encoding="utf-8")
    assert verify_backup_checksum(json_path, checksum_path) == digest


def test_backup_validation_rejects_incomplete_subscriptions():
    with pytest.raises(BackupValidationError, match="subscription"):
        validate_backup_payload(
            {
                "exported_at_utc": "t",
                "rehearsal_hostname": REHEARSAL_DB_HOST,
                "alembic_version": "x",
                "subscriptions": [],
                "invoices": [{"id": 1}],
                "member_device_state": [],
                "device_commands": [],
            }
        )


def test_zero_devices_aborts_without_opt_in(db: Session, monkeypatch):
    plan, member = _seed(db)
    monkeypatch.setattr("rehearsal_lifecycle_execution.device_readiness.settings.device_push_enabled", True)
    monkeypatch.setattr(
        "rehearsal_lifecycle_execution.device_readiness.list_eligible_push_device_serials",
        lambda _db: [],
    )
    with pytest.raises(DeviceSyncError, match="Zero eligible"):
        run_device_access_sync(db, member_ids=(member.id,), allow_zero_push_devices=False)


def test_zero_devices_opt_in_skips_successfully(db: Session, monkeypatch):
    plan, member = _seed(db)
    monkeypatch.setattr("rehearsal_lifecycle_execution.device_readiness.settings.device_push_enabled", True)
    monkeypatch.setattr(
        "rehearsal_lifecycle_execution.device_readiness.list_eligible_push_device_serials",
        lambda _db: [],
    )
    report = run_device_access_sync(db, member_ids=(member.id,), allow_zero_push_devices=True)
    assert report.device_sync_skipped is True
    assert report.command_strings == []


def test_missing_commands_when_devices_exist(db: Session, monkeypatch):
    plan, member = _seed(db)
    monkeypatch.setattr("rehearsal_lifecycle_execution.device_readiness.settings.device_push_enabled", True)
    monkeypatch.setattr(
        "rehearsal_lifecycle_execution.device_readiness.list_eligible_push_device_serials",
        lambda _db: ["DEV001"],
    )
    monkeypatch.setattr(
        "rehearsal_lifecycle_execution.device_sync._queue_member_access_idempotent",
        lambda *a, **k: [],
    )
    with pytest.raises(DeviceSyncError, match="(Access sync incomplete|expected up to|Expected at least)"):
        run_device_access_sync(db, member_ids=(member.id,))


def test_device_retry_does_not_call_reconcile(monkeypatch):
    validated = f"postgresql://u:p@{REHEARSAL_DB_HOST}/neondb"
    with patch("rehearsal_lifecycle_execution.runner.reconcile_all_stale") as stale:
        with patch("rehearsal_lifecycle_execution.runner.reconcile_member_98_pause") as pause:
            with patch("rehearsal_lifecycle_execution.runner.prompt_execute_confirmation"):
                with patch("rehearsal_lifecycle_execution.runner.rehearsal_run_lock") as _rl:
                    _rl.return_value.__enter__ = lambda s: None
                    _rl.return_value.__exit__ = lambda s, *a: None
                    with patch("rehearsal_lifecycle_execution.runner.resolve_database_url", return_value=validated):
                        with patch(
                            "rehearsal_lifecycle_execution.runner.run_device_access_sync_idempotent",
                            return_value=MagicMock(
                                device_sync_skipped=False,
                                command_strings=["x"],
                                eligible_device_serials=["D"],
                                commands_newly_queued=1,
                                commands_satisfied_in_flight=0,
                                commands_satisfied_completed_ack=0,
                            ),
                        ):
                            from rehearsal_lifecycle_execution.runner import run_execute

                            with patch("rehearsal_lifecycle_execution.runner.assert_engine_uses_validated_url"):
                                with patch("rehearsal_lifecycle_execution.runner.create_engine_for_url"):
                                    with patch("rehearsal_lifecycle_execution.runner.sessionmaker") as sm:
                                        sm.return_value = MagicMock()
                                        run_execute(device_sync_only=True, allow_zero_push_devices=True)
            stale.assert_not_called()
            pause.assert_not_called()


def test_preflight_failure_blocks_runner(monkeypatch):
    validated = f"postgresql://u:p@{REHEARSAL_DB_HOST}/db"
    n9a = "n9o0p1q2r3s4"
    with patch("rehearsal_lifecycle_execution.runner.prompt_execute_confirmation"):
        with patch("rehearsal_lifecycle_execution.runner.rehearsal_run_lock") as _rl:
            _rl.return_value.__enter__ = lambda s: None
            _rl.return_value.__exit__ = lambda s, *a: None
            with patch("rehearsal_lifecycle_execution.runner.resolve_database_url", return_value=validated):
                with patch("rehearsal_lifecycle_execution.runner.build_dry_run_plan") as plan:
                    plan.return_value = MagicMock(snapshot_ok=True, remaining_days_sub_92=7)
                    with patch(
                        "rehearsal_lifecycle_execution.runner.read_alembic_version",
                        return_value=n9a,
                    ):
                        with patch(
                            "rehearsal_lifecycle_execution.migrations.read_alembic_version",
                            return_value=n9a,
                        ):
                            with patch(
                                "rehearsal_lifecycle_execution.runner.write_backup_bundle",
                                return_value={"json_path": "/tmp/x.json"},
                            ):
                                with patch(
                                    "rehearsal_lifecycle_execution.runner._fetch_invoices",
                                    return_value=[],
                                ):
                                    with patch(
                                        "rehearsal_lifecycle_execution.runner.run_preflight_checks",
                                        side_effect=PreflightError("check 3 failed"),
                                    ):
                                        from rehearsal_lifecycle_execution.runner import run_execute

                                        with patch(
                                            "rehearsal_lifecycle_execution.runner.assert_engine_uses_validated_url"
                                        ):
                                            with patch(
                                                "rehearsal_lifecycle_execution.runner.create_engine_for_url",
                                                return_value=MagicMock(),
                                            ):
                                                with patch(
                                                    "rehearsal_lifecycle_execution.runner.assess_device_readiness",
                                                    return_value=MagicMock(
                                                        device_count=1,
                                                        database_only_opt_in=False,
                                                    ),
                                                ):
                                                    with patch(
                                                        "rehearsal_lifecycle_execution.runner.reconcile_all_stale"
                                                    ) as stale:
                                                        with pytest.raises(PreflightError):
                                                            run_execute()
                                                        stale.assert_not_called()


def test_post_reconcile_preflight_failure_blocks_n9b():
    validated = f"postgresql://u:p@{REHEARSAL_DB_HOST}/db"
    n9a = "n9o0p1q2r3s4"
    calls = {"n": 0}

    def preflight_side_effect(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return MagicMock(as_dict=lambda: {"ok": True})
        raise PreflightError("post-reconcile check 8 failed")

    with patch("rehearsal_lifecycle_execution.runner.prompt_execute_confirmation"):
        with patch("rehearsal_lifecycle_execution.runner.rehearsal_run_lock") as _rl:
            _rl.return_value.__enter__ = lambda s: None
            _rl.return_value.__exit__ = lambda s, *a: None
            with patch("rehearsal_lifecycle_execution.runner.resolve_database_url", return_value=validated):
                with patch("rehearsal_lifecycle_execution.runner.build_dry_run_plan") as plan:
                    plan.return_value = MagicMock(snapshot_ok=True, remaining_days_sub_92=7)
                    with patch(
                        "rehearsal_lifecycle_execution.runner.read_alembic_version",
                        return_value=n9a,
                    ):
                        with patch(
                            "rehearsal_lifecycle_execution.migrations.read_alembic_version",
                            return_value=n9a,
                        ):
                            with patch(
                                "rehearsal_lifecycle_execution.runner.write_backup_bundle",
                                return_value={"json_path": "/tmp/x.json"},
                            ):
                                with patch(
                                    "rehearsal_lifecycle_execution.runner._fetch_invoices",
                                    return_value=[],
                                ):
                                    with patch(
                                        "rehearsal_lifecycle_execution.runner.run_preflight_checks",
                                        side_effect=preflight_side_effect,
                                    ):
                                        with patch(
                                            "rehearsal_lifecycle_execution.runner.reconcile_all_stale"
                                        ):
                                            with patch(
                                                "rehearsal_lifecycle_execution.runner.reconcile_member_98_pause",
                                                return_value=7,
                                            ):
                                                with patch(
                                                    "rehearsal_lifecycle_execution.runner.assert_no_duplicate_active"
                                                ):
                                                    with patch(
                                                        "rehearsal_lifecycle_execution.runner.upgrade_to_revision"
                                                    ) as upgrade:
                                                        from rehearsal_lifecycle_execution.runner import run_execute

                                                        with patch(
                                                            "rehearsal_lifecycle_execution.runner.assert_engine_uses_validated_url"
                                                        ):
                                                            with patch(
                                                                "rehearsal_lifecycle_execution.runner.create_engine_for_url",
                                                                return_value=MagicMock(),
                                                            ):
                                                                with patch(
                                                                    "rehearsal_lifecycle_execution.runner.sessionmaker",
                                                                    return_value=MagicMock(),
                                                                ):
                                                                    with patch(
                                                                        "rehearsal_lifecycle_execution.runner.assess_device_readiness",
                                                                        return_value=MagicMock(
                                                                            device_count=1,
                                                                            database_only_opt_in=False,
                                                                        ),
                                                                    ):
                                                                        with pytest.raises(PreflightError):
                                                                            run_execute()
                                                                        upgrade.assert_not_called()


def _seed(db: Session):
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
        full_name="M",
        mobile_number="9399111222",
        joined_at=date.today(),
        status="active",
    )
    db.add_all([plan, member])
    db.commit()
    return plan, member


def test_existing_device_sync_idempotent_with_devices(db: Session, monkeypatch):
    """Updated from 1.3.8: eligible devices required."""
    plan, member = _seed(db)
    sub = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=date.today(),
        end_date=date.today(),
        base_price=1,
        tax_percent=5,
        tax_amount=0,
        total_amount=1,
        payment_status="paid",
        status="active",
    )
    db.add(sub)
    db.commit()

    class _Cmd:
        command = "C:1:DATA UPDATE USERINFO PIN=1\tName=x\tPri=0\tPasswd="

    def _fake(self, member_id, member_name, *, enabled):
        return [_Cmd()]

    monkeypatch.setattr("rehearsal_lifecycle_execution.device_readiness.settings.device_push_enabled", True)
    monkeypatch.setattr(
        "rehearsal_lifecycle_execution.device_readiness.list_eligible_push_device_serials",
        lambda _db: ["DEV001"],
    )
    monkeypatch.setattr(
        "rehearsal_lifecycle_execution.device_sync._queue_member_access_idempotent",
        lambda *a, **k: [_Cmd().command],
    )
    from rehearsal_lifecycle_execution.device_sync import run_device_access_sync_idempotent

    run_device_access_sync_idempotent(db, member_ids=(member.id,))
    run_device_access_sync_idempotent(db, member_ids=(member.id,))