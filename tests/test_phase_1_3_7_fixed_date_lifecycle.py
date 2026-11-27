"""Phase 1.3.7 — fixed-date lifecycle regression (member 98 / subscription 92 semantics)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from core.membership_lifecycle import (
    STATUS_ACTIVE,
    STATUS_EXPIRED,
    STATUS_PAUSED,
    end_date_for_remaining_days,
    inclusive_day_count,
    remaining_days_from_today,
)
from models import Member, MembershipPlan, MembershipSubscription
from services.membership_lifecycle_service import (
    InvalidLifecycleTransitionError,
    MembershipLifecycleService,
)

# Subscription 92 reference term (rehearsal audit).
SUB_92_START = date(2026, 8, 4)
SUB_92_END = date(2026, 12, 3)
PAUSE_2026_11_27 = date(2026, 11, 27)
RESUME_2026_12_05 = date(2026, 12, 5)


def _seed_plan(db: Session) -> MembershipPlan:
    plan = MembershipPlan(
        name="VYON BASIC - 3 Months",
        family_name="VYON BASIC",
        variant_name=None,
        duration_months=3,
        duration_label="3 Months",
        duration_days=90,
        base_price=7000,
        tax_percent=5,
        total_price=7350,
        price=7350,
        is_active=True,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def _seed_member(db: Session) -> Member:
    member = Member(
        full_name="Fixed Date Member",
        mobile_number="9399000098",
        joined_at=SUB_92_START,
        status="active",
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def _sub_92_row(*, member_id: int, plan_id: int, status: str = STATUS_ACTIVE) -> MembershipSubscription:
    return MembershipSubscription(
        member_id=member_id,
        plan_id=plan_id,
        start_date=SUB_92_START,
        end_date=SUB_92_END,
        duration_value=3,
        duration_unit="months",
        base_price=7000,
        tax_percent=5,
        tax_amount=350,
        total_amount=7350,
        payment_status="paid",
        status=status,
    )


class TestSub92FixedDateHelpers:
    def test_purchased_inclusive_days_122(self) -> None:
        assert inclusive_day_count(SUB_92_START, SUB_92_END) == 122

    def test_remaining_days_on_pause_2026_11_27(self) -> None:
        assert (
            remaining_days_from_today(
                start_date=SUB_92_START,
                end_date=SUB_92_END,
                today=PAUSE_2026_11_27,
            )
            == 7
        )

    def test_resume_end_date_2026_12_05(self) -> None:
        end = end_date_for_remaining_days(start=RESUME_2026_12_05, remaining_days=7)
        assert end == date(2026, 12, 11)
        assert inclusive_day_count(RESUME_2026_12_05, end) == 7

    def test_resume_on_pause_date_restores_original_end(self) -> None:
        remaining = 7
        end = end_date_for_remaining_days(start=PAUSE_2026_11_27, remaining_days=remaining)
        assert end == SUB_92_END

    def test_remaining_on_subscription_end_date_one_day(self) -> None:
        end_date = date(2026, 12, 3)
        assert (
            remaining_days_from_today(
                start_date=SUB_92_START,
                end_date=SUB_92_END,
                today=end_date,
            )
            == 1
        )

    def test_remaining_after_subscription_end_date_zero(self) -> None:
        assert (
            remaining_days_from_today(
                start_date=SUB_92_START,
                end_date=SUB_92_END,
                today=date(2026, 12, 4),
            )
            == 0
        )


class TestSub92PauseResumeService:
    def test_pause_2026_11_27_sets_remaining_seven(self, db: Session) -> None:
        plan = _seed_plan(db)
        member = _seed_member(db)
        basic = _sub_92_row(member_id=member.id, plan_id=plan.id)
        db.add(basic)
        db.commit()
        db.refresh(basic)

        MembershipLifecycleService(db).pause_subscription(
            basic,
            today=PAUSE_2026_11_27,
            resume_after_subscription_id=None,
        )
        db.commit()
        db.refresh(basic)

        assert basic.status == STATUS_PAUSED
        assert basic.remaining_days == 7

    def test_paused_basic_links_to_active_pro_predecessor(self, db: Session) -> None:
        """Member 98 target shape: paused 92 waiting on active 631 (one active per member)."""
        plan = _seed_plan(db)
        member = _seed_member(db)
        pro = MembershipSubscription(
            member_id=member.id,
            plan_id=plan.id,
            start_date=date(2026, 11, 5),
            end_date=date(2026, 12, 4),
            duration_value=1,
            duration_unit="months",
            base_price=12000,
            tax_percent=5,
            tax_amount=600,
            total_amount=12600,
            payment_status="paid",
            status=STATUS_ACTIVE,
        )
        basic = _sub_92_row(member_id=member.id, plan_id=plan.id, status=STATUS_PAUSED)
        basic.remaining_days = 7
        db.add_all([pro, basic])
        db.commit()
        db.refresh(basic)
        db.refresh(pro)

        lifecycle = MembershipLifecycleService(db)
        lifecycle.lock_member_for_lifecycle(member.id)
        lifecycle.validate_and_set_resume_after(basic, pro.id, relation="paused_wait")
        db.commit()
        db.refresh(basic)

        assert basic.resume_after_subscription_id == pro.id
        assert pro.status == STATUS_ACTIVE

    def test_resume_2026_12_05_seven_inclusive_days(self, db: Session) -> None:
        plan = _seed_plan(db)
        member = _seed_member(db)
        paused = _sub_92_row(member_id=member.id, plan_id=plan.id, status=STATUS_PAUSED)
        paused.remaining_days = 7
        db.add(paused)
        db.commit()
        db.refresh(paused)

        MembershipLifecycleService(db).resume_subscription_from_pause(paused, today=RESUME_2026_12_05)
        db.commit()
        db.refresh(paused)

        assert paused.status == STATUS_ACTIVE
        assert paused.start_date == RESUME_2026_12_05
        assert paused.end_date == date(2026, 12, 11)
        assert inclusive_day_count(paused.start_date, paused.end_date) == 7

    def test_resume_on_pause_date_original_end(self, db: Session) -> None:
        plan = _seed_plan(db)
        member = _seed_member(db)
        paused = _sub_92_row(member_id=member.id, plan_id=plan.id, status=STATUS_PAUSED)
        paused.remaining_days = 7
        db.add(paused)
        db.commit()
        db.refresh(paused)

        MembershipLifecycleService(db).resume_subscription_from_pause(paused, today=PAUSE_2026_11_27)
        db.commit()
        db.refresh(paused)

        assert paused.end_date == SUB_92_END
        assert inclusive_day_count(paused.start_date, paused.end_date) == 7

    def test_pause_on_end_date_remaining_one(self, db: Session) -> None:
        plan = _seed_plan(db)
        member = _seed_member(db)
        basic = _sub_92_row(member_id=member.id, plan_id=plan.id)
        db.add(basic)
        db.commit()
        db.refresh(basic)

        on_end = date(2026, 12, 3)
        MembershipLifecycleService(db).pause_subscription(basic, today=on_end, resume_after_subscription_id=None)
        db.commit()
        db.refresh(basic)

        assert basic.remaining_days == 1

    def test_pause_after_end_date_remaining_zero(self, db: Session) -> None:
        plan = _seed_plan(db)
        member = _seed_member(db)
        basic = _sub_92_row(member_id=member.id, plan_id=plan.id)
        db.add(basic)
        db.commit()
        db.refresh(basic)

        MembershipLifecycleService(db).pause_subscription(
            basic,
            today=date(2026, 12, 4),
            resume_after_subscription_id=None,
        )
        db.commit()
        db.refresh(basic)

        assert basic.remaining_days == 0

    def test_resume_zero_remaining_expires(self, db: Session) -> None:
        plan = _seed_plan(db)
        member = _seed_member(db)
        paused = _sub_92_row(member_id=member.id, plan_id=plan.id, status=STATUS_PAUSED)
        paused.remaining_days = 0
        db.add(paused)
        db.commit()
        db.refresh(paused)

        MembershipLifecycleService(db).resume_subscription_from_pause(paused, today=date(2026, 12, 4))
        db.commit()
        db.refresh(paused)

        assert paused.status == STATUS_EXPIRED

    def test_repeated_pause_resume_cycle_preserves_counts(self, db: Session) -> None:
        plan = _seed_plan(db)
        member = _seed_member(db)
        basic = _sub_92_row(member_id=member.id, plan_id=plan.id)
        db.add(basic)
        db.commit()
        db.refresh(basic)

        lifecycle = MembershipLifecycleService(db)
        lifecycle.pause_subscription(basic, today=PAUSE_2026_11_27)
        db.commit()
        assert basic.remaining_days == 7

        lifecycle.resume_subscription_from_pause(basic, today=RESUME_2026_12_05)
        db.commit()
        assert inclusive_day_count(basic.start_date, basic.end_date) == 7

        second_pause = date(2026, 12, 8)
        lifecycle.pause_subscription(basic, today=second_pause)
        db.commit()
        expected = remaining_days_from_today(
            start_date=RESUME_2026_12_05,
            end_date=date(2026, 12, 11),
            today=second_pause,
        )
        assert basic.remaining_days == expected
        assert expected == 4

    def test_idempotent_complete_and_resume_unchanged_end(self, db: Session) -> None:
        plan = _seed_plan(db)
        member = _seed_member(db)
        today = date(2026, 11, 5)
        active = MembershipSubscription(
            member_id=member.id,
            plan_id=plan.id,
            start_date=today,
            end_date=today,
            duration_value=1,
            duration_unit="days",
            base_price=1000,
            tax_percent=5,
            tax_amount=50,
            total_amount=1050,
            payment_status="paid",
            status=STATUS_ACTIVE,
        )
        paused = _sub_92_row(member_id=member.id, plan_id=plan.id, status=STATUS_PAUSED)
        paused.remaining_days = 7
        paused.resume_after_subscription_id = None
        db.add_all([active, paused])
        db.commit()
        db.refresh(active)
        db.refresh(paused)
        paused.resume_after_subscription_id = active.id
        db.commit()
        db.refresh(paused)

        lifecycle = MembershipLifecycleService(db)
        lifecycle.complete_subscription_and_continue(active, today=date(2026, 11, 6))
        db.commit()
        first_end = paused.end_date

        lifecycle.complete_subscription_and_continue(active, today=date(2026, 11, 6))
        db.commit()
        db.refresh(paused)

        assert paused.status == STATUS_ACTIVE
        assert paused.end_date == first_end
        assert inclusive_day_count(paused.start_date, paused.end_date) == 7

    def test_failed_link_rolls_back_predecessor(self, db: Session) -> None:
        plan = _seed_plan(db)
        member = _seed_member(db)
        terminal = MembershipSubscription(
            member_id=member.id,
            plan_id=plan.id,
            start_date=date(2026, 10, 5),
            end_date=date(2026, 11, 4),
            duration_value=1,
            duration_unit="months",
            base_price=12000,
            tax_percent=5,
            tax_amount=600,
            total_amount=12600,
            payment_status="paid",
            status=STATUS_EXPIRED,
        )
        basic = _sub_92_row(member_id=member.id, plan_id=plan.id)
        db.add_all([terminal, basic])
        db.commit()
        db.refresh(basic)
        db.refresh(terminal)

        lifecycle = MembershipLifecycleService(db)
        lifecycle.lock_member_for_lifecycle(member.id)
        with pytest.raises(InvalidLifecycleTransitionError):
            lifecycle.pause_subscription(
                basic,
                today=PAUSE_2026_11_27,
                resume_after_subscription_id=terminal.id,
            )
        db.rollback()
        db.refresh(basic)

        assert basic.status == STATUS_ACTIVE
        assert basic.resume_after_subscription_id is None
        assert basic.remaining_days is None