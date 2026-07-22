"""
Authentication Service
Handles user authentication and token generation
"""

from typing import Optional, Tuple
from data.mock_users import verify_credentials, MockUser
from schemas.auth import UserInfo


class AuthService:
    """Service for authentication operations"""
    
    @staticmethod
    def authenticate(email: str, password: str) -> Tuple[bool, Optional[UserInfo], Optional[str]]:
        """
        Authenticate user with email and password
        
        Returns:
            Tuple of (success: bool, user_info: UserInfo, error_message: str)
        """
        user = verify_credentials(email, password)
        
        if not user:
            return False, None, "Invalid email or password"
        
        user_info = UserInfo(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.role
        )
        
        return True, user_info, None
    
    @staticmethod
    def generate_mock_token(user_id: str) -> str:
        """
        Generate a mock JWT token
        In Phase 5, this will use actual JWT generation
        """
        return f"mock-jwt-token-{user_id}"
