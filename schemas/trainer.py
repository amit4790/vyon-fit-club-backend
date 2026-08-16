"""Trainer management schemas."""

from pydantic import BaseModel, EmailStr, Field, field_validator


class TrainerBase(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    phone_number: str = Field(..., min_length=1, max_length=30)
    specialization: str | None = Field(default=None, max_length=120)
    is_active: bool = True

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Trainer name is required")
        return value


class TrainerCreateRequest(TrainerBase):
    """Request model for creating a trainer (no app login)."""

    temporary_password: str | None = Field(default=None, min_length=6, max_length=128)


class TrainerUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = None
    phone_number: str | None = Field(default=None, min_length=1, max_length=30)
    specialization: str | None = Field(default=None, max_length=120)
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
    phone_number: str | None
    specialization: str | None
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


class TrainerDeviceSyncResponse(BaseModel):
    message: str
    trainers_queued: int
    commands_queued: int
