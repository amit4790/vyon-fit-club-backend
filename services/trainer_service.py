"""Trainer service layer for trainer management business logic."""

import logging
import secrets
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import select

from core.config import settings
from core.roles import UserRole
from core.security import hash_password
from models import Member
from models import User
from repositories import MemberRepository, TrainerRepository
from schemas.trainer import TrainerCreateRequest, TrainerUpdateRequest
from services.push_device_service import PushDeviceService

logger = logging.getLogger(__name__)


class TrainerNotFoundError(Exception):
    """Raised when a trainer does not exist."""


class DuplicateTrainerEmailError(Exception):
    """Raised when a trainer email already exists."""


class DuplicateTrainerPhoneError(Exception):
    """Raised when a trainer phone already exists."""


class MemberNotFoundError(Exception):
    """Raised when a member does not exist."""


class MemberAlreadyAssignedError(Exception):
    """Raised when member is already assigned to this trainer."""


class TrainerService:
    """Service for trainer management operations."""

    def __init__(self, db: Session):
        self.db = db
        self.repository = TrainerRepository(db)
        self.member_repository = MemberRepository(db)

    def list_trainers(self) -> list[User]:
        return self.repository.list_trainers()

    def get_assigned_member_count(self, trainer_id: int) -> int:
        return self.member_repository.count_members_for_trainer(trainer_id)

    def create_trainer(self, payload: TrainerCreateRequest) -> User:
        existing = self.db.execute(select(User).where(User.email == str(payload.email))).scalar_one_or_none()
        if existing:
            raise DuplicateTrainerEmailError("Trainer email already exists")

        existing_phone = self.db.execute(select(User).where(User.phone_number == payload.phone_number)).scalar_one_or_none()
        if existing_phone:
            raise DuplicateTrainerPhoneError("Trainer phone number already exists")

        # Trainers do not log into the app; store an unusable random password hash.
        password = payload.temporary_password or secrets.token_urlsafe(32)

        trainer = User(
            full_name=payload.full_name,
            email=str(payload.email),
            phone_number=payload.phone_number,
            specialization=payload.specialization,
            role=UserRole.TRAINER,
            is_active=payload.is_active,
            password_hash=hash_password(password),
        )

        try:
            self.repository.add(trainer)
            self.db.commit()
            self.db.refresh(trainer)

            if settings.device_push_enabled and trainer.is_active:
                try:
                    push = PushDeviceService(self.db)
                    commands = push.sync_trainer_to_devices(trainer.id, trainer.full_name)
                    logger.info(
                        "Queued trainer device sync",
                        extra={"trainer_id": trainer.id, "command_count": len(commands)},
                    )
                except Exception:
                    logger.exception("Failed to queue trainer device sync", extra={"trainer_id": trainer.id})

            return trainer
        except Exception:
            self.db.rollback()
            raise

    def update_trainer(self, trainer_id: int, payload: TrainerUpdateRequest) -> User:
        trainer = self.repository.get_trainer_by_id(trainer_id)
        if not trainer:
            raise TrainerNotFoundError("Trainer not found")

        update_data = payload.model_dump(exclude_unset=True)
        was_active = trainer.is_active
        name_changed = False

        if "email" in update_data and update_data["email"] is not None:
            email = str(update_data["email"])
            existing = self.db.execute(select(User).where(User.email == email)).scalar_one_or_none()
            if existing and existing.id != trainer.id:
                raise DuplicateTrainerEmailError("Trainer email already exists")
            trainer.email = email

        if "phone_number" in update_data and update_data["phone_number"] is not None:
            phone_number = update_data["phone_number"]
            existing_phone = self.db.execute(select(User).where(User.phone_number == phone_number)).scalar_one_or_none()
            if existing_phone and existing_phone.id != trainer.id:
                raise DuplicateTrainerPhoneError("Trainer phone number already exists")
            trainer.phone_number = phone_number

        if "specialization" in update_data:
            trainer.specialization = update_data["specialization"]

        if "full_name" in update_data and update_data["full_name"] is not None:
            if trainer.full_name != update_data["full_name"]:
                name_changed = True
            trainer.full_name = update_data["full_name"]

        if "is_active" in update_data and update_data["is_active"] is not None:
            trainer.is_active = bool(update_data["is_active"])

        try:
            self.db.commit()
            self.db.refresh(trainer)

            if settings.device_push_enabled:
                push = PushDeviceService(self.db)
                try:
                    if trainer.is_active and (name_changed or not was_active):
                        push.sync_trainer_to_devices(trainer.id, trainer.full_name)
                    elif was_active and not trainer.is_active:
                        push.remove_trainer_from_devices(trainer.id)
                except Exception:
                    logger.exception(
                        "Failed to queue trainer device sync on update",
                        extra={"trainer_id": trainer.id},
                    )

            return trainer
        except Exception:
            self.db.rollback()
            raise

    def sync_all_active_trainers_to_devices(self) -> dict[str, int]:
        """Queue USERINFO for every active trainer (PIN = 50000 + id)."""
        if not settings.device_push_enabled:
            return {"trainers_queued": 0, "commands_queued": 0}

        trainers = [trainer for trainer in self.repository.list_trainers() if trainer.is_active]
        push = PushDeviceService(self.db)
        commands_queued = 0
        for trainer in trainers:
            commands = push.sync_trainer_to_devices(trainer.id, trainer.full_name)
            commands_queued += len(commands)
        return {"trainers_queued": len(trainers), "commands_queued": commands_queued}

    def get_trainer_assigned_members(self, trainer_id: int) -> list[Member]:
        return self.member_repository.list_members_for_trainer(trainer_id)

    def search_assignable_members(
        self,
        trainer_id: int,
        *,
        search: str | None = None,
    ) -> list[Member]:
        trainer = self.repository.get_trainer_by_id(trainer_id)
        if not trainer:
            raise TrainerNotFoundError("Trainer not found")
        return self.member_repository.search_assignable_members(
            search=search,
            exclude_trainer_id=trainer_id,
            limit=25,
        )

    def assign_member(
        self,
        trainer_id: int,
        member_id: int,
    ) -> Member:
        trainer = self.repository.get_trainer_by_id(trainer_id)
        if not trainer:
            raise TrainerNotFoundError("Trainer not found")
        if not trainer.is_active:
            raise TrainerNotFoundError("Cannot assign members to an inactive trainer")

        member = self.member_repository.get_member_by_id(member_id)
        if not member:
            raise MemberNotFoundError("Member not found")

        if member.trainer_id == trainer_id:
            raise MemberAlreadyAssignedError("Member is already assigned to this trainer")

        member.trainer_id = trainer_id
        member.trainer_assignment_source = None
        member.trainer_assigned_at = datetime.now(timezone.utc)

        try:
            self.db.commit()
            self.db.refresh(member)
            return member
        except Exception:
            self.db.rollback()
            raise

    def unassign_member(self, trainer_id: int, member_id: int) -> None:
        trainer = self.repository.get_trainer_by_id(trainer_id)
        if not trainer:
            raise TrainerNotFoundError("Trainer not found")

        member = self.member_repository.get_member_by_id(member_id)
        if not member:
            raise MemberNotFoundError("Member not found")
        if member.trainer_id != trainer_id:
            raise MemberNotFoundError("Member is not assigned to this trainer")

        member.trainer_id = None
        member.trainer_assignment_source = None
        member.trainer_assigned_at = None

        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def delete_trainer(self, trainer_id: int) -> None:
        trainer = self.repository.get_trainer_by_id(trainer_id)
        if not trainer:
            raise TrainerNotFoundError("Trainer not found")

        trainer.is_active = False

        try:
            self.db.commit()
            if settings.device_push_enabled:
                try:
                    PushDeviceService(self.db).remove_trainer_from_devices(trainer.id)
                except Exception:
                    logger.exception(
                        "Failed to queue trainer device delete",
                        extra={"trainer_id": trainer.id},
                    )
        except Exception:
            self.db.rollback()
            raise
