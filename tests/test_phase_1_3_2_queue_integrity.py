"""Phase 1.3.2 — independent renewal queues and relationship integrity."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from core.membership_lifecycle import (
    ASSIGNMENT_INTENT_RENEW,
    STATUS_ACTIVE,
    STATUS_PAUSED,
    STATUS_SCHEDULED,
    purchased_inclusive_days,
)
from models import MembershipPlan, MembershipSubscription
from services.membership_lifecycle_service import InvalidLifecycleTransitionError, MembershipLifecycleService
from services.subscription_service import SubscriptionService
from tests.test_phase_1_3_scheduled_sequencing import (
    _member,
    _plan,
    _stub_side_effects,
)

pytestmark = pytest.mark.usefixtures("_stub_side_effects")


def test_advance_renew_ignores_basic_scheduled_after_conversion(db: Session):
    """Advance PT renew must anchor on PT, not an unrelated scheduled Basic renewal."""
    basic_plan = _plan(db, "VYON BASIC", 3)
    pt_plan = _plan(db, "VYON ADVANCE PT", 1)
    renew_plan = _plan(db, "VYON BASIC", 3, suffix="-renew")
    member = _member(db, "9310000001")
    today = date.today()
    basic_start = today - timedelta(days=60)
    basic_end = today + timedelta(days=16)

    basic = MembershipSubscription(
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
    db.add(basic)
    db.commit()
    db.refresh(basic)

    renew_start = basic_end + timedelta(days=1)
    renew_end = renew_start + timedelta(days=89)
    scheduled_basic = MembershipSubscription(
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
    db.add(scheduled_basic)
    db.commit()

    pt_sub, _ = SubscriptionService(db).convert_membership(
        member_id=member.id,
        plan_id=pt_plan.id,
        start_date=today,
        duration_value=30,
        duration_unit="days",
    )
    db.refresh(basic)
    pt_row = db.get(MembershipSubscription, pt_sub.id)
    assert pt_row is not None

    pt_renew_start = pt_row.end_date + timedelta(days=1)
    pt_renew_resp, _ = SubscriptionService(db).assign_subscription(
        member_id=member.id,
        plan_id=pt_plan.id,
        start_date=pt_renew_start,
        assignment_intent=ASSIGNMENT_INTENT_RENEW,
        duration_value=30,
        duration_unit="days",
    )
    pt_renew = db.get(MembershipSubscription, pt_renew_resp.id)
    assert pt_renew is not None
    assert pt_renew.status == STATUS_SCHEDULED
    assert pt_renew.start_date == pt_renew_start
    assert pt_renew.resume_after_subscription_id == pt_row.id
    assert pt_renew.resume_after_subscription_id != scheduled_basic.id


def test_renew_basic_after_resume_uses_basic_queue(db: Session):
    basic_plan = _plan(db, "VYON BASIC", 1)
    pt_plan = _plan(db, "VYON ADVANCE PT", 1)
    member = _member(db, "9310000002")
    today = date.today()
    svc = SubscriptionService(db)

    basic_resp, _ = svc.assign_subscription(
        member_id=member.id,
        plan_id=basic_plan.id,
        start_date=today - timedelta(days=20),
        assignment_intent="new",
        duration_value=1,
        duration_unit="months",
    )
    basic = db.get(MembershipSubscription, basic_resp.id)
    assert basic is not None
    basic.end_date = today + timedelta(days=5)
    db.commit()

    sched_resp, _ = svc.assign_subscription(
        member_id=member.id,
        plan_id=basic_plan.id,
        start_date=today,
        assignment_intent=ASSIGNMENT_INTENT_RENEW,
    )
    scheduled_basic = db.get(MembershipSubscription, sched_resp.id)
    assert scheduled_basic is not None

    pt_resp, _ = svc.convert_membership(
        member_id=member.id,
        plan_id=pt_plan.id,
        start_date=today,
        duration_value=14,
        duration_unit="days",
    )
    lifecycle = MembershipLifecycleService(db)
    pt_row = db.get(MembershipSubscription, pt_resp.id)
    assert pt_row is not None
    pt_row.end_date = today - timedelta(days=1)
    lifecycle.complete_subscription_and_continue(pt_row, today=today)
    db.commit()
    db.refresh(basic)
    assert basic.status == STATUS_ACTIVE

    anchor = lifecycle.get_renewal_stack_anchor(member.id, today)
    assert anchor is not None
    assert anchor.id == scheduled_basic.id

    stack_start = scheduled_basic.end_date + timedelta(days=1)
    second_renew_resp, _ = svc.assign_subscription(
        member_id=member.id,
        plan_id=basic_plan.id,
        start_date=stack_start,
        assignment_intent=ASSIGNMENT_INTENT_RENEW,
    )
    second_renew = db.get(MembershipSubscription, second_renew_resp.id)
    assert second_renew is not None
    assert second_renew.status == STATUS_SCHEDULED
    assert second_renew.start_date == stack_start
    assert second_renew.resume_after_subscription_id == scheduled_basic.id


def test_duplicate_paused_bothEventually_resumable(db: Session):
    plan = _plan(db)
    member = _member(db, "9310000003")
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
        paused_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
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
        paused_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
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
    assert pb.remaining_days == 10

    pa.end_date = today + timedelta(days=19)
    lifecycle.complete_subscription_and_continue(pa, today=pa.end_date + timedelta(days=1))
    db.commit()
    db.refresh(pb)
    assert pb.status == STATUS_ACTIVE
    assert pb.remaining_days is None


def test_three_scheduled_siblings_activate_in_order(db: Session):
    plan = _plan(db)
    member = _member(db, "9310000004")
    today = date.today()
    pred_end = today + timedelta(days=10)
    pred = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today,
        end_date=pred_end,
        duration_value=10,
        duration_unit="days",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="paid",
        status=STATUS_ACTIVE,
    )
    db.add(pred)
    db.commit()
    db.refresh(pred)

    def _sched(label_suffix: str, purch: int, created: datetime) -> MembershipSubscription:
        start = pred_end + timedelta(days=1)
        row = MembershipSubscription(
            member_id=member.id,
            plan_id=plan.id,
            start_date=start,
            end_date=start + timedelta(days=purch - 1),
            duration_value=purch,
            duration_unit="days",
            base_price=1000,
            tax_percent=5,
            tax_amount=50,
            total_amount=1050,
            payment_status="pending",
            status=STATUS_SCHEDULED,
            resume_after_subscription_id=pred.id,
            assignment_intent=ASSIGNMENT_INTENT_RENEW,
        )
        db.add(row)
        db.flush()
        row.created_at = created
        return row

    s1 = _sched("a", 30, datetime(2026, 3, 1, tzinfo=timezone.utc))
    s2 = _sched("b", 45, datetime(2026, 3, 2, tzinfo=timezone.utc))
    s3 = _sched("c", 60, datetime(2026, 3, 3, tzinfo=timezone.utc))
    db.commit()
    db.refresh(s1)
    db.refresh(s2)
    db.refresh(s3)

    lifecycle = MembershipLifecycleService(db)
    lifecycle.complete_subscription_and_continue(pred, today=pred_end + timedelta(days=1))
    db.commit()
    db.refresh(s1)
    db.refresh(s2)
    db.refresh(s3)
    assert s1.status == STATUS_ACTIVE
    assert s2.status == STATUS_SCHEDULED
    assert s3.status == STATUS_SCHEDULED
    assert s2.resume_after_subscription_id == s1.id
    assert s3.resume_after_subscription_id == s2.id

    days1 = purchased_inclusive_days(start_date=s1.start_date, end_date=s1.end_date)
    s1.end_date = s1.start_date + timedelta(days=days1 - 1)
    lifecycle.complete_subscription_and_continue(s1, today=s1.end_date + timedelta(days=1))
    db.commit()
    db.refresh(s2)
    assert s2.status == STATUS_ACTIVE
    days2 = purchased_inclusive_days(start_date=s2.start_date, end_date=s2.end_date)
    assert days2 == 45


def test_nested_conversions_renew_anchors_on_current_effective_line(db: Session):
    basic_plan = _plan(db, "VYON BASIC", 1)
    adv_plan = _plan(db, "VYON ADVANCE", 1)
    prem_plan = _plan(db, "VYON PREMIUM", 1)
    member = _member(db, "9310000007")
    today = date.today()
    svc = SubscriptionService(db)
    svc.assign_subscription(
        member_id=member.id,
        plan_id=basic_plan.id,
        start_date=today - timedelta(days=10),
        assignment_intent="new",
    )
    svc.assign_subscription(
        member_id=member.id,
        plan_id=basic_plan.id,
        start_date=today + timedelta(days=60),
        assignment_intent=ASSIGNMENT_INTENT_RENEW,
    )
    adv_resp, _ = svc.convert_membership(
        member_id=member.id,
        plan_id=adv_plan.id,
        start_date=today,
        duration_value=15,
        duration_unit="days",
    )
    adv = db.get(MembershipSubscription, adv_resp.id)
    assert adv is not None
    prem_resp, _ = svc.convert_membership(
        member_id=member.id,
        plan_id=prem_plan.id,
        start_date=today,
        duration_value=10,
        duration_unit="days",
    )
    prem = db.get(MembershipSubscription, prem_resp.id)
    assert prem is not None

    lifecycle = MembershipLifecycleService(db)
    anchor_before = lifecycle.get_renewal_stack_anchor(member.id, today)
    assert anchor_before is not None
    assert anchor_before.id == prem.id

    prem_renew_start = prem.end_date + timedelta(days=1)
    assert prem_renew_start > today
    renew_resp, _ = svc.assign_subscription(
        member_id=member.id,
        plan_id=prem_plan.id,
        start_date=prem_renew_start,
        assignment_intent=ASSIGNMENT_INTENT_RENEW,
        duration_value=10,
        duration_unit="days",
    )
    prem_renew = db.get(MembershipSubscription, renew_resp.id)
    assert prem_renew is not None
    assert prem_renew.status == STATUS_SCHEDULED
    assert prem_renew.resume_after_subscription_id == prem.id


def test_cross_member_resume_after_rejected(db: Session):
    plan = _plan(db)
    m1 = _member(db, "9310000005")
    m2 = _member(db, "9310000006")
    sub1 = MembershipSubscription(
        member_id=m1.id,
        plan_id=plan.id,
        start_date=date.today(),
        end_date=date.today() + timedelta(days=10),
        duration_value=10,
        duration_unit="days",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="paid",
        status=STATUS_ACTIVE,
    )
    sub2 = MembershipSubscription(
        member_id=m2.id,
        plan_id=plan.id,
        start_date=date.today(),
        end_date=date.today() + timedelta(days=10),
        duration_value=10,
        duration_unit="days",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="paid",
        status=STATUS_PAUSED,
        remaining_days=5,
    )
    db.add_all([sub1, sub2])
    db.commit()
    with pytest.raises(InvalidLifecycleTransitionError, match="same member"):
        MembershipLifecycleService(db).validate_and_set_resume_after(
            sub2,
            sub1.id,
            relation="paused_wait",
        )