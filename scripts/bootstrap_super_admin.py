"""One-time, idempotent bootstrap for the first production SUPER_ADMIN user."""

from pathlib import Path
import sys

# Allow direct script execution: `python scripts/bootstrap_super_admin.py`.
sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from core.roles import UserRole
from core.security import hash_password, verify_password
from database import SessionLocal
from models import User


SUPER_ADMIN_NAME = "Amit Sharma"
SUPER_ADMIN_EMAIL = "amits8052@gmail.com"
SUPER_ADMIN_PHONE = "8800240055"
SUPER_ADMIN_PASSWORD = "9041amit"


def bootstrap_super_admin() -> None:
    """Create or update the first SUPER_ADMIN user without creating duplicates."""
    db = SessionLocal()

    try:
        user_by_email = db.execute(
            select(User).where(User.email == SUPER_ADMIN_EMAIL)
        ).scalar_one_or_none()
        user_by_phone = db.execute(
            select(User).where(User.phone_number == SUPER_ADMIN_PHONE)
        ).scalar_one_or_none()

        if (
            user_by_email
            and user_by_phone
            and user_by_email.id != user_by_phone.id
        ):
            raise RuntimeError(
                "Cannot bootstrap SUPER_ADMIN because email and phone are linked to different users."
            )

        target_user = user_by_email or user_by_phone

        if target_user is None:
            db.add(
                User(
                    full_name=SUPER_ADMIN_NAME,
                    email=SUPER_ADMIN_EMAIL,
                    phone_number=SUPER_ADMIN_PHONE,
                    password_hash=hash_password(SUPER_ADMIN_PASSWORD),
                    role=UserRole.SUPER_ADMIN,
                    is_active=True,
                )
            )
            db.commit()
            print("SUPER_ADMIN created.")
            return

        changed = False

        if target_user.full_name != SUPER_ADMIN_NAME:
            target_user.full_name = SUPER_ADMIN_NAME
            changed = True

        if target_user.email != SUPER_ADMIN_EMAIL:
            target_user.email = SUPER_ADMIN_EMAIL
            changed = True

        if target_user.phone_number != SUPER_ADMIN_PHONE:
            target_user.phone_number = SUPER_ADMIN_PHONE
            changed = True

        if target_user.role != UserRole.SUPER_ADMIN:
            target_user.role = UserRole.SUPER_ADMIN
            changed = True

        if not target_user.is_active:
            target_user.is_active = True
            changed = True

        if not verify_password(SUPER_ADMIN_PASSWORD, target_user.password_hash):
            target_user.password_hash = hash_password(SUPER_ADMIN_PASSWORD)
            changed = True

        if changed:
            db.commit()
            print("SUPER_ADMIN updated.")
        else:
            print("SUPER_ADMIN already up to date.")
    finally:
        db.close()


if __name__ == "__main__":
    bootstrap_super_admin()
