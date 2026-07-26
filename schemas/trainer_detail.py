"""Trainer detail schemas."""

from pydantic import BaseModel


class TrainerAssignedMember(BaseModel):
    id: int
    full_name: str
    mobile_number: str


class TrainerDetailResponse(BaseModel):
    id: int
    full_name: str
    email: str
    phone_number: str | None
    specialization: str | None
    role: str
    is_active: bool
    assigned_members: list[TrainerAssignedMember]


class TrainerDetailOperationResponse(BaseModel):
    message: str
    data: TrainerDetailResponse
