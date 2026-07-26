"""
Authentication Service
Handles user authentication and token generation
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from jose import jwt  # type: ignore[reportMissingImports]
from jose.exceptions import ExpiredSignatureError, JWTError  # type: ignore[reportMissingImports]
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from core.config import settings
from core.authorization import can_access_admin
from core.roles import UserRole
from core.security import verify_password
from models import User
from schemas.auth import UserInfo


@dataclass
class SessionPayload:
    user_id: str
    role: UserRole


class TokenExpiredError(Exception):
    """Raised when a JWT token has expired."""


class InvalidTokenError(Exception):
    """Raised when a JWT token is invalid."""


class AuthService:
    """Service for authentication operations"""
    
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
    def create_access_token(user_info: UserInfo) -> str:
        """Create a signed JWT access token.

        Claims used:
        - sub: user id (preferred standard subject claim)
        - user_id: compatibility claim for older decoders
        - role: role string value used by authorization checks
        - token_type: access
        - iat: issued-at timestamp
        - exp: expiry timestamp
        """
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
        issued_at = datetime.now(timezone.utc)
        role_value = user_info.role.value if isinstance(user_info.role, UserRole) else str(user_info.role)
        payload = {
            "sub": user_info.id,
            "user_id": user_info.id,
            "role": role_value,
            "token_type": "access",
            "iat": issued_at,
            "exp": expires_at,
        }
        return jwt.encode(payload, settings.effective_jwt_secret_key, algorithm=settings.jwt_algorithm)

    @staticmethod
    def decode_access_token(token: str) -> SessionPayload:
        """Decode and validate a JWT access token."""
        try:
            payload = jwt.decode(
                token,
                settings.effective_jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
        except ExpiredSignatureError as exc:
            raise TokenExpiredError("Token has expired") from exc
        except JWTError as exc:
            raise InvalidTokenError("Invalid token") from exc

        token_type = payload.get("token_type")
        user_id = payload.get("sub") or payload.get("user_id")
        role = payload.get("role")

        if token_type != "access":
            raise InvalidTokenError("Invalid token type")

        if not user_id or not role:
            raise InvalidTokenError("Token is missing required claims")

        try:
            normalized_role = UserRole(role)
        except ValueError as exc:
            raise InvalidTokenError("Token role is invalid") from exc

        return SessionPayload(
            user_id=str(user_id),
            role=normalized_role,
        )
