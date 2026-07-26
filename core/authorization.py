"""Centralized authorization helpers."""

from core.roles import UserRole


ADMIN_ACCESS_ROLES = {UserRole.SUPER_ADMIN, UserRole.ADMIN}


def can_access_admin(role: str | None) -> bool:
    if not role:
        return False

    try:
        return UserRole(role) in ADMIN_ACCESS_ROLES
    except ValueError:
        return False
