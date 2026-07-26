"""
Dashboard repository for admin dashboard queries.
"""

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import Member, MembershipSubscription
from models import User


class DashboardRepository:
    """Repository for dashboard persistence queries."""

    def __init__(self, db: Session):
        self.db = db

    def get_total_members(self) -> int:
        statement = select(func.count(Member.id)).where(Member.deleted_at.is_(None))
        return self.db.execute(statement).scalar_one()

    def get_active_members(self) -> int:
        statement = select(func.count(Member.id)).where(
            Member.deleted_at.is_(None),
            Member.status == "active",
        )
        return self.db.execute(statement).scalar_one()

    def get_total_trainers(self) -> int:
        statement = select(func.count(User.id)).where(
            User.role.in_(["TRAINER", "trainer"]),
            User.is_active.is_(True),
        )
        return self.db.execute(statement).scalar_one()

    def get_inactive_members(self) -> int:
        statement = select(func.count(Member.id)).where(
            Member.deleted_at.is_(None),
            Member.status == "inactive",
        )
        return self.db.execute(statement).scalar_one()

    def get_recent_registrations(self, limit: int = 5) -> list[Member]:
        statement = (
            select(Member)
            .where(Member.deleted_at.is_(None))
            .order_by(Member.joined_at.desc(), Member.id.desc())
            .limit(limit)
        )
        return self.db.execute(statement).scalars().all()

    def get_expiring_memberships(self, days: int = 30) -> int:
        today = date.today()
        end_window = today + timedelta(days=days)

        statement = select(func.count(MembershipSubscription.id)).where(
            MembershipSubscription.status == "active",
            MembershipSubscription.end_date >= today,
            MembershipSubscription.end_date <= end_window,
        )
        return self.db.execute(statement).scalar_one()
