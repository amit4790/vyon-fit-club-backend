"""
Authentication Schemas
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Literal


class LoginRequest(BaseModel):
    """Login request model"""
    
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="User password")
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "admin@vyon.com",
                "password": "password123"
            }
        }


class UserInfo(BaseModel):
    """User information model"""
    
    id: str = Field(..., description="User ID")
    name: str = Field(..., description="User full name")
    email: str = Field(..., description="User email")
    role: Literal["admin", "trainer", "member"] = Field(..., description="User role")


class LoginResponse(BaseModel):
    """Successful login response model"""
    
    success: bool = Field(True, description="Whether login was successful")
    token: str = Field(..., description="Authentication token (mock JWT)")
    user: UserInfo = Field(..., description="Authenticated user information")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "token": "mock-jwt-token-xyz123",
                "user": {
                    "id": "admin_001",
                    "name": "John Doe",
                    "email": "admin@vyon.com",
                    "role": "admin"
                }
            }
        }
