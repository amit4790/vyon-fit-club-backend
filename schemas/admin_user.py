"""Admin user management schemas."""

from pydantic import BaseModel, EmailStr, Field, field_validator


class AdminCreateRequest(BaseModel):
    """Request payload for creating an ADMIN user."""

    full_name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    phone_number: str = Field(..., min_length=1, max_length=30)
    password: str = Field(..., min_length=6, max_length=128)
    is_active: bool = True

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Full Name is required")
        return value

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Phone Number is required")
        return value


class AdminUserResponse(BaseModel):
    """Admin user response model."""

    id: int
    full_name: str
    email: str
    phone_number: str | None
    role: str
    is_active: bool

    class Config:
        from_attributes = True


class AdminUserOperationResponse(BaseModel):
    """Create response for admin users."""

    message: str
    data: AdminUserResponse
