"""Orchestration for dry-run and execute modes."""

from __future__ import annotations

import json
import logging
import sys
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from rehearsal_lifecycle_execution.backup import create_engine_for_url, write_backup_bundle
from rehearsal_lifecycle_execution.constants import (
    REHEARSAL_DB_HOST,
    REVISION_L7,
    REVISION_M8,
    REVISION_N9A,
    REVISION_N9B,
    SUBSCRIPTION_IDS,
)
from rehearsal_lifecycle_execution.device_readiness import assess_device_readiness
from rehearsal_lifecycle_execution.execution_lock import rehearsal_run_lock
from rehearsal_lifecycle_execution.device_sync import (
    DeviceSyncReport,
    run_device_access_sync_idempotent,
)
from rehearsal_lifecycle_execution.errors import (
    PreflightError,
    ReconciliationError,
    RemainingDaysError,
    RehearsalExecutionError,
)
from rehearsal_lifecycle_execution.migrations import (
    read_alembic_version,
    require_alembic_version,
    upgrade_to_revision,
)
from rehearsal_lifecycle_execution.plan import build_dry_run_plan, format_plan
from rehearsal_lifecycle_execution.preflight import run_preflight_checks
from rehearsal_lifecycle_execution.reconcile import reconcile_all_stale, reconcile_member_98_pause
from rehearsal_lifecycle_execution.safety import (
    assert_engine_uses_validated_url,
    assert_write_phase_hostname,
    database_hostname,
    resolve_database_url,
)
from rehearsal_lifecycle_execution.snapshot import invoice_rows_unchanged

logger = logging.getLogger(__name__)

EXIT_DEVICE_SYNC_FAILED = 3
EXIT_DEVICE_SYNC_SKIPPED = 4


def configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(name)s %(message)s")


def prompt_execute_confirmation() -> None:
    print(f"Rehearsal execution will write to host: {REHEARSAL_DB_HOST}")
    typed = input("Type the exact rehearsal hostname to continue: ").strip()
    if typed != REHEARSAL_DB_HOST:
        raise RehearsalExecutionError("Hostname confirmation failed; aborting execute mode")


def _duplicate_active_sql() -> str:
    return """
        SELECT member_id, COUNT(*) AS active_count, array_agg(id) AS ids
        FROM membership_subscriptions
        WHERE status = 'active'
        GROUP BY member_id
        HAVING COUNT(*) > 1
    """


def assert_no_duplicate_active(engine) -> None:
    with engine.connect() as conn:
        rows = conn.execute(text(_duplicate_active_sql())).mappings().all()
    if rows:
        raise ReconciliationError(f"Duplicate active subscriptions block n9b: {list(rows)}")


def _fetch_invoices(engine, sub_ids: tuple[int, ...]) -> list[dict]:
    sub_in = ",".join(str(i) for i in sub_ids)
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(f"SELECT * FROM invoices WHERE subscription_id IN ({sub_in}) ORDER BY id")).mappings().all()]


def _log_preflight(report) -> None:
    logger.info("preflight_ok", extra={"report": report.as_dict()})


def _device_sync_exit_code(report: DeviceSyncReport) -> int:
    if report.device_sync_skipped:
        return EXIT_DEVICE_SYNC_SKIPPED
    return 0


def _print_device_sync_skip(context: str) -> None:
    print(
        f"NOTE: {context}: device sync intentionally skipped (no eligible PUSH devices).",
        file=sys.stderr,
    )


def run_dry_run(*, execution_date: date | None = None, verbose: bool = False) -> int:
    configure_logging(verbose)
    database_url = resolve_database_url()
    engine = create_engine_for_url(database_url)
    assert_engine_uses_validated_url(engine, database_url)
    plan = build_dry_run_plan(engine, execution_date=execution_date or date.today())
    print(format_plan(plan))

    preflight_failed = False
    current: str | None = None

    try:
        current = read_alembic_version(database_url)
        if current in (REVISION_N9A, REVISION_N9B):
            pre = run_preflight_checks(engine, phase="pre_reconcile")
            print("preflight_pre_reconcile:", json.dumps(pre.as_dict(), default=str))
        if current == REVISION_N9A:
            msg = (
                "preflight_pre_n9b: INCONCLUSIVE in dry-run (requires reconciliation; "
                "full execute readiness NOT cleared for post-reconcile checks)"
            )
            print(msg, file=sys.stderr)
        elif current == REVISION_N9B:
            post = run_preflight_checks(engine, phase="pre_n9b")
            print("preflight_pre_n9b:", json.dumps(post.as_dict(), default=str))
    except PreflightError as exc:
        preflight_failed = True
        print(f"DRY-RUN preflight FAILED: {exc}", file=sys.stderr)

    if preflight_failed:
        print("DRY-RUN aborted: preflight checks did not pass.", file=sys.stderr)
        return 2

    if not plan.snapshot_ok:
        print("DRY-RUN: snapshot mismatches detected", file=sys.stderr)
        return 2
    if plan.remaining_days_sub_92 is not None and plan.remaining_days_sub_92 <= 0:
        print("DRY-RUN: remaining_days <= 0", file=sys.stderr)
        return 2

    if current == REVISION_N9A:
        print(
            "DRY-RUN complete (read-only; pre-reconcile preflight passed where applicable; "
            "pre-n9b not evaluated without reconciliation).",
        )
    else:
        print("DRY-RUN complete (read-only; applicable preflight checks passed).")
    return 0


def run_execute(
    *,
    execution_date: date | None = None,
    device_sync_only: bool = False,
    allow_zero_push_devices: bool = False,
    verbose: bool = False,
) -> int:
    configure_logging(verbose)
    if not device_sync_only:
        prompt_execute_confirmation()

    database_url = resolve_database_url()
    execution_date = execution_date or date.today()
    engine = create_engine_for_url(database_url)
    assert_engine_uses_validated_url(engine, database_url)
    SessionLocal = sessionmaker(bind=engine)
    hostname = database_hostname(database_url)

    with rehearsal_run_lock(engine):
        if device_sync_only:
            assert_write_phase_hostname(database_url)
            try:
                with SessionLocal() as db:
                    report = run_device_access_sync_idempotent(
                        db,
                        allow_zero_push_devices=allow_zero_push_devices,
                    )
            except Exception as exc:
                logger.error("device_sync_failed", extra={"error": str(exc), "mode": "device_sync_only"})
                print(f"device_sync_only: failed ({exc})", file=sys.stderr)
                return EXIT_DEVICE_SYNC_FAILED
            code = _device_sync_exit_code(report)
            if code == EXIT_DEVICE_SYNC_SKIPPED:
                _print_device_sync_skip("device_sync_only")
                return code
            print(
                "device_sync_only: queue reconciliation complete (NOT physical device verification). "
                f"Devices={report.eligible_device_serials} "
                f"newly_queued={report.commands_newly_queued} "
                f"in_flight_equivalent={report.commands_satisfied_in_flight} "
                f"completed_ack_equivalent={report.commands_satisfied_completed_ack}"
            )
            return 0

        # --- read-only plan gate ---
        plan = build_dry_run_plan(engine, execution_date=execution_date)
        if not plan.snapshot_ok:
            raise RehearsalExecutionError(f"Snapshot mismatch: {plan.snapshot_errors}")
        if plan.remaining_days_sub_92 is None or plan.remaining_days_sub_92 <= 0:
            raise RemainingDaysError("remaining_days <= 0 at execution time")

        logger.info(
            "execution_phase_order",
            extra={"step": "read_only_plan_ok", "next": "device_readiness_upfront"},
        )
        assert_write_phase_hostname(database_url)
        with SessionLocal() as db:
            upfront = assess_device_readiness(
                db,
                allow_zero_push_devices=allow_zero_push_devices,
                phase="upfront",
            )
        if upfront.database_only_opt_in:
            print(
                "AUTHORIZED: database-only execution (--allow-database-only-without-device-sync); "
                "zero eligible PUSH devices at upfront check.",
                file=sys.stderr,
            )
        logger.info(
            "execution_phase_order",
            extra={
                "step": "device_readiness_upfront_ok",
                "eligible_device_count": upfront.device_count,
                "next": "backup_export_local_files_only",
            },
        )

        current = read_alembic_version(database_url)
        invoices_before = _fetch_invoices(engine, SUBSCRIPTION_IDS)
        backup_meta = write_backup_bundle(engine, current, rehearsal_hostname=hostname)

        logger.info("backup_written", extra=backup_meta)
        logger.info(
            "execution_phase_order",
            extra={"step": "backup_export_complete", "next": "database_writes_migrations"},
        )

        # --- migrations before reconcile ---
        if current == REVISION_N9B:
            raise ReconciliationError("Database already at n9b; refusing full execute (use device-sync-only if needed)")
        if current == REVISION_L7:
            require_alembic_version(database_url, REVISION_L7, context="pre-m8")
            assert_write_phase_hostname(database_url)
            upgrade_to_revision(database_url, REVISION_M8, context="upgrade m8")
            current = REVISION_M8
        if current == REVISION_M8:
            require_alembic_version(database_url, REVISION_M8, context="pre-n9a")
            assert_write_phase_hostname(database_url)
            upgrade_to_revision(database_url, REVISION_N9A, context="upgrade n9a")
            current = REVISION_N9A
        if current != REVISION_N9A:
            raise ReconciliationError(f"Unexpected revision before reconcile: {current!r}")

        require_alembic_version(database_url, REVISION_N9A, context="pre-reconcile")
        assert_engine_uses_validated_url(engine, database_url)

        # --- preflight before reconciliation ---
        pre_report = run_preflight_checks(engine, phase="pre_reconcile")
        _log_preflight(pre_report)

        # --- reconciliation (per-member transactions inside reconcile_*) ---
        assert_write_phase_hostname(database_url)
        with SessionLocal() as db:
            reconcile_all_stale(db, today=execution_date)
        assert_write_phase_hostname(database_url)
        with SessionLocal() as db:
            remaining = reconcile_member_98_pause(db, today=execution_date)
            logger.info("member_98_paused", extra={"remaining_days": remaining})

        invoices_after_reconcile = _fetch_invoices(engine, SUBSCRIPTION_IDS)
        invoice_rows_unchanged(invoices_before, invoices_after_reconcile)

        assert_no_duplicate_active(engine)

        # --- preflight before n9b ---
        post_report = run_preflight_checks(engine, phase="pre_n9b")
        _log_preflight(post_report)

        # --- n9b ---
        assert_write_phase_hostname(database_url)
        require_alembic_version(database_url, REVISION_N9A, context="pre-n9b")
        upgrade_to_revision(database_url, REVISION_N9B, context="upgrade n9b")
        require_alembic_version(database_url, REVISION_N9B, context="post-n9b")

        # --- device sync (separate phase; can retry via --device-sync-only) ---
        try:
            assert_write_phase_hostname(database_url)
            with SessionLocal() as db:
                report = run_device_access_sync_idempotent(
                    db,
                    allow_zero_push_devices=allow_zero_push_devices,
                )
            code = _device_sync_exit_code(report)
            if code == EXIT_DEVICE_SYNC_SKIPPED:
                _print_device_sync_skip("full_execute")
                print(
                    "Database migrations and reconciliation completed; device sync was not performed.",
                    file=sys.stderr,
                )
                return code
            logger.info(
                "device_sync",
                extra={
                    "commands_newly_queued": report.commands_newly_queued,
                    "in_flight_equivalent": report.commands_satisfied_in_flight,
                    "completed_ack_equivalent": report.commands_satisfied_completed_ack,
                    "device_physically_verified": report.device_physically_verified,
                    "pri_values": report.privilege_values,
                    "devices": report.eligible_device_serials,
                },
            )
        except Exception as exc:
            logger.error("device_sync_failed", extra={"error": str(exc)})
            print(
                "WARNING: reconciliation and migrations succeeded; device sync failed. "
                "Re-run with --execute --device-sync-only",
                file=sys.stderr,
            )
            return EXIT_DEVICE_SYNC_FAILED

        print(
            "EXECUTE complete (queue state reconciled; NOT physical device verification). "
            f"backup: {backup_meta.get('json_path')}"
        )
        return 0