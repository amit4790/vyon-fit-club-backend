"""Rehearsal execution constants and reviewed preflight snapshot (Phase 1.3.5/1.3.8)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

REHEARSAL_DB_HOST = "ep-blue-night-b37s7qe2-pooler.c-4.ap-southeast-1.aws.neon.tech"

REVISION_L7 = "l7m8n9o0p1q2"
REVISION_M8 = "m8n9o0p1q2r3"
REVISION_N9A = "n9o0p1q2r3s4"
REVISION_N9B = "o0p1q2r3s4t5"

SUBSCRIPTION_IDS = (92, 507, 631, 125, 141, 259, 613)
AFFECTED_MEMBER_IDS = (98, 126, 139, 244, 408)

STALE_SUBSCRIPTIONS: dict[int, int] = {
    125: 126,
    141: 139,
    259: 244,
    613: 408,
}

MEMBER_98_PAUSE_SUB_ID = 92
MEMBER_98_PREDECESSOR_SUB_ID = 631
MEMBER_98_LEAVE_EXPIRED_SUB_ID = 507


@dataclass(frozen=True)
class ReviewedSubscriptionSnapshot:
    id: int
    member_id: int
    status: str
    payment_status: str
    start_date: date
    end_date: date


REVIEWED_SUBSCRIPTION_SNAPSHOT: dict[int, ReviewedSubscriptionSnapshot] = {
    92: ReviewedSubscriptionSnapshot(
        id=92,
        member_id=98,
        status="active",
        payment_status="paid",
        start_date=date(2026, 8, 4),
        end_date=date(2026, 12, 3),
    ),
    507: ReviewedSubscriptionSnapshot(
        id=507,
        member_id=98,
        status="expired",
        payment_status="paid",
        start_date=date(2026, 10, 5),
        end_date=date(2026, 11, 4),
    ),
    631: ReviewedSubscriptionSnapshot(
        id=631,
        member_id=98,
        status="active",
        payment_status="paid",
        start_date=date(2026, 11, 5),
        end_date=date(2026, 12, 4),
    ),
    125: ReviewedSubscriptionSnapshot(
        id=125,
        member_id=126,
        status="active",
        payment_status="paid",
        start_date=date(2026, 7, 27),
        end_date=date(2026, 11, 26),
    ),
    141: ReviewedSubscriptionSnapshot(
        id=141,
        member_id=139,
        status="active",
        payment_status="paid",
        start_date=date(2026, 8, 14),
        end_date=date(2026, 11, 26),
    ),
    259: ReviewedSubscriptionSnapshot(
        id=259,
        member_id=244,
        status="active",
        payment_status="paid",
        start_date=date(2026, 8, 27),
        end_date=date(2026, 11, 26),
    ),
    613: ReviewedSubscriptionSnapshot(
        id=613,
        member_id=408,
        status="active",
        payment_status="paid",
        start_date=date(2026, 10, 27),
        end_date=date(2026, 11, 26),
    ),
}

INVOICE_IMMUTABLE_COLUMNS = frozenset(
    {
        "amount",
        "status",
        "original_price",
        "final_amount_received",
        "discount_amount",
        "discount_percentage",
        "gst_amount",
        "amount_paid_today",
        "outstanding_balance",
        "total_paid",
        "payment_mode",
        "transaction_reference",
        "payment_date",
        "counsellor",
        "notes",
        "invoice_number",
        "invoice_pdf_path",
        "paid_at",
    }
)

MEMBER_DEVICE_COLUMNS = (
    "id",
    "full_name",
    "device_user_id",
    "device_uid",
    "device_card",
    "device_sync_status",
    "device_access_enabled",
    "last_device_sync_at",
)