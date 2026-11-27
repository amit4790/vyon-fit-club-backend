"""Phase 1.3 — scheduled renewal queue, delayed activation, multi-paused safety."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from core.membership_lifecycle import (
    ASSIGNMENT_INTENT_CONVERSION,
    ASSIGNMENT_INTENT_NEW,
    ASSIGNMENT_INTENT_RENEW,
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_EXPIRED,
    STATUS_PAUSED,
    STATUS_SCHEDULED,
    purchased_inclusive_days,
)
from models import Invoice, Member, MembershipPlan, MembershipSubscription
from schemas.invoice import CapturePaymentRequest
from services.invoice_service import InvoiceService
from services.membership_lifecycle_service import MembershipLifecycleService
from services.subscription_service import SubscriptionService


@pytest.fixture(autouse=True)
def _stub_side_effects(monkeypatch):
    monkeypatch.setattr(
        SubscriptionService,
        "_sync_device_access_for_members",
        lambda self, member_ids: None,
    )
    monkeypatch.setattr(SubscriptionService, "sync_expired_subscriptions", lambda self: None)


def _plan(db: Session, family: str = "VYON BASIC", months: int = 3, *, suffix: str = "") -> MembershipPlan:
    label = f"{family}-{months}M{suffix}"
    p = MembershipPlan(
        name=label,
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
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _member(db: Session, mobile: str) -> Member:
    m = Member(full_name=mobile, mobile_number=mobile, joined_at=date.today(), status="active")
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def test_scheduled_renew_then_conversion_preserves_scheduled_purchase(db: Session):
    """Basic + scheduled renew + PT convert + PT end + Basic resume/end → scheduled runs full term."""
    basic_plan = _plan(db, "VYON BASIC", 3)
    pt_plan = _plan(db, "VYON ADVANCE PT", 1)
    renew_plan = _plan(db, "VYON BASIC", 3, suffix="-renew")
    member = _member(db, "9300000001")
    today = date.today()
    basic_start = today - timedelta(days=60)
    basic_end = today + timedelta(days=16)

    db.add(
        MembershipSubscription(
            member_id=member.id,
            plan_id=basic_plan.id,
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
    basic = db.query(MembershipSubscription).one()
    purchased_renew_days = 90
    renew_start = basic_end + timedelta(days=1)
    renew_end = renew_start + timedelta(days=purchased_renew_days - 1)

    scheduled = MembershipSubscription(
        member_id=member.id,
        plan_id=renew_plan.id,
        start_date=renew_start,
        end_date=renew_end,
        duration_value=3,
        duration_unit="months",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="pending",
        status=STATUS_SCHEDULED,
        resume_after_subscription_id=basic.id,
        assignment_intent=ASSIGNMENT_INTENT_RENEW,
    )
    db.add(scheduled)
    db.commit()
    db.refresh(scheduled)

    pt_sub, _ = SubscriptionService(db).convert_membership(
        member_id=member.id,
        plan_id=pt_plan.id,
        start_date=today,
        duration_value=30,
        duration_unit="days",
    )
    db.refresh(basic)
    assert basic.status == STATUS_PAUSED
    assert scheduled.resume_after_subscription_id == basic.id

    lifecycle = MembershipLifecycleService(db)
    pt_row = db.get(MembershipSubscription, pt_sub.id)
    assert pt_row is not None
    pt_row.end_date = today
    lifecycle.complete_subscription_and_continue(pt_row, today=today + timedelta(days=1))
    db.commit()
    db.refresh(basic)
    assert basic.status == STATUS_ACTIVE

    basic.end_date = today + timedelta(days=16)
    lifecycle.complete_subscription_and_continue(basic, today=basic.end_date + timedelta(days=1))
    db.commit()
    db.refresh(scheduled)
    assert scheduled.status == STATUS_ACTIVE
    activated_days = purchased_inclusive_days(
        start_date=scheduled.start_date, end_date=scheduled.end_date
    )
    assert activated_days == purchased_renew_days
    assert scheduled.start_date >= renew_start


def test_multiple_scheduled_renewals_stack_and_run_sequentially(db: Session):
    plan = _plan(db)
    member = _member(db, "9300000002")
    today = date.today()
    current_end = today + timedelta(days=30)
    db.add(
        MembershipSubscription(
            member_id=member.id,
            plan_id=plan.id,
            start_date=today,
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
    )
    db.commit()

    svc = SubscriptionService(db)
    first, _ = svc.assign_subscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today,
        assignment_intent=ASSIGNMENT_INTENT_RENEW,
    )
    second, _ = svc.assign_subscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today,
        assignment_intent=ASSIGNMENT_INTENT_RENEW,
    )
    assert first.status == STATUS_SCHEDULED
    assert second.status == STATUS_SCHEDULED
    assert second.start_date == first.end_date + timedelta(days=1)
    assert first.resume_after_subscription_id is not None
    assert second.resume_after_subscription_id == first.id


def test_activate_scheduled_after_original_start_passed(db: Session):
    plan = _plan(db)
    member = _member(db, "9300000003")
    today = date(2026, 7, 1)
    predecessor_end = date(2026, 6, 30)
    purchased = 60
    sched_start = date(2026, 4, 1)
    sched_end = sched_start + timedelta(days=purchased - 1)
    pred = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=date(2026, 1, 1),
        end_date=predecessor_end,
        duration_value=6,
        duration_unit="months",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="paid",
        status=STATUS_ACTIVE,
    )
    sched = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=sched_start,
        end_date=sched_end,
        duration_value=2,
        duration_unit="months",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="pending",
        status=STATUS_SCHEDULED,
        resume_after_subscription_id=None,
    )
    db.add_all([pred, sched])
    db.commit()
    db.refresh(pred)
    db.refresh(sched)
    sched.resume_after_subscription_id = pred.id
    db.commit()

    lifecycle = MembershipLifecycleService(db)
    lifecycle.complete_subscription_and_continue(pred, today=today)
    db.commit()
    db.refresh(sched)
    assert sched.status == STATUS_ACTIVE
    assert purchased_inclusive_days(start_date=sched.start_date, end_date=sched.end_date) == purchased
    assert sched.start_date == today


def test_only_one_paused_resumes_when_duplicates_share_predecessor(db: Session):
    plan = _plan(db)
    member = _member(db, "9300000004")
    today = date.today()
    active = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today - timedelta(days=5),
        end_date=today - timedelta(days=1),
        duration_value=5,
        duration_unit="days",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="paid",
        status=STATUS_ACTIVE,
    )
    pa = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today - timedelta(days=90),
        end_date=today - timedelta(days=20),
        duration_value=30,
        duration_unit="days",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="paid",
        status=STATUS_PAUSED,
        remaining_days=20,
        resume_after_subscription_id=None,
    )
    pb = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today - timedelta(days=60),
        end_date=today - timedelta(days=20),
        duration_value=30,
        duration_unit="days",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="paid",
        status=STATUS_PAUSED,
        remaining_days=10,
        resume_after_subscription_id=None,
    )
    db.add_all([active, pa, pb])
    db.commit()
    db.refresh(active)
    pa.resume_after_subscription_id = active.id
    pb.resume_after_subscription_id = active.id
    db.commit()

    lifecycle = MembershipLifecycleService(db)
    lifecycle.complete_subscription_and_continue(active, today=today)
    db.commit()
    db.refresh(pa)
    db.refresh(pb)
    assert pa.status == STATUS_ACTIVE
    assert pb.status == STATUS_PAUSED
    assert pb.resume_after_subscription_id == pa.id

    pa.end_date = today + timedelta(days=19)
    lifecycle.complete_subscription_and_continue(pa, today=pa.end_date + timedelta(days=1))
    db.commit()
    db.refresh(pb)
    assert pb.status == STATUS_ACTIVE


def test_cancel_with_scheduled_waiting(db: Session):
    plan = _plan(db)
    member = _member(db, "9300000005")
    today = date.today()
    basic = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today - timedelta(days=60),
        end_date=today + timedelta(days=30),
        duration_value=3,
        duration_unit="months",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="paid",
        status=STATUS_PAUSED,
        remaining_days=25,
        resume_after_subscription_id=None,
    )
    pt = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today,
        end_date=today + timedelta(days=14),
        duration_value=15,
        duration_unit="days",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="paid",
        status=STATUS_ACTIVE,
    )
    sched = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today + timedelta(days=60),
        end_date=today + timedelta(days=119),
        duration_value=2,
        duration_unit="months",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="pending",
        status=STATUS_SCHEDULED,
        resume_after_subscription_id=None,
    )
    db.add_all([basic, pt, sched])
    db.commit()
    db.refresh(basic)
    db.refresh(pt)
    db.refresh(sched)
    basic.resume_after_subscription_id = pt.id
    sched.resume_after_subscription_id = basic.id
    db.commit()

    purchased = purchased_inclusive_days(start_date=sched.start_date, end_date=sched.end_date)
    SubscriptionService(db).cancel_subscription(pt.id)
    db.refresh(basic)
    db.refresh(pt)
    db.refresh(sched)
    assert pt.status == STATUS_CANCELLED
    assert basic.status == STATUS_ACTIVE
    assert sched.status == STATUS_SCHEDULED

    lifecycle = MembershipLifecycleService(db)
    basic.end_date = today
    lifecycle.complete_subscription_and_continue(basic, today=today + timedelta(days=1))
    db.commit()
    db.refresh(sched)
    assert sched.status == STATUS_ACTIVE
    assert purchased_inclusive_days(start_date=sched.start_date, end_date=sched.end_date) == purchased


def test_repeated_expiry_idempotent_on_scheduled_activation(db: Session):
    plan = _plan(db)
    member = _member(db, "9300000006")
    today = date.today()
    pred = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today - timedelta(days=10),
        end_date=today - timedelta(days=1),
        duration_value=10,
        duration_unit="days",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="paid",
        status=STATUS_ACTIVE,
    )
    sched = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today - timedelta(days=5),
        end_date=today + timedelta(days=24),
        duration_value=30,
        duration_unit="days",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="pending",
        status=STATUS_SCHEDULED,
        resume_after_subscription_id=None,
    )
    db.add_all([pred, sched])
    db.commit()
    db.refresh(pred)
    db.refresh(sched)
    sched.resume_after_subscription_id = pred.id
    db.commit()

    lifecycle = MembershipLifecycleService(db)
    lifecycle.complete_subscription_and_continue(pred, today=today)
    db.commit()
    db.refresh(sched)
    first_end = sched.end_date
    lifecycle.complete_subscription_and_continue(pred, today=today)
    db.commit()
    db.refresh(sched)
    assert sched.end_date == first_end


def test_partial_payment_then_scheduled_renew_intact(db: Session):
    plan = _plan(db)
    member = _member(db, "9300000007")
    today = date.today()
    sub, _ = SubscriptionService(db).assign_subscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today,
        assignment_intent=ASSIGNMENT_INTENT_NEW,
    )
    InvoiceService(db).capture_payment_for_subscription(
        subscription_id=sub.id,
        payload=CapturePaymentRequest(
            final_amount_received=500.0,
            amount_paid_today=200.0,
            payment_mode="cash",
        ),
    )
    renew, _ = SubscriptionService(db).assign_subscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today,
        assignment_intent=ASSIGNMENT_INTENT_RENEW,
    )
    inv = db.query(Invoice).filter_by(subscription_id=sub.id).one()
    assert inv.status == "partial"
    assert renew.status == STATUS_SCHEDULED
    assert renew.resume_after_subscription_id == sub.id