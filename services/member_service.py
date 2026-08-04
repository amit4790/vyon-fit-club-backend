"""
Member service layer for member management business logic.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import Member
from repositories import MemberRepository
from schemas.member import MemberCreateRequest, MemberUpdateRequest
from services.push_device_service import PushDeviceService
from core.config import settings


logger = logging.getLogger(__name__)


class MemberNotFoundError(Exception):
    """Raised when a member does not exist."""


class DuplicateMobileError(Exception):
    """Raised when a mobile number already exists."""


class DuplicateDeviceIdentifierError(Exception):
    """Raised when a device user identifier is already linked to another member."""


class InvalidDeviceMappingError(Exception):
    """Raised when device mapping payload is invalid."""


def _is_mobile_unique_violation(exc: IntegrityError) -> bool:
    constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if constraint_name == "ix_members_mobile_number":
        return True

    return "ix_members_mobile_number" in str(exc.orig)


class MemberService:
    """Service for member management operations."""

    def __init__(self, db: Session):
        self.db = db
        self.repository = MemberRepository(db)

    def list_members(self, *, page: int, page_size: int, search: str | None) -> tuple[list[Member], int]:
        return self.repository.list_members(page=page, page_size=page_size, search=search)

    @staticmethod
    def _normalize_device_user_id(device_user_id: str | None) -> str | None:
        if device_user_id is None:
            return None
        normalized = device_user_id.strip()
        return normalized or None

    @staticmethod
    def _apply_create_payload(member: Member, payload: MemberCreateRequest) -> None:
        member.full_name = payload.full_name
        member.mobile_number = payload.mobile_number
        member.phone = payload.mobile_number
        member.joined_at = payload.joining_date
        member.status = payload.status
        member.email = payload.email
        member.date_of_birth = payload.date_of_birth
        member.gender = payload.gender
        member.address = payload.address
        member.emergency_contact = payload.emergency_contact
        member.emergency_phone = payload.emergency_phone
        member.notes = payload.notes

    def _restore_deleted_member(self, member: Member, payload: MemberCreateRequest) -> Member:
        logger.info(
            "Restoring soft-deleted member during create",
            extra={"member_id": member.id, "mobile_number": payload.mobile_number},
        )
        self._apply_create_payload(member, payload)
        member.deleted_at = None
        self.db.flush()
        self.db.refresh(member)
        return member

    def create_member(self, payload: MemberCreateRequest) -> Member:
        logger.info("Creating member", extra={"mobile_number": payload.mobile_number})

        existing_member = self.repository.get_member_by_mobile_any_status(payload.mobile_number)
        if existing_member and existing_member.deleted_at is None:
            logger.warning(
                "Member create conflict on active mobile number",
                extra={"member_id": existing_member.id, "mobile_number": payload.mobile_number},
            )
            raise DuplicateMobileError("Mobile Number already exists")

        try:
            if existing_member and existing_member.deleted_at is not None:
                member = self._restore_deleted_member(existing_member, payload)
            else:
                member = Member(user_id=None)
                self._apply_create_payload(member, payload)
                self.repository.add(member)

            self.db.commit()
            self.db.refresh(member)
            
            # Auto-sync to PUSH devices if enabled
            if settings.device_push_enabled:
                try:
                    push_service = PushDeviceService(self.db)
                    card_number = str(member.device_card) if member.device_card else None
                    commands = push_service.sync_member_to_devices(
                        member_id=member.id,
                        member_name=member.full_name,
                        card_number=card_number
                    )
                    logger.info(
                        f"Queued {len(commands)} user sync commands for new member",
                        extra={"member_id": member.id, "command_count": len(commands)}
                    )
                except Exception as sync_error:
                    # Log but don't fail member creation if sync fails
                    logger.error(
                        "Failed to queue device sync commands for new member",
                        extra={"member_id": member.id},
                        exc_info=sync_error
                    )
            
            return member
        except IntegrityError as exc:
            self.db.rollback()
            if _is_mobile_unique_violation(exc):
                logger.warning(
                    "Member create failed due to duplicate mobile number",
                    extra={"mobile_number": payload.mobile_number},
                    exc_info=exc,
                )
                raise DuplicateMobileError("Mobile Number already exists") from exc

            logger.exception(
                "Unexpected integrity error during member create",
                extra={"mobile_number": payload.mobile_number},
            )
            raise
        except Exception:
            self.db.rollback()
            logger.exception(
                "Unexpected error during member create",
                extra={"mobile_number": payload.mobile_number},
            )
            raise

    def update_member(self, member_id: int, payload: MemberUpdateRequest) -> Member:
        member = self.repository.get_member_by_id(member_id)
        if not member:
            logger.warning("Member update target not found", extra={"member_id": member_id})
            raise MemberNotFoundError("Member not found")

        update_data = payload.model_dump(exclude_unset=True)
        logger.info("Updating member", extra={"member_id": member_id, "fields": sorted(update_data.keys())})

        if "mobile_number" in update_data:
            mobile_number = update_data["mobile_number"]
            existing_member = self.repository.get_member_by_mobile_any_status(mobile_number)
            if existing_member and existing_member.id != member.id:
                logger.warning(
                    "Member update conflict on mobile number",
                    extra={
                        "member_id": member_id,
                        "conflicting_member_id": existing_member.id,
                        "mobile_number": mobile_number,
                        "conflicting_member_deleted": existing_member.deleted_at is not None,
                    },
                )
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
        except IntegrityError as exc:
            self.db.rollback()
            if _is_mobile_unique_violation(exc):
                logger.warning(
                    "Member update failed due to duplicate mobile number",
                    extra={"member_id": member_id},
                    exc_info=exc,
                )
                raise DuplicateMobileError("Mobile Number already exists") from exc

            logger.exception("Unexpected integrity error during member update", extra={"member_id": member_id})
            raise
        except Exception:
            self.db.rollback()
            logger.exception("Unexpected error during member update", extra={"member_id": member_id})
            raise

    def get_member_or_raise(self, member_id: int) -> Member:
        member = self.repository.get_member_by_id(member_id)
        if not member:
            logger.warning("Member target not found", extra={"member_id": member_id})
            raise MemberNotFoundError("Member not found")
        return member

    def upsert_device_mapping(
        self,
        *,
        member_id: int,
        device_user_id: str | None,
        device_uid: int | None,
        device_card: int | None,
        sync_status: str,
        update_sync_timestamp: bool,
    ) -> Member:
        member = self.get_member_or_raise(member_id)

        normalized_device_user_id = self._normalize_device_user_id(device_user_id)
        if normalized_device_user_id is None and device_uid is None:
            raise InvalidDeviceMappingError("Either device_user_id or device_uid is required")

        if normalized_device_user_id is not None:
            conflict_by_user_id = self.repository.get_member_by_device_user_id_any_status(
                normalized_device_user_id,
                exclude_member_id=member_id,
            )
            if conflict_by_user_id:
                logger.warning(
                    "Device mapping conflict on device_user_id",
                    extra={
                        "member_id": member_id,
                        "conflicting_member_id": conflict_by_user_id.id,
                        "device_user_id": normalized_device_user_id,
                    },
                )
                raise DuplicateDeviceIdentifierError("Device user id is already linked to another member")

        if device_uid is not None:
            conflict_by_uid = self.repository.get_member_by_device_uid_any_status(
                device_uid,
                exclude_member_id=member_id,
            )
            if conflict_by_uid:
                logger.warning(
                    "Device mapping conflict on device_uid",
                    extra={
                        "member_id": member_id,
                        "conflicting_member_id": conflict_by_uid.id,
                        "device_uid": device_uid,
                    },
                )
                raise DuplicateDeviceIdentifierError("Device UID is already linked to another member")

        member.device_user_id = normalized_device_user_id
        member.device_uid = device_uid
        member.device_card = device_card
        member.device_sync_status = sync_status
        if update_sync_timestamp:
            member.last_device_sync_at = datetime.now(timezone.utc)

        try:
            self.db.commit()
            self.db.refresh(member)
            return member
        except IntegrityError as exc:
            self.db.rollback()
            logger.warning(
                "Device mapping update failed due to uniqueness conflict",
                extra={"member_id": member_id},
                exc_info=exc,
            )
            raise DuplicateDeviceIdentifierError("Device identifiers are already linked to another member") from exc
        except Exception:
            self.db.rollback()
            logger.exception("Unexpected error during device mapping update", extra={"member_id": member_id})
            raise

    def clear_device_mapping(self, *, member_id: int, sync_status: str) -> Member:
        member = self.get_member_or_raise(member_id)

        member.device_user_id = None
        member.device_uid = None
        member.device_card = None
        member.device_sync_status = sync_status
        member.last_device_sync_at = datetime.now(timezone.utc)

        try:
            self.db.commit()
            self.db.refresh(member)
            return member
        except Exception:
            self.db.rollback()
            logger.exception("Unexpected error during device mapping clear", extra={"member_id": member_id})
            raise

    def delete_member(self, member_id: int) -> None:
        member = self.repository.get_member_by_id(member_id)
        if not member:
            logger.warning("Member delete target not found", extra={"member_id": member_id})
            raise MemberNotFoundError("Member not found")

        logger.info("Soft deleting member", extra={"member_id": member_id, "mobile_number": member.mobile_number})
        member.status = "inactive"
        member.deleted_at = datetime.now(timezone.utc)

        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            logger.exception("Unexpected error during member delete", extra={"member_id": member_id})
            raise
