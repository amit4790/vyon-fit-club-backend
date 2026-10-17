"""Centralized authorization helpers."""

from core.roles import UserRole


ADMIN_ACCESS_ROLES = {UserRole.SUPER_ADMIN, UserRole.ADMIN}
GYM_TABLET_ACCESS_ROLES = {UserRole.GYM_TABLET}
BODY_ASSESSMENT_ACCESS_ROLES = ADMIN_ACCESS_ROLES | GYM_TABLET_ACCESS_ROLES
PASSWORD_LOGIN_ROLES = ADMIN_ACCESS_ROLES | GYM_TABLET_ACCESS_ROLES


def can_access_admin(role: str | None) -> bool:
    if not role:
        return False

    try:
        return UserRole(role) in ADMIN_ACCESS_ROLES
    except ValueError:
        return False


def can_access_gym_tablet(role: str | None) -> bool:
    if not role:
        return False
    try:
        return UserRole(role) in GYM_TABLET_ACCESS_ROLES
    except ValueError:
        return False


def can_access_body_assessments(role: str | None) -> bool:
    if not role:
        return False
    try:
        return UserRole(role) in BODY_ASSESSMENT_ACCESS_ROLES
    except ValueError:
        return False


def can_use_password_login(role: str | None) -> bool:
    if not role:
        return False
    try:
        return UserRole(role) in PASSWORD_LOGIN_ROLES
    except ValueError:
        return False
