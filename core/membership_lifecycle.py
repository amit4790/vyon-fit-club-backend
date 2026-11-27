"""Membership subscription lifecycle statuses and date helpers."""

from __future__ import annotations

from datetime import date, timedelta

# Stored in membership_subscriptions.status (lowercase strings, existing convention).
STATUS_ACTIVE = "active"
STATUS_PAUSED = "paused"
STATUS_SCHEDULED = "scheduled"
STATUS_EXPIRED = "expired"
STATUS_CANCELLED = "cancelled"

TERMINAL_STATUSES = frozenset({STATUS_EXPIRED, STATUS_CANCELLED})

ASSIGNMENT_INTENT_NEW = "new"
ASSIGNMENT_INTENT_RENEW = "renew"
ASSIGNMENT_INTENT_CONVERSION = "conversion"


def inclusive_day_count(start: date, end: date) -> int:
    """Inclusive calendar days between start and end."""
    return max((end - start).days + 1, 0)


def remaining_days_from_today(*, start_date: date, end_date: date, today: date) -> int:
    """
    Days not yet consumed when pausing/switching on ``today``.

    Elapsed days are counted exclusive of ``today`` (today belongs to the new plan).
    """
    total = inclusive_day_count(start_date, end_date)
    elapsed = max((today - start_date).days, 0)
    return max(total - elapsed, 0)


def purchased_inclusive_days(*, start_date: date, end_date: date) -> int:
    """Paid term length at purchase; preserved when shifting scheduled activation."""
    return inclusive_day_count(start_date, end_date)


def end_date_for_remaining_days(*, start: date, remaining_days: int) -> date:
    if remaining_days <= 0:
        return start - timedelta(days=1)
    return start + timedelta(days=remaining_days - 1)


def is_effective_active(
    *,
    status: str,
    start_date: date,
    end_date: date,
    today: date,
) -> bool:
    return (
        status == STATUS_ACTIVE
        and start_date <= today
        and end_date >= today
    )