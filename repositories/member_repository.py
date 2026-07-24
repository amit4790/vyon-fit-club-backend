"""
Member repository for database operations.
"""

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from models import Member


class MemberRepository:
    """Repository for member persistence operations."""

    def __init__(self, db: Session):
        self.db = db

    def list_members(self, *, page: int, page_size: int, search: str | None) -> tuple[list[Member], int]:
        query: Select[tuple[Member]] = select(Member).where(Member.deleted_at.is_(None))
        count_query = select(func.count(Member.id)).where(Member.deleted_at.is_(None))

        if search:
            search_term = f"%{search.strip()}%"
            search_filter = or_(
                Member.full_name.ilike(search_term),
                Member.mobile_number.ilike(search_term),
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        total_items = self.db.execute(count_query).scalar_one()
        members = (
            self.db.execute(
                query.order_by(Member.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .scalars()
            .all()
        )

        return members, total_items

    def get_member_by_id(self, member_id: int) -> Member | None:
        statement = select(Member).where(Member.id == member_id, Member.deleted_at.is_(None))
        return self.db.execute(statement).scalar_one_or_none()

    def get_member_by_mobile(self, mobile_number: str) -> Member | None:
        statement = select(Member).where(
            Member.mobile_number == mobile_number,
            Member.deleted_at.is_(None),
        )
        return self.db.execute(statement).scalar_one_or_none()

    def add(self, member: Member) -> Member:
        self.db.add(member)
        self.db.flush()
        self.db.refresh(member)
        return member
