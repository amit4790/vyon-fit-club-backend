"""Trainer management schemas."""

from pydantic import BaseModel, EmailStr, Field, field_validator


class TrainerBase(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    is_active: bool = True

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Trainer name is required")
        return value


class TrainerCreateRequest(TrainerBase):
    """Request model for creating a trainer."""


class TrainerUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = None
    is_active: bool | None = None

    @field_validator("full_name")
    @classmethod
    def validate_optional_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Trainer name is required")
        return value


class TrainerResponse(BaseModel):
    id: int
    full_name: str
    email: str
    role: str
    is_active: bool

    class Config:
        from_attributes = True


class TrainerListResponse(BaseModel):
    message: str
    data: list[TrainerResponse]


class TrainerOperationResponse(BaseModel):
    message: str
    data: TrainerResponse


class TrainerDeleteResponse(BaseModel):
    message: str
