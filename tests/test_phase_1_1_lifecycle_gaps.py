"""Phase 1.1 — P0 lifecycle gap fixes (add plan intent, change plan, cancel)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.membership_lifecycle import (
    ASSIGNMENT_INTENT_NEW,
    ASSIGNMENT_INTENT_RENEW,
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_PAUSED,
    STATUS_SCHEDULED,
    remaining_days_from_today,
)
from models import Invoice, Member, MembershipPlan, MembershipSubscription
from schemas.invoice import CapturePaymentRequest
from services.invoice_service import InvoiceService
from services.membership_lifecycle_service import MembershipLifecycleService
from services.subscription_service import SubscriptionConflictError, SubscriptionService


@pytest.fixture(autouse=True)
def _stub_device_sync(monkeypatch):
    monkeypatch.setattr(
        SubscriptionService,
        "_sync_device_access_for_members",
        lambda self, member_ids: None,
    )
    monkeypatch.setattr(SubscriptionService, "sync_expired_subscriptions", lambda self: None)


def _seed_plan(db: Session, family: str = "VYON BASIC", months: int = 1) -> MembershipPlan:
    plan = MembershipPlan(
        name=f"{family} - {months}M",
        family_name=family,
        variant_name=None,
        duration_months=months,
        duration_label=f"{months} Months",
        duration_days=months * 30,
        base_price=1000,
        tax_percent=5,
        total_price=1050,
        price=1050,
        is_active=True,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def _seed_member(db: Session, mobile: str) -> Member:
    member = Member(
        full_name=f"Member {mobile}",
        mobile_number=mobile,
        joined_at=date.today(),
        status="active",
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def test_add_plan_intent_new_pauses_effective_membership(db: Session):
    basic = _seed_plan(db, family="VYON BASIC", months=3)
    advance = _seed_plan(db, family="VYON ADVANCE PT", months=1)
    member = _seed_member(db, "9200000001")
    today = date.today()
    basic_start = today - timedelta(days=10)
    basic_end = basic_start + timedelta(days=89)
    db.add(
        MembershipSubscription(
            member_id=member.id,
            plan_id=basic.id,
            start_date=basic_start,
            end_date=basic_end,
            duration_value=3,
            duration_unit="months",
            base_price=1000,
            tax_percent=5,
            tax_amount=50,
            total_amount=1050,
            payment_status="paid",
            status=STATUS_ACTIVE,
        )
    )
    db.commit()
    basic_row = db.query(MembershipSubscription).filter_by(member_id=member.id, plan_id=basic.id).one()

    new_sub, _ = SubscriptionService(db).assign_subscription(
        member_id=member.id,
        plan_id=advance.id,
        start_date=today,
        duration_value=1,
        duration_unit="months",
        assignment_intent=ASSIGNMENT_INTENT_NEW,
    )
    db.refresh(basic_row)
    assert basic_row.status == STATUS_PAUSED
    assert basic_row.resume_after_subscription_id == new_sub.id
    assert new_sub.status == STATUS_ACTIVE


def test_renew_still_stacks_without_pause(db: Session):
    plan = _seed_plan(db)
    member = _seed_member(db, "9200000002")
    today = date.today()
    current_end = today + timedelta(days=20)
    current = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today - timedelta(days=10),
        end_date=current_end,
        duration_value=1,
        duration_unit="months",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="paid",
        status=STATUS_ACTIVE,
    )
    db.add(current)
    db.commit()

    renew, _ = SubscriptionService(db).assign_subscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today,
        assignment_intent=ASSIGNMENT_INTENT_RENEW,
    )
    db.refresh(current)
    assert current.status == STATUS_ACTIVE
    assert renew.start_date == current_end + timedelta(days=1)
    assert renew.status == STATUS_SCHEDULED


def test_change_plan_tier_on_effective_requires_conversion(db: Session):
    basic = _seed_plan(db, family="VYON BASIC")
    advance = _seed_plan(db, family="VYON ADVANCE PT")
    member = _seed_member(db, "9200000003")
    today = date.today()
    row = MembershipSubscription(
        member_id=member.id,
        plan_id=basic.id,
        start_date=today,
        end_date=today + timedelta(days=30),
        duration_value=1,
        duration_unit="months",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="pending",
        status=STATUS_ACTIVE,
    )
    db.add(row)
    db.commit()

    svc = SubscriptionService(db)
    with pytest.raises(SubscriptionConflictError):
        svc.change_subscription_plan(subscription_id=row.id, plan_id=advance.id)

    conv, _ = svc.convert_membership(
        member_id=member.id,
        plan_id=advance.id,
        start_date=today,
        duration_value=1,
        duration_unit="months",
    )
    db.refresh(row)
    assert row.status == STATUS_PAUSED
    assert conv.status == STATUS_ACTIVE


def test_change_plan_preserves_remaining_days_via_convert(db: Session):
    basic = _seed_plan(db, family="VYON BASIC", months=3)
    advance = _seed_plan(db, family="VYON ADVANCE PT")
    member = _seed_member(db, "9200000004")
    today = date.today()
    basic_start = today - timedelta(days=30)
    basic_end = basic_start + timedelta(days=89)
    db.add(
        MembershipSubscription(
            member_id=member.id,
            plan_id=basic.id,
            start_date=basic_start,
            end_date=basic_end,
            duration_value=3,
            duration_unit="months",
            base_price=1000,
            tax_percent=5,
            tax_amount=50,
            total_amount=1050,
            payment_status="paid",
            status=STATUS_ACTIVE,
        )
    )
    db.commit()
    basic_row = db.query(MembershipSubscription).one()
    expected = remaining_days_from_today(
        start_date=basic_start, end_date=basic_end, today=today
    )

    SubscriptionService(db).convert_membership(
        member_id=member.id,
        plan_id=advance.id,
        start_date=today,
        duration_value=1,
        duration_unit="months",
    )
    db.refresh(basic_row)
    assert basic_row.remaining_days == expected


def test_convert_invoice_history_intact(db: Session):
    basic = _seed_plan(db)
    advance = _seed_plan(db, family="VYON ALT")
    member = _seed_member(db, "9200000005")
    today = date.today()

    sub, _ = SubscriptionService(db).assign_subscription(
        member_id=member.id,
        plan_id=basic.id,
        start_date=today,
        assignment_intent=ASSIGNMENT_INTENT_NEW,
    )
    invoices_before = db.query(Invoice).filter_by(subscription_id=sub.id).count()

    SubscriptionService(db).convert_membership(
        member_id=member.id,
        plan_id=advance.id,
        start_date=today,
    )
    invoices_after_basic = db.query(Invoice).filter_by(subscription_id=sub.id).count()
    assert invoices_after_basic == invoices_before


def test_cancel_pt_resumes_paused_basic(db: Session):
    basic = _seed_plan(db, family="VYON BASIC")
    pt = _seed_plan(db, family="VYON ADVANCE PT")
    member = _seed_member(db, "9200000006")
    today = date.today()
    svc = SubscriptionService(db)
    basic_sub, _ = svc.assign_subscription(
        member_id=member.id,
        plan_id=basic.id,
        start_date=today - timedelta(days=30),
        duration_value=90,
        duration_unit="days",
        assignment_intent=ASSIGNMENT_INTENT_NEW,
    )
    pt_sub, _ = svc.convert_membership(
        member_id=member.id,
        plan_id=pt.id,
        start_date=today,
        duration_value=30,
        duration_unit="days",
    )
    basic_row = db.get(MembershipSubscription, basic_sub.id)
    pt_row = db.get(MembershipSubscription, pt_sub.id)
    assert basic_row is not None and pt_row is not None
    assert basic_row.status == STATUS_PAUSED

    SubscriptionService(db).cancel_subscription(pt_row.id)
    db.refresh(basic_row)
    db.refresh(pt_row)
    assert pt_row.status == STATUS_CANCELLED
    assert basic_row.status == STATUS_ACTIVE


def test_nested_cancel_resumes_immediate_predecessor_only(db: Session):
    basic = _seed_plan(db, family="VYON BASIC")
    mid = _seed_plan(db, family="VYON MID PT")
    top = _seed_plan(db, family="VYON TOP PT")
    member = _seed_member(db, "9200000007")
    today = date.today()
    svc = SubscriptionService(db)
    basic_sub, _ = svc.assign_subscription(
        member_id=member.id,
        plan_id=basic.id,
        start_date=today - timedelta(days=60),
        duration_value=90,
        duration_unit="days",
        assignment_intent=ASSIGNMENT_INTENT_NEW,
    )
    mid_sub, _ = svc.convert_membership(
        member_id=member.id,
        plan_id=mid.id,
        start_date=today - timedelta(days=10),
        duration_value=30,
        duration_unit="days",
    )
    top_sub, _ = svc.convert_membership(
        member_id=member.id,
        plan_id=top.id,
        start_date=today,
        duration_value=15,
        duration_unit="days",
    )
    basic_row = db.get(MembershipSubscription, basic_sub.id)
    mid_row = db.get(MembershipSubscription, mid_sub.id)
    top_row = db.get(MembershipSubscription, top_sub.id)
    assert basic_row is not None and mid_row is not None and top_row is not None

    SubscriptionService(db).cancel_subscription(top_row.id)
    db.refresh(mid_row)
    db.refresh(basic_row)
    assert top_row.status == STATUS_CANCELLED
    assert mid_row.status == STATUS_ACTIVE
    assert basic_row.status == STATUS_PAUSED


def test_repeated_cancel_is_idempotent(db: Session):
    plan = _seed_plan(db)
    member = _seed_member(db, "9200000008")
    today = date.today()
    sub, _ = SubscriptionService(db).assign_subscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today,
        assignment_intent=ASSIGNMENT_INTENT_NEW,
    )
    svc = SubscriptionService(db)
    first = svc.cancel_subscription(sub.id)
    assert first.status == STATUS_CANCELLED
    second = svc.cancel_subscription(sub.id)
    assert second.status == STATUS_CANCELLED


def test_change_plan_same_tier_correction_allowed(db: Session):
    plan = _seed_plan(db)
    member = _seed_member(db, "9200000009")
    today = date.today()
    row = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today,
        end_date=today + timedelta(days=25),
        duration_value=1,
        duration_unit="months",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="pending",
        status=STATUS_ACTIVE,
    )
    db.add(row)
    db.commit()

    updated = SubscriptionService(db).change_subscription_plan(
        subscription_id=row.id,
        plan_id=plan.id,
        duration_value=2,
        duration_unit="months",
    )
    assert updated.duration_value == 2


def test_cannot_reactivate_expired_while_other_active(db: Session):
    plan = _seed_plan(db)
    alt = _seed_plan(db, family="VYON ALT")
    member = _seed_member(db, "9200000010")
    today = date.today()
    active = MembershipSubscription(
        member_id=member.id,
        plan_id=alt.id,
        start_date=today,
        end_date=today + timedelta(days=30),
        duration_value=1,
        duration_unit="months",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="paid",
        status=STATUS_ACTIVE,
    )
    expired = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today - timedelta(days=60),
        end_date=today - timedelta(days=1),
        duration_value=1,
        duration_unit="months",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="paid",
        status="expired",
    )
    db.add_all([active, expired])
    db.commit()

    with pytest.raises(SubscriptionConflictError):
        SubscriptionService(db).change_subscription_plan(
            subscription_id=expired.id,
            plan_id=plan.id,
            duration_value=1,
            duration_unit="months",
        )


def test_duplicate_active_blocked_by_index(db: Session):
    plan = _seed_plan(db)
    member = _seed_member(db, "9200000011")
    today = date.today()
    db.add(
        MembershipSubscription(
            member_id=member.id,
            plan_id=plan.id,
            start_date=today,
            end_date=today + timedelta(days=30),
            duration_value=1,
            duration_unit="months",
            base_price=1000,
            tax_percent=5,
            tax_amount=50,
            total_amount=1050,
            payment_status="pending",
            status=STATUS_ACTIVE,
        )
    )
    db.commit()
    db.add(
        MembershipSubscription(
            member_id=member.id,
            plan_id=plan.id,
            start_date=today,
            end_date=today + timedelta(days=60),
            duration_value=2,
            duration_unit="months",
            base_price=1000,
            tax_percent=5,
            tax_amount=50,
            total_amount=1050,
            payment_status="pending",
            status=STATUS_ACTIVE,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_partial_payment_unaffected(db: Session):
    basic = _seed_plan(db)
    advance = _seed_plan(db, family="VYON ALT")
    member = _seed_member(db, "9200000012")
    sub, _ = SubscriptionService(db).assign_subscription(
        member_id=member.id,
        plan_id=basic.id,
        start_date=date.today(),
        assignment_intent=ASSIGNMENT_INTENT_NEW,
    )
    inv = InvoiceService(db).capture_payment_for_subscription(
        subscription_id=sub.id,
        payload=CapturePaymentRequest(
            final_amount_received=500.0,
            amount_paid_today=200.0,
            payment_mode="cash",
        ),
    )
    assert inv.status == "partial"
    SubscriptionService(db).convert_membership(
        member_id=member.id,
        plan_id=advance.id,
        start_date=date.today(),
    )
    basic_invoice = db.query(Invoice).filter_by(subscription_id=sub.id).one()
    assert basic_invoice.status == "partial"