"""Preflight snapshot comparison."""

from __future__ import annotations

from datetime import date
from typing import Any

from rehearsal_lifecycle_execution.constants import (
    INVOICE_IMMUTABLE_COLUMNS,
    MEMBER_98_LEAVE_EXPIRED_SUB_ID,
    MEMBER_98_PAUSE_SUB_ID,
    MEMBER_98_PREDECESSOR_SUB_ID,
    REVIEWED_SUBSCRIPTION_SNAPSHOT,
    STALE_SUBSCRIPTIONS,
    ReviewedSubscriptionSnapshot,
)
from rehearsal_lifecycle_execution.errors import SnapshotMismatchError


def _as_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise SnapshotMismatchError(f"Cannot parse date from {value!r}")


def subscription_matches_snapshot(row: dict[str, Any]) -> None:
    sub_id = int(row["id"])
    expected = REVIEWED_SUBSCRIPTION_SNAPSHOT.get(sub_id)
    if expected is None:
        raise SnapshotMismatchError(f"Subscription {sub_id} is not in reviewed snapshot")

    checks = {
        "member_id": int(row["member_id"]),
        "status": str(row["status"]),
        "payment_status": str(row["payment_status"]),
        "start_date": _as_date(row["start_date"]),
        "end_date": _as_date(row["end_date"]),
    }
    if checks["member_id"] != expected.member_id:
        raise SnapshotMismatchError(f"Subscription {sub_id}: member_id mismatch")
    if checks["status"] != expected.status:
        raise SnapshotMismatchError(
            f"Subscription {sub_id}: status {checks['status']!r} != {expected.status!r}"
        )
    if checks["payment_status"] != expected.payment_status:
        raise SnapshotMismatchError(f"Subscription {sub_id}: payment_status mismatch")
    if checks["start_date"] != expected.start_date:
        raise SnapshotMismatchError(f"Subscription {sub_id}: start_date mismatch")
    if checks["end_date"] != expected.end_date:
        raise SnapshotMismatchError(f"Subscription {sub_id}: end_date mismatch")


def assert_stale_subscriptions_match_snapshot(rows_by_id: dict[int, dict[str, Any]]) -> None:
    for sub_id, member_id in STALE_SUBSCRIPTIONS.items():
        row = rows_by_id.get(sub_id)
        if row is None:
            raise SnapshotMismatchError(f"Missing stale subscription {sub_id}")
        if int(row["member_id"]) != member_id:
            raise SnapshotMismatchError(
                f"Subscription {sub_id}: expected member {member_id}, got {row['member_id']}"
            )
        subscription_matches_snapshot(row)


def assert_member_98_pre_reconcile(rows_by_id: dict[int, dict[str, Any]]) -> None:
    for sub_id in (MEMBER_98_PAUSE_SUB_ID, MEMBER_98_PREDECESSOR_SUB_ID, MEMBER_98_LEAVE_EXPIRED_SUB_ID):
        if sub_id not in rows_by_id:
            raise SnapshotMismatchError(f"Missing member 98 subscription {sub_id}")
        subscription_matches_snapshot(rows_by_id[sub_id])

    basic = rows_by_id[MEMBER_98_PAUSE_SUB_ID]
    pro = rows_by_id[MEMBER_98_PREDECESSOR_SUB_ID]
    expired = rows_by_id[MEMBER_98_LEAVE_EXPIRED_SUB_ID]

    if basic["status"] != "active" or pro["status"] != "active":
        raise SnapshotMismatchError("Member 98: subscriptions 92 and 631 must both be active")
    if expired["status"] != "expired":
        raise SnapshotMismatchError("Member 98: subscription 507 must remain expired")


def invoice_rows_unchanged(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> None:
    before_by_id = {int(r["id"]): r for r in before}
    after_by_id = {int(r["id"]): r for r in after}
    if before_by_id.keys() != after_by_id.keys():
        raise SnapshotMismatchError("Invoice id set changed during reconciliation")

    for inv_id, prev in before_by_id.items():
        cur = after_by_id[inv_id]
        for col in INVOICE_IMMUTABLE_COLUMNS:
            if col not in prev and col not in cur:
                continue
            if prev.get(col) != cur.get(col):
                raise SnapshotMismatchError(
                    f"Invoice {inv_id} column {col!r} changed from {prev.get(col)!r} to {cur.get(col)!r}"
                )


def row_to_snapshot_dict(row: ReviewedSubscriptionSnapshot) -> dict[str, Any]:
    return {
        "id": row.id,
        "member_id": row.member_id,
        "status": row.status,
        "payment_status": row.payment_status,
        "start_date": row.start_date.isoformat(),
        "end_date": row.end_date.isoformat(),
    }