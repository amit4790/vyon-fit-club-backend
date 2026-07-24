"""
Member service layer for member management business logic.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import Member
from repositories import MemberRepository
from schemas.member import MemberCreateRequest, MemberUpdateRequest


class MemberNotFoundError(Exception):
    """Raised when a member does not exist."""


class DuplicateMobileError(Exception):
    """Raised when a mobile number already exists."""


class MemberService:
    """Service for member management operations."""

    def __init__(self, db: Session):
        self.db = db
        self.repository = MemberRepository(db)

    def list_members(self, *, page: int, page_size: int, search: str | None) -> tuple[list[Member], int]:
        return self.repository.list_members(page=page, page_size=page_size, search=search)

    def create_member(self, payload: MemberCreateRequest) -> Member:
        existing_member = self.repository.get_member_by_mobile(payload.mobile_number)
        if existing_member:
            raise DuplicateMobileError("Mobile Number already exists")

        member = Member(
            full_name=payload.full_name,
            mobile_number=payload.mobile_number,
            phone=payload.mobile_number,
            joined_at=payload.joining_date,
            status=payload.status,
            email=payload.email,
            date_of_birth=payload.date_of_birth,
            gender=payload.gender,
            address=payload.address,
            emergency_contact=payload.emergency_contact,
            emergency_phone=payload.emergency_phone,
            notes=payload.notes,
            user_id=None,
        )

        try:
            self.repository.add(member)
            self.db.commit()
            return member
        except Exception:
            self.db.rollback()
            raise

    def update_member(self, member_id: int, payload: MemberUpdateRequest) -> Member:
        member = self.repository.get_member_by_id(member_id)
        if not member:
            raise MemberNotFoundError("Member not found")

        update_data = payload.model_dump(exclude_unset=True)

        if "mobile_number" in update_data:
            mobile_number = update_data["mobile_number"]
            existing_member = self.repository.get_member_by_mobile(mobile_number)
            if existing_member and existing_member.id != member.id:
                raise DuplicateMobileError("Mobile Number already exists")
            member.mobile_number = mobile_number
            member.phone = mobile_number

        if "full_name" in update_data:
            member.full_name = update_data["full_name"]
        if "joining_date" in update_data:
            member.joined_at = update_data["joining_date"]
        if "status" in update_data:
            member.status = update_data["status"]
        if "email" in update_data:
            member.email = update_data["email"]
        if "date_of_birth" in update_data:
            member.date_of_birth = update_data["date_of_birth"]
        if "gender" in update_data:
            member.gender = update_data["gender"]
        if "address" in update_data:
            member.address = update_data["address"]
        if "emergency_contact" in update_data:
            member.emergency_contact = update_data["emergency_contact"]
        if "emergency_phone" in update_data:
            member.emergency_phone = update_data["emergency_phone"]
        if "notes" in update_data:
            member.notes = update_data["notes"]

        try:
            self.db.commit()
            self.db.refresh(member)
            return member
        except Exception:
            self.db.rollback()
            raise

    def delete_member(self, member_id: int) -> None:
        member = self.repository.get_member_by_id(member_id)
        if not member:
            raise MemberNotFoundError("Member not found")

        member.status = "inactive"
        member.deleted_at = datetime.now(timezone.utc)

        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
