"""Bootstrap the single production administrator account."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import settings
from core.roles import UserRole
from core.security import hash_password
from models import User


def ensure_super_admin(db: Session) -> None:
    """Create the configured super administrator if it does not yet exist."""
    existing_admin = db.execute(
        select(User).where(User.role == UserRole.SUPER_ADMIN)
    ).scalar_one_or_none()
    if existing_admin:
        return

    existing_user = db.execute(
        select(User).where(User.email == settings.super_admin_email)
    ).scalar_one_or_none()
    if existing_user:
        existing_user.full_name = settings.super_admin_name
        existing_user.password_hash = hash_password(settings.super_admin_password)
        existing_user.role = UserRole.SUPER_ADMIN
        existing_user.is_active = True
        db.commit()
        return

    db.add(User(
        email=settings.super_admin_email,
        full_name=settings.super_admin_name,
        password_hash=hash_password(settings.super_admin_password),
        role=UserRole.SUPER_ADMIN,
        is_active=True,
    ))
    db.commit()
