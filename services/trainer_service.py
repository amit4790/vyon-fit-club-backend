"""Trainer service layer for trainer management business logic."""

from sqlalchemy.orm import Session

from core.roles import UserRole
from models import User
from repositories import TrainerRepository
from schemas.trainer import TrainerCreateRequest, TrainerUpdateRequest


class TrainerNotFoundError(Exception):
    """Raised when a trainer does not exist."""


class DuplicateTrainerEmailError(Exception):
    """Raised when a trainer email already exists."""


class TrainerService:
    """Service for trainer management operations."""

    def __init__(self, db: Session):
        self.db = db
        self.repository = TrainerRepository(db)

    def list_trainers(self) -> list[User]:
        return self.repository.list_trainers()

    def create_trainer(self, payload: TrainerCreateRequest) -> User:
        existing = self.repository.get_trainer_by_email(str(payload.email))
        if existing:
            raise DuplicateTrainerEmailError("Trainer email already exists")

        trainer = User(
            full_name=payload.full_name,
            email=str(payload.email),
            role=UserRole.TRAINER,
            is_active=payload.is_active,
            # Placeholder value: current auth flow uses mock users only.
            password_hash="trainer-managed-by-admin",
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
            existing = self.repository.get_trainer_by_email(email)
            if existing and existing.id != trainer.id:
                raise DuplicateTrainerEmailError("Trainer email already exists")
            trainer.email = email

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
