"""
Authentication Schemas
"""

from pydantic import BaseModel, Field
from typing import Literal


class LoginRequest(BaseModel):
    """Login request model"""
    
    identifier: str = Field(..., description="User email address or phone number")
    password: str = Field(..., description="User password")
    
class UserInfo(BaseModel):
    """User information model"""
    
    id: str = Field(..., description="User ID")
    name: str = Field(..., description="User full name")
    email: str = Field(..., description="User email")
    role: Literal["SUPER_ADMIN", "ADMIN", "TRAINER", "MEMBER"] = Field(..., description="User role")


class LoginResponse(BaseModel):
    """Successful login response model"""
    
    success: bool = Field(True, description="Whether login was successful")
    token: str = Field(..., description="Authentication token")
    user: UserInfo = Field(..., description="Authenticated user information")
    
