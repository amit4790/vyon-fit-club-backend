"""Phase 1.3.4 — member locking, transaction boundaries, cycle validation."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from core.membership_lifecycle import ASSIGNMENT_INTENT_NEW, STATUS_ACTIVE, STATUS_PAUSED
from models import MembershipSubscription
from services.membership_lifecycle_service import InvalidLifecycleTransitionError, MembershipLifecycleService
from tests.test_phase_1_3_scheduled_sequencing import _member, _plan, _stub_side_effects

pytestmark = pytest.mark.usefixtures("_stub_side_effects")


def test_three_node_cycle_rejected(db: Session):
    plan = _plan(db)
    member = _member(db, "9320000001")
    today = date.today()
    a = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today,
        end_date=today + timedelta(days=10),
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
    b = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today,
        end_date=today + timedelta(days=10),
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
    c = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today,
        end_date=today + timedelta(days=10),
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
    db.add_all([a, b, c])
    db.commit()
    db.refresh(a)
    db.refresh(b)
    db.refresh(c)

    lifecycle = MembershipLifecycleService(db)
    lifecycle.validate_and_set_resume_after(a, b.id, relation="paused_wait")
    lifecycle.validate_and_set_resume_after(b, c.id, relation="paused_wait")
    db.commit()

    with pytest.raises(InvalidLifecycleTransitionError, match="cycle"):
        lifecycle.validate_and_set_resume_after(c, a.id, relation="paused_wait")
    assert c.resume_after_subscription_id is None


def test_ab_cycle_rejected(db: Session):
    plan = _plan(db)
    member = _member(db, "9320000002")
    today = date.today()
    a = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today,
        end_date=today + timedelta(days=5),
        duration_value=5,
        duration_unit="days",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="paid",
        status=STATUS_PAUSED,
        remaining_days=3,
    )
    b = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today,
        end_date=today + timedelta(days=5),
        duration_value=5,
        duration_unit="days",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="paid",
        status=STATUS_PAUSED,
        remaining_days=2,
    )
    db.add_all([a, b])
    db.commit()
    db.refresh(a)
    db.refresh(b)

    lifecycle = MembershipLifecycleService(db)
    lifecycle.validate_and_set_resume_after(a, b.id, relation="paused_wait")
    db.commit()

    with pytest.raises(InvalidLifecycleTransitionError, match="cycle"):
        lifecycle.validate_and_set_resume_after(b, a.id, relation="paused_wait")
    assert b.resume_after_subscription_id is None


def test_assign_expiry_sync_single_transaction(db: Session, monkeypatch):
    """Assignment should not commit during in-transaction member expiry sync."""
    from services import subscription_service as submod

    plan = _plan(db)
    member = _member(db, "9320000003")
    commits: list[int] = []
    original_commit = db.commit

    def counting_commit():
        commits.append(1)
        return original_commit()

    today = date.today()
    db.add(
        MembershipSubscription(
            member_id=member.id,
            plan_id=plan.id,
            start_date=today - timedelta(days=30),
            end_date=today - timedelta(days=1),
            duration_value=30,
            duration_unit="days",
            base_price=1000,
            tax_percent=5,
            tax_amount=50,
            total_amount=1050,
            payment_status="paid",
            status=STATUS_ACTIVE,
        )
    )
    db.commit()

    monkeypatch.setattr(db, "commit", counting_commit)

    submod.SubscriptionService(db).assign_subscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today,
        assignment_intent=ASSIGNMENT_INTENT_NEW,
    )
    assert len(commits) == 1


def test_lock_member_for_lifecycle_zero_subscriptions(db: Session):
    member = _member(db, "9320000004")
    locked = MembershipLifecycleService(db).lock_member_for_lifecycle(member.id)
    assert locked.id == member.id


def test_repeated_member_sync_idempotent_scheduled_dates(db: Session):
    plan = _plan(db)
    member = _member(db, "9320000005")
    today = date.today()
    pred_end = today - timedelta(days=1)
    pred = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today - timedelta(days=15),
        end_date=pred_end,
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
        start_date=today - timedelta(days=5),
        end_date=today + timedelta(days=24),
        duration_value=30,
        duration_unit="days",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="pending",
        status="scheduled",
        resume_after_subscription_id=None,
    )
    db.add_all([pred, sched])
    db.commit()
    db.refresh(pred)
    db.refresh(sched)
    sched.resume_after_subscription_id = pred.id
    db.commit()

    svc = __import__(
        "services.subscription_service",
        fromlist=["SubscriptionService"],
    ).SubscriptionService(db)
    lifecycle = MembershipLifecycleService(db)
    lifecycle.lock_member_for_lifecycle(member.id)
    svc._sync_expired_subscriptions_for_member(member.id, today, lifecycle=lifecycle)
    db.commit()
    db.refresh(sched)
    first_end = sched.end_date

    lifecycle.lock_member_for_lifecycle(member.id)
    svc._sync_expired_subscriptions_for_member(member.id, today, lifecycle=lifecycle)
    db.commit()
    db.refresh(sched)
    assert sched.end_date == first_end


@pytest.mark.skip(reason="PostgreSQL FOR UPDATE required; SQLite does not prove row-lock concurrency")
def test_concurrent_renew_postgres_only():
    """Run against Neon/Postgres with a threaded integration harness (not in CI)."""
    pytest.skip("No PostgreSQL test database configured in this environment")


def test_corrupt_cycle_blocks_new_link(db: Session):
    plan = _plan(db)
    member = _member(db, "9320000006")
    today = date.today()
    rows = []
    for idx in range(3):
        row = MembershipSubscription(
            member_id=member.id,
            plan_id=plan.id,
            start_date=today,
            end_date=today + timedelta(days=5),
            duration_value=5,
            duration_unit="days",
            base_price=1000,
            tax_percent=5,
            tax_amount=50,
            total_amount=1050,
            payment_status="paid",
            status=STATUS_PAUSED,
            remaining_days=2,
        )
        rows.append(row)
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    rows[0].resume_after_subscription_id = rows[1].id
    rows[1].resume_after_subscription_id = rows[2].id
    rows[2].resume_after_subscription_id = rows[0].id
    db.commit()

    extra = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today,
        end_date=today + timedelta(days=5),
        duration_value=5,
        duration_unit="days",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="paid",
        status=STATUS_PAUSED,
        remaining_days=1,
    )
    db.add(extra)
    db.commit()
    db.refresh(extra)

    lifecycle = MembershipLifecycleService(db)
    with pytest.raises(InvalidLifecycleTransitionError, match="corrupt|cycle"):
        lifecycle.validate_and_set_resume_after(extra, rows[0].id, relation="paused_wait")