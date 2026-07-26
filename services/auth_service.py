"""
Authentication Service
Handles user authentication and token generation
"""

import secrets
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from core.authorization import can_access_admin
from core.roles import UserRole
from core.security import verify_password
from models import User
from schemas.auth import UserInfo


@dataclass
class SessionPayload:
    user_id: str
    role: UserRole


class AuthService:
    """Service for authentication operations"""

    _active_sessions: dict[str, SessionPayload] = {}
    
    @staticmethod
    def authenticate(db: Session, identifier: str, password: str) -> tuple[bool, UserInfo | None, str | None]:
        """
        Authenticate user with email and password
        
        Returns:
            Tuple of (success: bool, user_info: UserInfo, error_message: str)
        """
        normalized = identifier.strip()

        user = db.execute(
            select(User).where(
                or_(
                    User.email == normalized,
                    User.phone_number == normalized,
                ),
                User.is_active.is_(True),
            )
        ).scalar_one_or_none()
        
        if not user or not verify_password(password, user.password_hash) or not can_access_admin(user.role):
            return False, None, "Invalid email or phone number or password"
        
        user_info = UserInfo(
            id=str(user.id),
            name=user.full_name,
            email=user.email,
            role=UserRole(user.role)
        )
        
        return True, user_info, None
    
    @staticmethod
    def create_session(user_info: UserInfo) -> str:
        """
        Generate an opaque session token for the authenticated response.
        """
        token = secrets.token_urlsafe(32)
        AuthService._active_sessions[token] = SessionPayload(
            user_id=user_info.id,
            role=UserRole(user_info.role),
        )
        return token

    @staticmethod
    def get_session(token: str) -> SessionPayload | None:
        return AuthService._active_sessions.get(token)
