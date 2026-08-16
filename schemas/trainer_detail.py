"""Trainer detail schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class TrainerAssignedMember(BaseModel):
    id: int
    full_name: str
    mobile_number: str
    status: str | None = None
    assigned_at: datetime | None = None


class TrainerDetailResponse(BaseModel):
    id: int
    full_name: str
    email: str
    phone_number: str | None
    specialization: str | None
    role: str
    is_active: bool
    assigned_member_count: int = 0
    assigned_members: list[TrainerAssignedMember]


class TrainerDetailOperationResponse(BaseModel):
    message: str
    data: TrainerDetailResponse


class AssignMemberToTrainerRequest(BaseModel):
    member_id: int = Field(..., gt=0)


class AssignMemberToTrainerResponse(BaseModel):
    message: str
    data: TrainerAssignedMember


class UnassignMemberFromTrainerResponse(BaseModel):
    message: str
