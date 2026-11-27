"""Membership lifecycle: pause/resume stack, renew stacking, conversion."""

from __future__ import annotations

from datetime import date, timedelta
import pytest
from sqlalchemy.orm import Session

from core.membership_lifecycle import (
    ASSIGNMENT_INTENT_CONVERSION,
    ASSIGNMENT_INTENT_NEW,
    ASSIGNMENT_INTENT_RENEW,
    STATUS_ACTIVE,
    STATUS_EXPIRED,
    STATUS_PAUSED,
    STATUS_SCHEDULED,
    remaining_days_from_today,
)
from models import Invoice, Member, MembershipPlan, MembershipSubscription
from schemas.invoice import CapturePaymentRequest
from services.invoice_service import InvoiceService
from repositories.subscription_repository import SubscriptionRepository
from services.membership_lifecycle_service import (
    InvalidLifecycleTransitionError,
    MembershipLifecycleService,
)
from services.subscription_service import SubscriptionService


@pytest.fixture(autouse=True)
def _stub_subscription_side_effects(monkeypatch):
    monkeypatch.setattr(
        SubscriptionService,
        "_sync_device_access_for_members",
        lambda self, member_ids: None,
    )
    monkeypatch.setattr(SubscriptionService, "sync_expired_subscriptions", lambda self: None)


def _seed_plan(
    db: Session,
    *,
    family: str = "VYON BASIC",
    name: str | None = None,
    months: int = 3,
) -> MembershipPlan:
    label = name or f"{family} - {months} Months"
    plan = MembershipPlan(
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


def _service(db: Session) -> SubscriptionService:
    return SubscriptionService(db)


def test_new_membership_assignment(db: Session):
    plan = _seed_plan(db, months=1)
    member = _seed_member(db, "9100000001")

    sub, _ = _service(db).assign_subscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=date.today(),
        duration_value=1,
        duration_unit="months",
        assignment_intent=ASSIGNMENT_INTENT_NEW,
    )
    assert sub.status == STATUS_ACTIVE
    assert sub.assignment_intent == ASSIGNMENT_INTENT_NEW
    invoices = db.query(Invoice).filter(Invoice.member_id == member.id).all()
    assert len(invoices) == 1
    assert invoices[0].subscription_id == sub.id


def test_renew_does_not_pause_current_effective_membership(db: Session):
    plan = _seed_plan(db, months=1)
    member = _seed_member(db, "9100000017")
    today = date.today()
    current_end = today + timedelta(days=15)

    current = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today - timedelta(days=15),
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
    db.refresh(current)

    _service(db).assign_subscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today,
        duration_value=1,
        duration_unit="months",
        assignment_intent=ASSIGNMENT_INTENT_RENEW,
    )

    db.refresh(current)
    assert current.status == STATUS_ACTIVE
    assert current.remaining_days is None


def test_early_renewal_stacks_after_current_end(db: Session):
    plan = _seed_plan(db, months=1)
    member = _seed_member(db, "9100000002")
    today = date.today()
    current_end = today + timedelta(days=15)

    row = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today - timedelta(days=15),
        end_date=current_end,
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

    renew, _ = _service(db).assign_subscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today,
        duration_value=1,
        duration_unit="months",
        assignment_intent=ASSIGNMENT_INTENT_RENEW,
    )
    assert renew.start_date == current_end + timedelta(days=1)
    assert renew.status == STATUS_SCHEDULED


def test_conversion_pauses_basic_and_starts_new_plan(db: Session):
    basic = _seed_plan(db, family="VYON BASIC", months=3)
    advance = _seed_plan(db, family="VYON ADVANCE PT", months=1)
    member = _seed_member(db, "9100000003")
    today = date.today()
    basic_start = today - timedelta(days=30)
    basic_end = basic_start + timedelta(days=89)

    basic_row = MembershipSubscription(
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
    db.add(basic_row)
    db.commit()
    db.refresh(basic_row)

    new_sub, _ = _service(db).convert_membership(
        member_id=member.id,
        plan_id=advance.id,
        start_date=today,
        duration_value=1,
        duration_unit="months",
    )

    db.refresh(basic_row)
    assert basic_row.status == STATUS_PAUSED
    assert basic_row.resume_after_subscription_id == new_sub.id
    expected_remaining = remaining_days_from_today(
        start_date=basic_start,
        end_date=basic_end,
        today=today,
    )
    assert basic_row.remaining_days == expected_remaining
    assert new_sub.status == STATUS_ACTIVE
    assert new_sub.start_date == today


def test_resume_restores_remaining_duration(db: Session):
    plan = _seed_plan(db)
    member = _seed_member(db, "9100000004")
    today = date.today()
    lifecycle = MembershipLifecycleService(db)

    paused = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today - timedelta(days=10),
        end_date=today + timedelta(days=20),
        duration_value=1,
        duration_unit="months",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="paid",
        status=STATUS_PAUSED,
        remaining_days=15,
        resume_after_subscription_id=None,
    )
    db.add(paused)
    db.commit()
    db.refresh(paused)

    resume_on = today
    lifecycle.resume_subscription_from_pause(paused, today=resume_on)
    db.commit()

    assert paused.status == STATUS_ACTIVE
    assert paused.start_date == resume_on
    assert (paused.end_date - paused.start_date).days + 1 == 15
    assert paused.remaining_days is None


def test_two_level_nested_conversion_lifo_resume(db: Session):
    basic = _seed_plan(db, family="VYON BASIC", months=3)
    advance = _seed_plan(db, family="VYON ADVANCE PT", months=1)
    premium = _seed_plan(db, family="VYON PREMIUM PT", months=1)
    member = _seed_member(db, "9100000005")
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

    svc = _service(db)
    advance_sub, _ = svc.convert_membership(
        member_id=member.id,
        plan_id=advance.id,
        start_date=today,
        duration_value=30,
        duration_unit="days",
    )
    mid = today + timedelta(days=15)
    premium_sub, _ = svc.convert_membership(
        member_id=member.id,
        plan_id=premium.id,
        start_date=mid,
        duration_value=15,
        duration_unit="days",
    )

    lifecycle = MembershipLifecycleService(db)
    premium_row = db.get(MembershipSubscription, premium_sub.id)
    advance_row = db.get(MembershipSubscription, advance_sub.id)
    basic_row = db.query(MembershipSubscription).filter(
        MembershipSubscription.member_id == member.id,
        MembershipSubscription.plan_id == basic.id,
    ).one()

    assert basic_row.status == STATUS_PAUSED
    assert basic_row.resume_after_subscription_id == advance_row.id
    assert advance_row.status == STATUS_PAUSED
    assert advance_row.resume_after_subscription_id == premium_row.id

    premium_row.status = STATUS_ACTIVE
    premium_row.end_date = mid + timedelta(days=14)
    db.commit()

    lifecycle.complete_subscription_and_continue(premium_row, today=mid + timedelta(days=15))
    db.commit()
    db.refresh(advance_row)
    assert advance_row.status == STATUS_ACTIVE

    advance_row.end_date = advance_row.start_date + timedelta(days=14)
    lifecycle.complete_subscription_and_continue(advance_row, today=advance_row.end_date + timedelta(days=1))
    db.commit()
    db.refresh(basic_row)
    assert basic_row.status == STATUS_ACTIVE


def test_multiple_paused_subscriptions_chain(db: Session):
    plan = _seed_plan(db)
    member = _seed_member(db, "9100000006")
    active = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=date.today(),
        end_date=date.today() + timedelta(days=10),
        duration_value=10,
        duration_unit="days",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="pending",
        status=STATUS_ACTIVE,
    )
    db.add(active)
    db.commit()
    db.refresh(active)

    paused_a = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=date.today() - timedelta(days=90),
        end_date=date.today() - timedelta(days=1),
        duration_value=30,
        duration_unit="days",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="paid",
        status=STATUS_PAUSED,
        remaining_days=20,
        resume_after_subscription_id=active.id,
    )
    paused_b = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=date.today() - timedelta(days=60),
        end_date=date.today() - timedelta(days=1),
        duration_value=30,
        duration_unit="days",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="paid",
        status=STATUS_PAUSED,
        remaining_days=10,
        resume_after_subscription_id=active.id,
    )
    db.add_all([paused_a, paused_b])
    db.commit()

    waiting = svc_repo_list(db, active.id)
    assert len(waiting) == 2


def svc_repo_list(db: Session, sub_id: int) -> list[MembershipSubscription]:
    from repositories.subscription_repository import SubscriptionRepository

    return SubscriptionRepository(db).list_paused_waiting_for_subscription(sub_id)


def test_expired_membership_renew_after_sync(db: Session):
    plan = _seed_plan(db, months=1)
    member = _seed_member(db, "9100000007")
    past_end = date.today() - timedelta(days=5)
    db.add(
        MembershipSubscription(
            member_id=member.id,
            plan_id=plan.id,
            start_date=past_end - timedelta(days=30),
            end_date=past_end,
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
    expired_row = db.query(MembershipSubscription).filter(MembershipSubscription.member_id == member.id).one()
    expired_row.status = STATUS_EXPIRED
    db.commit()

    renewed, _ = _service(db).assign_subscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=date.today(),
        duration_value=1,
        duration_unit="months",
        assignment_intent=ASSIGNMENT_INTENT_RENEW,
    )
    assert renewed.status == STATUS_ACTIVE
    assert renewed.start_date == date.today()


def test_invalid_state_transition_pause_non_active(db: Session):
    plan = _seed_plan(db)
    member = _seed_member(db, "9100000008")
    row = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=date.today(),
        end_date=date.today() + timedelta(days=30),
        duration_value=1,
        duration_unit="months",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="pending",
        status=STATUS_PAUSED,
        remaining_days=10,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    lifecycle = MembershipLifecycleService(db)
    with pytest.raises(InvalidLifecycleTransitionError):
        lifecycle.pause_subscription(row, today=date.today())


def test_auto_pause_when_new_assign_with_effective_active(db: Session):
    basic = _seed_plan(db, family="VYON BASIC", months=3)
    advance = _seed_plan(db, family="VYON ADVANCE PT", months=1)
    member = _seed_member(db, "9100000009")
    today = date.today()
    basic_start = today - timedelta(days=30)
    basic_end = basic_start + timedelta(days=89)

    basic_row = MembershipSubscription(
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
    db.add(basic_row)
    db.commit()
    db.refresh(basic_row)
    expected_remaining = remaining_days_from_today(
        start_date=basic_start, end_date=basic_end, today=today
    )

    new_sub, _ = _service(db).assign_subscription(
        member_id=member.id,
        plan_id=advance.id,
        start_date=today,
        duration_value=1,
        duration_unit="months",
        assignment_intent=ASSIGNMENT_INTENT_NEW,
    )

    db.refresh(basic_row)
    assert basic_row.status == STATUS_PAUSED
    assert basic_row.remaining_days == expected_remaining
    assert basic_row.resume_after_subscription_id == new_sub.id
    assert new_sub.status == STATUS_ACTIVE


def test_assign_rollback_restores_active_if_create_fails(db: Session, monkeypatch):
    plan = _seed_plan(db)
    alt = _seed_plan(db, family="VYON ALT", months=1)
    member = _seed_member(db, "9100000014")
    first_sub, _ = _service(db).assign_subscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=date.today(),
        duration_value=1,
        duration_unit="months",
        assignment_intent=ASSIGNMENT_INTENT_NEW,
    )
    first_row = db.get(MembershipSubscription, first_sub.id)
    assert first_row is not None

    original_create = SubscriptionRepository.create_subscription

    def failing_create(self, subscription):
        raise RuntimeError("simulated persistence failure")

    monkeypatch.setattr(SubscriptionRepository, "create_subscription", failing_create)

    with pytest.raises(RuntimeError):
        _service(db).assign_subscription(
            member_id=member.id,
            plan_id=alt.id,
            start_date=date.today(),
            duration_value=1,
            duration_unit="months",
            assignment_intent=ASSIGNMENT_INTENT_NEW,
        )

    db.expire_all()
    restored = db.get(MembershipSubscription, first_row.id)
    assert restored is not None
    assert restored.status == STATUS_ACTIVE
    assert restored.remaining_days is None


def test_auto_resume_after_superseding_plan_expires(db: Session):
    basic = _seed_plan(db, family="VYON BASIC", months=3)
    advance = _seed_plan(db, family="VYON ADVANCE PT", months=1)
    member = _seed_member(db, "9100000015")
    today = date.today()

    basic_sub, _ = _service(db).assign_subscription(
        member_id=member.id,
        plan_id=basic.id,
        start_date=today - timedelta(days=5),
        duration_value=10,
        duration_unit="days",
        assignment_intent=ASSIGNMENT_INTENT_NEW,
    )
    basic_row = db.get(MembershipSubscription, basic_sub.id)
    assert basic_row is not None
    remaining_before = remaining_days_from_today(
        start_date=basic_row.start_date,
        end_date=basic_row.end_date,
        today=today,
    )

    advance_sub, _ = _service(db).assign_subscription(
        member_id=member.id,
        plan_id=advance.id,
        start_date=today,
        duration_value=5,
        duration_unit="days",
        assignment_intent=ASSIGNMENT_INTENT_NEW,
    )
    advance_row = db.get(MembershipSubscription, advance_sub.id)
    assert advance_row is not None
    db.refresh(basic_row)
    assert basic_row.status == STATUS_PAUSED
    assert basic_row.remaining_days == remaining_before

    advance_row.start_date = today - timedelta(days=6)
    advance_row.end_date = today - timedelta(days=1)
    db.commit()

    MembershipLifecycleService(db).complete_subscription_and_continue(advance_row, today=today)
    db.commit()

    db.refresh(basic_row)
    db.refresh(advance_row)
    assert advance_row.status == STATUS_EXPIRED
    assert basic_row.status == STATUS_ACTIVE
    assert (basic_row.end_date - basic_row.start_date).days + 1 == remaining_before


def test_complete_subscription_and_continue_is_idempotent(db: Session):
    plan = _seed_plan(db)
    member = _seed_member(db, "9100000016")
    today = date.today()
    lifecycle = MembershipLifecycleService(db)

    active = MembershipSubscription(
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
    paused = MembershipSubscription(
        member_id=member.id,
        plan_id=plan.id,
        start_date=today - timedelta(days=40),
        end_date=today - timedelta(days=11),
        duration_value=20,
        duration_unit="days",
        base_price=1000,
        tax_percent=5,
        tax_amount=50,
        total_amount=1050,
        payment_status="paid",
        status=STATUS_PAUSED,
        remaining_days=12,
        resume_after_subscription_id=None,
    )
    db.add_all([active, paused])
    db.commit()
    db.refresh(active)
    db.refresh(paused)
    paused.resume_after_subscription_id = active.id
    db.commit()
    db.refresh(paused)
    remaining_days = paused.remaining_days

    lifecycle.complete_subscription_and_continue(active, today=today)
    db.commit()
    db.refresh(paused)
    assert paused.status == STATUS_ACTIVE
    first_end = paused.end_date

    lifecycle.complete_subscription_and_continue(active, today=today)
    db.commit()
    db.refresh(paused)
    assert paused.status == STATUS_ACTIVE
    assert paused.end_date == first_end
    assert (paused.end_date - paused.start_date).days + 1 == remaining_days


def test_partial_payment_unchanged_after_conversion(db: Session):
    basic = _seed_plan(db, family="VYON BASIC", months=1)
    advance = _seed_plan(db, family="VYON ADVANCE PT", months=1)
    member = _seed_member(db, "9100000010")

    basic_sub, _ = _service(db).assign_subscription(
        member_id=member.id,
        plan_id=basic.id,
        start_date=date.today(),
        duration_value=1,
        duration_unit="months",
        assignment_intent=ASSIGNMENT_INTENT_NEW,
    )
    invoice = InvoiceService(db).capture_payment_for_subscription(
        subscription_id=basic_sub.id,
        payload=CapturePaymentRequest(
            final_amount_received=500.00,
            amount_paid_today=200.00,
            payment_mode="cash",
        ),
    )
    assert invoice.status == "partial"

    _service(db).convert_membership(
        member_id=member.id,
        plan_id=advance.id,
        start_date=date.today(),
        duration_value=1,
        duration_unit="months",
    )

    basic_invoice = db.query(Invoice).filter(Invoice.subscription_id == basic_sub.id).one()
    assert basic_invoice.status == "partial"
    assert float(basic_invoice.outstanding_balance or 0) > 0


def test_invoice_history_intact_on_conversion(db: Session):
    basic = _seed_plan(db, family="VYON BASIC", months=1)
    advance = _seed_plan(db, family="VYON ADVANCE PT", months=1)
    member = _seed_member(db, "9100000011")

    before_count = db.query(Invoice).count()
    basic_sub, _ = _service(db).assign_subscription(
        member_id=member.id,
        plan_id=basic.id,
        start_date=date.today(),
        assignment_intent=ASSIGNMENT_INTENT_NEW,
    )
    after_basic = db.query(Invoice).count()
    assert after_basic == before_count + 1

    _service(db).convert_membership(
        member_id=member.id,
        plan_id=advance.id,
        start_date=date.today(),
    )
    after_convert = db.query(Invoice).count()
    assert after_convert == after_basic + 1

    basic_invoice = db.query(Invoice).filter(Invoice.subscription_id == basic_sub.id).one()
    assert basic_invoice.amount == basic_invoice.amount


def test_conversion_requires_active_membership(db: Session):
    plan = _seed_plan(db)
    member = _seed_member(db, "9100000012")
    with pytest.raises(InvalidLifecycleTransitionError):
        _service(db).convert_membership(member_id=member.id, plan_id=plan.id)


def test_database_rejects_two_active_subscriptions_per_member(db: Session):
    """Partial unique index: at most one status='active' row per member."""
    from sqlalchemy.exc import IntegrityError

    plan = _seed_plan(db)
    member = _seed_member(db, "9100000013")
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
            start_date=today + timedelta(days=31),
            end_date=today + timedelta(days=60),
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
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()