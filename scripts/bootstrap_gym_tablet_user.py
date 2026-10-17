"""Create or update the shared gym-tablet login user (role GYM_TABLET)."""

from __future__ import annotations

import os
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from core.roles import UserRole
from core.security import hash_password, verify_password
from database import SessionLocal
from models import User

DEFAULT_EMAIL = "gym-tablet@vyonfitclub.com"
DEFAULT_NAME = "Gym Tablet"
DEFAULT_PHONE = "gym-tablet-0001"


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def bootstrap_gym_tablet_user() -> None:
    email = _env("GYM_TABLET_EMAIL", DEFAULT_EMAIL).lower()
    full_name = _env("GYM_TABLET_NAME", DEFAULT_NAME)
    phone = _env("GYM_TABLET_PHONE", DEFAULT_PHONE)
    password = os.environ.get("GYM_TABLET_PASSWORD", "").strip()
    if not password:
        raise SystemExit("Set GYM_TABLET_PASSWORD before running this script.")

    db = SessionLocal()
    try:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            db.add(
                User(
                    full_name=full_name,
                    email=email,
                    phone_number=phone,
                    password_hash=hash_password(password),
                    role=UserRole.GYM_TABLET,
                    is_active=True,
                )
            )
            db.commit()
            print(f"GYM_TABLET user created ({email}).")
            return

        changed = False
        if user.role != UserRole.GYM_TABLET:
            user.role = UserRole.GYM_TABLET
            changed = True
        if user.full_name != full_name:
            user.full_name = full_name
            changed = True
        if not user.is_active:
            user.is_active = True
            changed = True
        if not verify_password(password, user.password_hash):
            user.password_hash = hash_password(password)
            changed = True

        if changed:
            db.commit()
            print(f"GYM_TABLET user updated ({email}).")
        else:
            print(f"GYM_TABLET user already up to date ({email}).")
    finally:
        db.close()


if __name__ == "__main__":
    bootstrap_gym_tablet_user()
