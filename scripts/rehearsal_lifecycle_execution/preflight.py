"""Automated membership queue integrity checks (Phase 1.3.2 / preflight SQL)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.engine import Engine

from rehearsal_lifecycle_execution.constants import MEMBER_98_PAUSE_SUB_ID, MEMBER_98_PREDECESSOR_SUB_ID
from rehearsal_lifecycle_execution.errors import PreflightError

PreflightPhase = Literal["pre_reconcile", "pre_n9b"]

PREFLIGHT_QUERIES: dict[int, str] = {
    1: """
        SELECT member_id, COUNT(*) AS orphan_count,
               array_agg(id ORDER BY start_date, created_at, id) AS subscription_ids
        FROM membership_subscriptions
        WHERE status = 'scheduled'
          AND resume_after_subscription_id IS NULL
        GROUP BY member_id
        HAVING COUNT(*) > 1
    """,
    2: """
        SELECT child.id AS child_id, child.member_id, child.status, child.resume_after_subscription_id
        FROM membership_subscriptions child
        LEFT JOIN membership_subscriptions pred ON pred.id = child.resume_after_subscription_id
        WHERE child.resume_after_subscription_id IS NOT NULL
          AND pred.id IS NULL
    """,
    3: """
        SELECT child.id AS child_id, child.member_id AS child_member_id,
               pred.id AS pred_id, pred.member_id AS pred_member_id
        FROM membership_subscriptions child
        JOIN membership_subscriptions pred ON pred.id = child.resume_after_subscription_id
        WHERE child.member_id <> pred.member_id
    """,
    4: """
        SELECT child.id, child.member_id, child.status, child.resume_after_subscription_id, pred.status AS pred_status
        FROM membership_subscriptions child
        JOIN membership_subscriptions pred ON pred.id = child.resume_after_subscription_id
        WHERE child.status IN ('paused', 'scheduled')
          AND pred.status IN ('expired', 'cancelled')
    """,
    5: """
        SELECT resume_after_subscription_id AS predecessor_id,
               COUNT(*) AS paused_count,
               array_agg(id ORDER BY paused_at NULLS LAST, created_at, id) AS paused_ids
        FROM membership_subscriptions
        WHERE status = 'paused'
          AND resume_after_subscription_id IS NOT NULL
        GROUP BY resume_after_subscription_id
        HAVING COUNT(*) > 1
    """,
    6: """
        SELECT resume_after_subscription_id AS predecessor_id,
               COUNT(*) AS scheduled_count,
               array_agg(id ORDER BY start_date, created_at, id) AS scheduled_ids
        FROM membership_subscriptions
        WHERE status = 'scheduled'
          AND resume_after_subscription_id IS NOT NULL
        GROUP BY resume_after_subscription_id
        HAVING COUNT(*) > 1
    """,
    7: """
        SELECT id, member_id, status
        FROM membership_subscriptions
        WHERE resume_after_subscription_id = id
    """,
    8: """
        SELECT member_id, COUNT(*) AS active_count, array_agg(id ORDER BY id) AS ids
        FROM membership_subscriptions
        WHERE status = 'active'
        GROUP BY member_id
        HAVING COUNT(*) > 1
    """,
}


@dataclass
class PreflightCheckResult:
    check_id: int
    row_count: int
    rows: list[dict[str, Any]]


@dataclass
class PreflightReport:
    phase: PreflightPhase
    results: list[PreflightCheckResult]

    @property
    def failed_checks(self) -> list[PreflightCheckResult]:
        return [r for r in self.results if r.row_count > 0]

    def as_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "checks": [
                {"id": r.check_id, "row_count": r.row_count, "rows": r.rows}
                for r in self.results
            ],
        }


def _lifecycle_columns_present(engine: Engine) -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_name = 'membership_subscriptions'
                  AND column_name = 'resume_after_subscription_id'
                """
            )
        ).scalar_one()
    return int(row) > 0


def _run_check(engine: Engine, check_id: int) -> PreflightCheckResult:
    query = PREFLIGHT_QUERIES[check_id]
    with engine.connect() as conn:
        rows = [dict(r) for r in conn.execute(text(query)).mappings().all()]
    return PreflightCheckResult(check_id=check_id, row_count=len(rows), rows=rows)


def _filter_check_8_pre_reconcile(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Member 98 may have two active rows (92, 631) until pause reconciliation."""
    unexpected: list[dict[str, Any]] = []
    for row in rows:
        member_id = int(row["member_id"])
        ids = sorted(int(x) for x in row.get("ids", []))
        if member_id == 98 and ids == [MEMBER_98_PAUSE_SUB_ID, MEMBER_98_PREDECESSOR_SUB_ID]:
            continue
        unexpected.append(row)
    return unexpected


def run_preflight_checks(engine: Engine, *, phase: PreflightPhase) -> PreflightReport:
    """
    Run integrity checks 1–8 against the validated engine.

    pre_reconcile: checks 1–7 must be empty; check 8 allows member 98 duplicate only.
    pre_n9b: all checks 1–8 must be empty.
    """
    if not _lifecycle_columns_present(engine):
        raise PreflightError(
            "Lifecycle columns missing; run n9a before preflight checks 1–7"
        )

    results: list[PreflightCheckResult] = []
    for check_id in range(1, 9):
        result = _run_check(engine, check_id)
        if check_id == 8 and phase == "pre_reconcile":
            filtered = _filter_check_8_pre_reconcile(result.rows)
            result = PreflightCheckResult(check_id=8, row_count=len(filtered), rows=filtered)
        results.append(result)

    report = PreflightReport(phase=phase, results=results)
    failures = report.failed_checks
    if failures:
        summary = ", ".join(f"check {r.check_id}: {r.row_count} row(s)" for r in failures)
        raise PreflightError(f"Preflight {phase} failed ({summary}): {report.as_dict()}")
    return report