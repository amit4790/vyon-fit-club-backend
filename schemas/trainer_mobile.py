"""Schemas for authenticated trainer mobile profile."""

from pydantic import BaseModel


class TrainerMeResponse(BaseModel):
    message: str = "Trainer profile"
    data: "TrainerMeData"


class TrainerMeData(BaseModel):
    user_id: int
    full_name: str
    email: str
    phone_number: str | None
    specialization: str | None
    assigned_member_count: int
    has_pin: bool = True
    is_active: bool
