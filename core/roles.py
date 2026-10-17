"""Centralized role definitions for the application."""

from enum import StrEnum


class UserRole(StrEnum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    TRAINER = "TRAINER"
    MEMBER = "MEMBER"
    GYM_TABLET = "GYM_TABLET"
