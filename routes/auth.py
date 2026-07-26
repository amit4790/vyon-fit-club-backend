"""
Authentication Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from schemas.auth import LoginRequest, LoginResponse
from services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="User Login",
    description="Authenticate user with email or phone number and password",
    responses={
        200: {"description": "Login successful"},
        401: {"description": "Invalid credentials"}
    }
)
def login(credentials: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    """
    Login endpoint for user authentication
    
    Args:
        credentials: LoginRequest with email and password
    
    Returns:
        LoginResponse: Authenticated user information and token
    
    Raises:
        HTTPException: 401 if credentials are invalid
    """
    success, user_info, error_message = AuthService.authenticate(
        db,
        credentials.identifier,
        credentials.password
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_message or "Invalid credentials"
        )
    
    token = AuthService.create_session(user_info)
    
    return LoginResponse(
        success=True,
        token=token,
        user=user_info
    )
