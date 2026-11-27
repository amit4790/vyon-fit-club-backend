"""Reconciliation using MembershipLifecycleService (one transaction per member)."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from core.membership_lifecycle import remaining_days_from_today
from services.membership_lifecycle_service import MembershipLifecycleService
from services.subscription_service import SubscriptionService

from rehearsal_lifecycle_execution.constants import (
    MEMBER_98_PAUSE_SUB_ID,
    MEMBER_98_PREDECESSOR_SUB_ID,
    STALE_SUBSCRIPTIONS,
)
from rehearsal_lifecycle_execution.errors import ReconciliationError, RemainingDaysError
from rehearsal_lifecycle_execution.snapshot import assert_member_98_pre_reconcile, subscription_matches_snapshot

logger = logging.getLogger(__name__)


def _subscription_map(db: Session, sub_ids: tuple[int, ...]) -> dict[int, Any]:
    from models import MembershipSubscription

    rows = db.query(MembershipSubscription).filter(MembershipSubscription.id.in_(sub_ids)).all()
    return {int(row.id): row for row in rows}


def subscription_rows_for_snapshot(db: Session, sub_ids: tuple[int, ...]) -> dict[int, dict[str, Any]]:
    from models import MembershipSubscription

    rows = db.query(MembershipSubscription).filter(MembershipSubscription.id.in_(sub_ids)).all()
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        out[int(row.id)] = {
            "id": row.id,
            "member_id": row.member_id,
            "status": row.status,
            "payment_status": row.payment_status,
            "start_date": row.start_date,
            "end_date": row.end_date,
        }
    return out


def reconcile_stale_member(db: Session, *, member_id: int, subscription_id: int, today: date) -> None:
    """Expire overdue active subscription for one member; single commit."""
    rows = subscription_rows_for_snapshot(db, (subscription_id,))
    if subscription_id not in rows:
        raise ReconciliationError(f"Subscription {subscription_id} not found")
    subscription_matches_snapshot(rows[subscription_id])
    if int(rows[subscription_id]["member_id"]) != member_id:
        raise ReconciliationError(
            f"Subscription {subscription_id} belongs to member {rows[subscription_id]['member_id']}, not {member_id}"
        )

    lifecycle = MembershipLifecycleService(db)
    try:
        lifecycle.lock_member_for_lifecycle(member_id)
        affected = SubscriptionService(db)._sync_expired_subscriptions_for_member(
            member_id,
            today,
            lifecycle=lifecycle,
        )
        if member_id not in affected and not affected:
            # Still commit if sync ran without marking member in set but row expired
            pass
        db.commit()
    except Exception:
        db.rollback()
        raise


def compute_pause_remaining_days(*, start_date: date, end_date: date, today: date) -> int:
    remaining = remaining_days_from_today(start_date=start_date, end_date=end_date, today=today)
    logger.info(
        "computed remaining_days",
        extra={
            "execution_date": today.isoformat(),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "remaining_days": remaining,
        },
    )
    if remaining <= 0:
        raise RemainingDaysError(
            f"remaining_days_from_today returned {remaining} for execution_date={today.isoformat()}; aborting"
        )
    return remaining


def reconcile_member_98_pause(db: Session, *, today: date) -> int:
    """Pause subscription 92 behind active 631; single commit. Returns computed remaining_days."""
    sub_ids = (MEMBER_98_PAUSE_SUB_ID, MEMBER_98_PREDECESSOR_SUB_ID, 507)
    rows = subscription_rows_for_snapshot(db, sub_ids)
    assert_member_98_pre_reconcile(rows)

    from models import MembershipSubscription

    basic = db.get(MembershipSubscription, MEMBER_98_PAUSE_SUB_ID)
    pro = db.get(MembershipSubscription, MEMBER_98_PREDECESSOR_SUB_ID)
    if basic is None or pro is None:
        raise ReconciliationError("Member 98 subscriptions 92 or 631 not found")
    if basic.status != "active" or pro.status != "active":
        raise ReconciliationError("Member 98: 92 and 631 must both be active before pause")

    remaining = compute_pause_remaining_days(
        start_date=basic.start_date,
        end_date=basic.end_date,
        today=today,
    )

    lifecycle = MembershipLifecycleService(db)
    try:
        lifecycle.lock_member_for_lifecycle(98)
        lifecycle.pause_subscription(
            basic,
            today=today,
            resume_after_subscription_id=pro.id,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(basic)
    if basic.resume_after_subscription_id != pro.id:
        raise ReconciliationError("Member 98: predecessor link not set after commit")
    if basic.remaining_days != remaining:
        raise ReconciliationError("Member 98: remaining_days differs from pre-commit calculation")

    return remaining


def reconcile_all_stale(db: Session, *, today: date) -> None:
    for sub_id, member_id in STALE_SUBSCRIPTIONS.items():
        reconcile_stale_member(db, member_id=member_id, subscription_id=sub_id, today=today)