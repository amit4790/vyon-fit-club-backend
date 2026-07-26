"""Service layer for admin user management."""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from core.roles import UserRole
from core.security import hash_password
from models import User
from schemas.admin_user import AdminCreateRequest


class DuplicateAdminEmailError(Exception):
    """Raised when an admin email already exists."""


class DuplicateAdminPhoneError(Exception):
    """Raised when an admin phone number already exists."""


class AdminUserService:
    """Business logic for creating admin users."""

    def __init__(self, db: Session):
        self.db = db

    def create_admin_user(self, payload: AdminCreateRequest) -> User:
        normalized_email = str(payload.email).strip().lower()
        normalized_phone = payload.phone_number.strip()

        existing_user = self.db.execute(
            select(User).where(
                or_(
                    User.email == normalized_email,
                    User.phone_number == normalized_phone,
                )
            )
        ).scalar_one_or_none()

        if existing_user:
            if existing_user.email == normalized_email:
                raise DuplicateAdminEmailError("Email already exists")
            raise DuplicateAdminPhoneError("Phone Number already exists")

        admin_user = User(
            full_name=payload.full_name.strip(),
            email=normalized_email,
            phone_number=normalized_phone,
            password_hash=hash_password(payload.password),
            role=UserRole.ADMIN,
            is_active=payload.is_active,
        )

        try:
            self.db.add(admin_user)
            self.db.commit()
            self.db.refresh(admin_user)
            return admin_user
        except Exception:
            self.db.rollback()
            raise
