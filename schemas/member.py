"""
Member Management Schemas
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class MemberBase(BaseModel):
    """Shared member fields."""

    full_name: str = Field(..., min_length=1, max_length=120, description="Member full name")
    mobile_number: str = Field(..., min_length=1, max_length=30, description="Member mobile number")
    joining_date: date = Field(default_factory=date.today, description="Member joining date")
    status: Literal["active", "inactive"] = Field(default="active", description="Member status")

    email: EmailStr | None = Field(default=None, description="Member email address")
    date_of_birth: date | None = Field(default=None, description="Member date of birth")
    gender: Literal["male", "female", "other"] | None = Field(default=None, description="Member gender")
    address: str | None = Field(default=None, description="Member address")
    emergency_contact: str | None = Field(default=None, description="Emergency contact name")
    emergency_phone: str | None = Field(default=None, description="Emergency contact phone")
    notes: str | None = Field(default=None, description="Additional notes")

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Full Name is required")
        return value

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile_number(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Mobile Number is required")
        return value


class MemberCreateRequest(MemberBase):
    """Request model for creating a member."""


class MemberUpdateRequest(BaseModel):
    """Request model for updating a member."""

    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    mobile_number: str | None = Field(default=None, min_length=1, max_length=30)
    joining_date: date | None = None
    status: Literal["active", "inactive"] | None = None

    email: EmailStr | None = None
    date_of_birth: date | None = None
    gender: Literal["male", "female", "other"] | None = None
    address: str | None = None
    emergency_contact: str | None = None
    emergency_phone: str | None = None
    notes: str | None = None

    @field_validator("full_name")
    @classmethod
    def validate_optional_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Full Name is required")
        return value

    @field_validator("mobile_number")
    @classmethod
    def validate_optional_mobile_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Mobile Number is required")
        return value


class MemberResponse(BaseModel):
    """Member response model."""

    id: int
    full_name: str
    mobile_number: str
    joining_date: date
    status: str

    email: str | None
    date_of_birth: date | None
    gender: str | None
    address: str | None
    emergency_contact: str | None
    emergency_phone: str | None
    notes: str | None
    device_user_id: str | None = None
    device_uid: int | None = None
    device_card: int | None = None
    device_sync_status: str | None = None

    class Config:
        from_attributes = True


class PaginationMeta(BaseModel):
    """Pagination metadata model."""

    page: int
    page_size: int
    total_items: int
    total_pages: int


class MemberListResponse(BaseModel):
    """Paginated member list response."""

    message: str
    data: list[MemberResponse]
    pagination: PaginationMeta


class MemberOperationResponse(BaseModel):
    """Create/update response for members."""

    message: str
    data: MemberResponse


class MemberDeleteResponse(BaseModel):
    """Delete response for members."""

    message: str
