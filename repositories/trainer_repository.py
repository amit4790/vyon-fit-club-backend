"""Trainer repository for database operations."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import User


class TrainerRepository:
    """Repository for trainer persistence operations."""

    def __init__(self, db: Session):
        self.db = db

    def list_trainers(self) -> list[User]:
        statement = (
            select(User)
            .where(User.role == "trainer")
            .order_by(User.created_at.desc(), User.id.desc())
        )
        return self.db.execute(statement).scalars().all()

    def get_trainer_by_id(self, trainer_id: int) -> User | None:
        statement = select(User).where(User.id == trainer_id, User.role == "trainer")
        return self.db.execute(statement).scalar_one_or_none()

    def get_trainer_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == email, User.role == "trainer")
        return self.db.execute(statement).scalar_one_or_none()

    def add(self, trainer: User) -> User:
        self.db.add(trainer)
        self.db.flush()
        self.db.refresh(trainer)
        return trainer
