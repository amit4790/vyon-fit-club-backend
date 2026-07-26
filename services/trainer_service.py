"""Trainer service layer for trainer management business logic."""

from sqlalchemy.orm import Session
from sqlalchemy import select

from core.roles import UserRole
from core.security import hash_password
from models import Member
from models import User
from repositories import TrainerRepository
from schemas.trainer import TrainerCreateRequest, TrainerUpdateRequest


class TrainerNotFoundError(Exception):
    """Raised when a trainer does not exist."""


class DuplicateTrainerEmailError(Exception):
    """Raised when a trainer email already exists."""


class DuplicateTrainerPhoneError(Exception):
    """Raised when a trainer phone already exists."""


class TrainerService:
    """Service for trainer management operations."""

    def __init__(self, db: Session):
        self.db = db
        self.repository = TrainerRepository(db)

    def list_trainers(self) -> list[User]:
        return self.repository.list_trainers()

    def create_trainer(self, payload: TrainerCreateRequest) -> User:
        existing = self.db.execute(select(User).where(User.email == str(payload.email))).scalar_one_or_none()
        if existing:
            raise DuplicateTrainerEmailError("Trainer email already exists")

        existing_phone = self.db.execute(select(User).where(User.phone_number == payload.phone_number)).scalar_one_or_none()
        if existing_phone:
            raise DuplicateTrainerPhoneError("Trainer phone number already exists")

        trainer = User(
            full_name=payload.full_name,
            email=str(payload.email),
            phone_number=payload.phone_number,
            specialization=payload.specialization,
            role=UserRole.TRAINER,
            is_active=payload.is_active,
            password_hash=hash_password(payload.temporary_password),
        )

        try:
            self.repository.add(trainer)
            self.db.commit()
            return trainer
        except Exception:
            self.db.rollback()
            raise

    def update_trainer(self, trainer_id: int, payload: TrainerUpdateRequest) -> User:
        trainer = self.repository.get_trainer_by_id(trainer_id)
        if not trainer:
            raise TrainerNotFoundError("Trainer not found")

        update_data = payload.model_dump(exclude_unset=True)

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
            trainer.full_name = update_data["full_name"]

        if "is_active" in update_data and update_data["is_active"] is not None:
            trainer.is_active = bool(update_data["is_active"])

        try:
            self.db.commit()
            self.db.refresh(trainer)
            return trainer
        except Exception:
            self.db.rollback()
            raise

    def get_trainer_assigned_members(self, trainer_id: int) -> list[Member]:
        # Trainer-member mapping is not yet modeled in the database.
        # Keep this list empty until assignment support is introduced.
        return []

    def delete_trainer(self, trainer_id: int) -> None:
        trainer = self.repository.get_trainer_by_id(trainer_id)
        if not trainer:
            raise TrainerNotFoundError("Trainer not found")

        trainer.is_active = False

        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
