"""Schemas for authenticated member mobile profile."""

from datetime import date

from pydantic import BaseModel


class MemberMeResponse(BaseModel):
    message: str = "Member profile"
    data: "MemberMeData"


class MemberMeData(BaseModel):
    user_id: int
    member_id: int
    full_name: str
    mobile_number: str
    email: str | None
    status: str
    joined_at: date
    trainer_id: int | None = None
    has_pin: bool = True
