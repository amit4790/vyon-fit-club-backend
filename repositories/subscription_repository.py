"""
Subscription repository for plan catalog and assignment queries.
"""

from datetime import date

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session, joinedload

from models import Member, MembershipPlan, MembershipSubscription


class SubscriptionRepository:
    """Repository for membership plan and subscription persistence operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_active_plan_by_id(self, plan_id: int) -> MembershipPlan | None:
        statement = select(MembershipPlan).where(
            MembershipPlan.id == plan_id,
            MembershipPlan.is_active.is_(True),
        )
        return self.db.execute(statement).scalar_one_or_none()

    def get_plan_by_id(self, plan_id: int) -> MembershipPlan | None:
        statement = select(MembershipPlan).where(MembershipPlan.id == plan_id)
        return self.db.execute(statement).scalar_one_or_none()

    def list_active_plans(self) -> list[MembershipPlan]:
        statement = select(MembershipPlan).where(MembershipPlan.is_active.is_(True)).order_by(
            MembershipPlan.family_name.asc(),
            MembershipPlan.duration_months.asc(),
            MembershipPlan.id.asc(),
        )
        return self.db.execute(statement).scalars().all()

    def get_member_by_id(self, member_id: int) -> Member | None:
        statement = select(Member).where(Member.id == member_id, Member.deleted_at.is_(None))
        return self.db.execute(statement).scalar_one_or_none()

    def get_overlapping_active_subscription(
        self,
        member_id: int,
        start_date: date,
    ) -> MembershipSubscription | None:
        statement = select(MembershipSubscription).where(
            MembershipSubscription.member_id == member_id,
            MembershipSubscription.status == "active",
            MembershipSubscription.end_date >= start_date,
        )
        return self.db.execute(statement).scalar_one_or_none()

    def create_subscription(self, subscription: MembershipSubscription) -> MembershipSubscription:
        self.db.add(subscription)
        self.db.flush()
        self.db.refresh(subscription)
        return subscription

    def delete_subscriptions_for_member(self, member_id: int) -> int:
        """Permanently delete all subscriptions for a member. Returns deleted count."""
        statement = select(MembershipSubscription).where(MembershipSubscription.member_id == member_id)
        rows = self.db.execute(statement).scalars().all()
        count = len(rows)
        for row in rows:
            self.db.delete(row)
        self.db.flush()
        return count

    def get_subscription_by_id(self, subscription_id: int) -> MembershipSubscription | None:
        statement = (
            select(MembershipSubscription)
            .options(
                joinedload(MembershipSubscription.member),
                joinedload(MembershipSubscription.plan),
            )
            .where(MembershipSubscription.id == subscription_id)
        )
        return self.db.execute(statement).scalar_one_or_none()

    def list_member_subscriptions(self, member_id: int) -> list[MembershipSubscription]:
        statement = (
            select(MembershipSubscription)
            .where(MembershipSubscription.member_id == member_id)
            .order_by(MembershipSubscription.start_date.desc(), MembershipSubscription.id.desc())
        )
        return self.db.execute(statement).scalars().all()

    def list_subscriptions_for_member_ids(self, member_ids: list[int]) -> list[MembershipSubscription]:
        if not member_ids:
            return []

        statement = (
            select(MembershipSubscription)
            .options(joinedload(MembershipSubscription.plan))
            .where(MembershipSubscription.member_id.in_(member_ids))
        )
        return list(self.db.execute(statement).unique().scalars().all())

    def list_expiring_subscriptions(
        self,
        *,
        from_date: date,
        to_date: date,
        page: int,
        page_size: int,
    ) -> tuple[list[MembershipSubscription], int]:
        filters = and_(
            MembershipSubscription.status == "active",
            MembershipSubscription.end_date >= from_date,
            MembershipSubscription.end_date <= to_date,
        )

        query: Select[tuple[MembershipSubscription]] = (
            select(MembershipSubscription)
            .options(
                joinedload(MembershipSubscription.member),
                joinedload(MembershipSubscription.plan),
            )
            .where(filters)
            .order_by(MembershipSubscription.end_date.asc(), MembershipSubscription.id.asc())
        )
        count_query = select(func.count(MembershipSubscription.id)).where(filters)

        total_items = self.db.execute(count_query).scalar_one()
        subscriptions = (
            self.db.execute(query.offset((page - 1) * page_size).limit(page_size)).scalars().all()
        )
        return subscriptions, total_items

    def list_expired_subscriptions(self, today: date) -> list[MembershipSubscription]:
        statement = select(MembershipSubscription).where(
            MembershipSubscription.end_date < today,
            MembershipSubscription.status == "active",
        )
        return self.db.execute(statement).scalars().all()

    def member_has_active_membership(self, member_id: int, today: date) -> bool:
        """True when the member has at least one non-expired active subscription."""
        statement = (
            select(MembershipSubscription.id)
            .where(
                MembershipSubscription.member_id == member_id,
                MembershipSubscription.status == "active",
                MembershipSubscription.end_date >= today,
            )
            .limit(1)
        )
        return self.db.execute(statement).scalar_one_or_none() is not None
