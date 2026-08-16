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

    def list_members_for_trainer(self, trainer_id: int) -> list[Member]:
        statement = (
            select(Member)
            .where(
                Member.deleted_at.is_(None),
                Member.trainer_id == trainer_id,
            )
            .order_by(Member.full_name.asc(), Member.id.asc())
        )
        return list(self.db.execute(statement).scalars().all())

    def count_members_for_trainer(self, trainer_id: int) -> int:
        statement = select(func.count(Member.id)).where(
            Member.deleted_at.is_(None),
            Member.trainer_id == trainer_id,
        )
        return int(self.db.execute(statement).scalar_one())

    def search_assignable_members(
        self,
        *,
        search: str | None,
        exclude_trainer_id: int | None = None,
        limit: int = 20,
    ) -> list[Member]:
        """Active members available to assign (optionally excluding already on this trainer)."""
        query: Select[tuple[Member]] = select(Member).where(
            Member.deleted_at.is_(None),
            Member.status == "active",
        )
        if exclude_trainer_id is not None:
            query = query.where(
                or_(Member.trainer_id.is_(None), Member.trainer_id != exclude_trainer_id)
            )
        if search and search.strip():
            search_term = f"%{search.strip()}%"
            query = query.where(
                or_(
                    Member.full_name.ilike(search_term),
                    Member.mobile_number.ilike(search_term),
                )
            )
        return list(
            self.db.execute(query.order_by(Member.full_name.asc()).limit(limit)).scalars().all()
        )

    def get_member_by_id(self, member_id: int) -> Member | None:
        statement = select(Member).where(Member.id == member_id, Member.deleted_at.is_(None))
        return self.db.execute(statement).scalar_one_or_none()

    def get_member_by_id_any_status(self, member_id: int) -> Member | None:
        statement = select(Member).where(Member.id == member_id)
        return self.db.execute(statement).scalar_one_or_none()

    def get_member_by_mobile(self, mobile_number: str) -> Member | None:
        statement = select(Member).where(
            Member.mobile_number == mobile_number,
            Member.deleted_at.is_(None),
        )
        return self.db.execute(statement).scalar_one_or_none()

    def get_member_by_mobile_any_status(self, mobile_number: str) -> Member | None:
        statement = select(Member).where(Member.mobile_number == mobile_number)
        return self.db.execute(statement).scalar_one_or_none()

    def get_member_by_device_user_id_any_status(
        self,
        device_user_id: str,
        *,
        exclude_member_id: int | None = None,
    ) -> Member | None:
        statement = select(Member).where(Member.device_user_id == device_user_id)
        if exclude_member_id is not None:
            statement = statement.where(Member.id != exclude_member_id)
        return self.db.execute(statement).scalar_one_or_none()

    def get_member_by_device_uid_any_status(
        self,
        device_uid: int,
        *,
        exclude_member_id: int | None = None,
    ) -> Member | None:
        statement = select(Member).where(Member.device_uid == device_uid)
        if exclude_member_id is not None:
            statement = statement.where(Member.id != exclude_member_id)
        return self.db.execute(statement).scalar_one_or_none()

    def add(self, member: Member) -> Member:
        self.db.add(member)
        self.db.flush()
        self.db.refresh(member)
        return member
