"""
Authentication Routes
"""

from fastapi import APIRouter, HTTPException, status
from schemas.auth import LoginRequest, LoginResponse
from services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="User Login",
    description="Authenticate user with email and password",
    responses={
        200: {"description": "Login successful"},
        401: {"description": "Invalid credentials"}
    }
)
def login(credentials: LoginRequest) -> LoginResponse:
    """
    Login endpoint for user authentication
    
    Args:
        credentials: LoginRequest with email and password
    
    Returns:
        LoginResponse: User information and mock JWT token
    
    Raises:
        HTTPException: 401 if credentials are invalid
    """
    success, user_info, error_message = AuthService.authenticate(
        credentials.email,
        credentials.password
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_message or "Invalid credentials"
        )
    
    token = AuthService.generate_mock_token(user_info.id)
    
    return LoginResponse(
        success=True,
        token=token,
        user=user_info
    )
