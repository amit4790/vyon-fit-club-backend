"""Schemas for authenticated profile responses."""

from pydantic import BaseModel, Field


class AdminProfileResponse(BaseModel):
    id: int
    full_name: str
    email: str
    phone_number: str | None
    role: str
    is_active: bool
    joined_date: str = Field(..., description="ISO formatted account creation timestamp")
