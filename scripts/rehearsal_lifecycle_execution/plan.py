"""Dry-run execution plan builder."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from core.membership_lifecycle import remaining_days_from_today

from rehearsal_lifecycle_execution.constants import (
    MEMBER_98_PAUSE_SUB_ID,
    REVISION_N9B,
    STALE_SUBSCRIPTIONS,
    SUBSCRIPTION_IDS,
)
from rehearsal_lifecycle_execution.migrations import planned_migration_steps, read_alembic_version_from_engine
from rehearsal_lifecycle_execution.snapshot import (
    _as_date,
    assert_member_98_pre_reconcile,
    assert_stale_subscriptions_match_snapshot,
    subscription_matches_snapshot,
)


@dataclass
class ExecutionPlan:
    execution_date: date
    alembic_current: str
    migration_targets_before_reconcile: list[str]
    migration_after_reconcile: str | None
    remaining_days_sub_92: int | None
    stale_actions: list[dict[str, int]]
    member_98_action: dict[str, Any]
    snapshot_ok: bool
    snapshot_errors: list[str]


def _load_subscription_rows(engine: Engine) -> dict[int, dict[str, Any]]:
    sub_in = ",".join(str(i) for i in SUBSCRIPTION_IDS)
    with engine.connect() as conn:
        conn.execute(text("BEGIN READ ONLY"))
        rows = conn.execute(
            text(
                f"""
                SELECT id, member_id, status, payment_status, start_date, end_date
                FROM membership_subscriptions WHERE id IN ({sub_in})
                """
            )
        ).mappings().all()
        conn.execute(text("ROLLBACK"))
    return {int(r["id"]): dict(r) for r in rows}


def build_dry_run_plan(engine: Engine, *, execution_date: date | None = None) -> ExecutionPlan:
    execution_date = execution_date or date.today()
    current = read_alembic_version_from_engine(engine)
    steps = planned_migration_steps(current)

    remaining: int | None = None
    snapshot_errors: list[str] = []
    rows = _load_subscription_rows(engine)
    snapshot_ok = True
    try:
        for sub_id in SUBSCRIPTION_IDS:
            subscription_matches_snapshot(rows[sub_id])
        assert_stale_subscriptions_match_snapshot(rows)
        assert_member_98_pre_reconcile(rows)
        basic = rows[MEMBER_98_PAUSE_SUB_ID]
        remaining = remaining_days_from_today(
            start_date=_as_date(basic["start_date"]),
            end_date=_as_date(basic["end_date"]),
            today=execution_date,
        )
    except Exception as exc:
        snapshot_ok = False
        snapshot_errors.append(str(exc))

    migration_before = [s for s in steps if s != REVISION_N9B]
    migration_after = REVISION_N9B if REVISION_N9B in steps else None

    stale_actions = [
        {"subscription_id": sid, "member_id": mid, "action": "expire_via_complete_subscription"}
        for sid, mid in STALE_SUBSCRIPTIONS.items()
    ]

    member_98_action = {
        "subscription_id": 92,
        "predecessor_id": 631,
        "action": "pause_with_resume_after",
        "computed_remaining_days": remaining,
        "requires_n9a": True,
    }

    return ExecutionPlan(
        execution_date=execution_date,
        alembic_current=current,
        migration_targets_before_reconcile=migration_before,
        migration_after_reconcile=migration_after,
        remaining_days_sub_92=remaining,
        stale_actions=stale_actions,
        member_98_action=member_98_action,
        snapshot_ok=snapshot_ok,
        snapshot_errors=snapshot_errors,
    )


def format_plan(plan: ExecutionPlan) -> str:
    lines = [
        f"execution_date={plan.execution_date.isoformat()}",
        f"alembic_current={plan.alembic_current!r}",
        f"snapshot_ok={plan.snapshot_ok}",
        f"migrations_before_reconcile={plan.migration_targets_before_reconcile}",
        f"migration_after_reconcile={plan.migration_after_reconcile!r}",
        f"remaining_days_sub_92={plan.remaining_days_sub_92}",
        "stale_reconciliation=" + repr(plan.stale_actions),
        "member_98=" + repr(plan.member_98_action),
    ]
    if plan.snapshot_errors:
        lines.append("snapshot_errors=" + repr(plan.snapshot_errors))
    lines.extend(
        [
            "ordered_steps:",
            "  1) backup export",
            "  2) alembic upgrades before reconcile",
            "  3) reconcile stale (one txn/member)",
            "  4) reconcile member 98 pause",
            "  5) alembic upgrade n9b",
            "  6) device_access_sync",
            "  7) preflight checks 1-8",
        ]
    )
    return "\n".join(lines)