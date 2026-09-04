"""
Dependency Injection
Centralized dependencies for request handling
"""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.authorization import can_access_admin
from core.roles import UserRole
from services.auth_service import AuthService, InvalidTokenError, SessionPayload, TokenExpiredError

bearer_scheme = HTTPBearer(auto_error=False)


class RequestContext:
    """Context object for request information"""
    
    def __init__(self, user_role: Optional[str] = None, user_id: Optional[str] = None):
        self.user_role = user_role
        self.user_id = user_id


def get_request_context() -> RequestContext:
    """
    Get the current request context
    Can be extended with authentication later
    """
    return RequestContext()


def get_current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> SessionPayload:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    try:
        return AuthService.decode_access_token(credentials.credentials)
    except TokenExpiredError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def require_admin_access(session: SessionPayload = Depends(get_current_session)) -> SessionPayload:
    if not can_access_admin(session.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return session


def require_super_admin(session: SessionPayload = Depends(get_current_session)) -> SessionPayload:
    if session.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin access required")
    return session


def require_member_access(session: SessionPayload = Depends(get_current_session)) -> SessionPayload:
    if session.role != UserRole.MEMBER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Member access required")
    return session


def require_trainer_access(session: SessionPayload = Depends(get_current_session)) -> SessionPayload:
    if session.role != UserRole.TRAINER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Trainer access required")
    return session
