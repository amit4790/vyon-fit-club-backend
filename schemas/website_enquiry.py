"""Public website enquiry schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

EnquiryStatus = Literal["new", "contacted", "closed"]


class WebsiteEnquiryCreateRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=120)
    phone_number: str = Field(..., min_length=10, max_length=15)
    email: str | None = Field(default=None, max_length=255)
    intent: str = Field(..., max_length=40)
    plan_interest: str | None = Field(default=None, max_length=120)

    @field_validator("phone_number")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        if len(digits) != 10:
            raise ValueError("Phone number must be a valid 10-digit Indian mobile number")
        return digits


class WebsiteEnquiryCreateResponse(BaseModel):
    message: str
    enquiry_id: int


class WebsiteEnquiryResponse(BaseModel):
    id: int
    full_name: str
    phone_number: str
    email: str | None
    intent: str
    plan_interest: str | None
    notes: str | None
    status: EnquiryStatus
    created_at: datetime

    class Config:
        from_attributes = True


class WebsiteEnquiryListResponse(BaseModel):
    data: list[WebsiteEnquiryResponse]
    new_count: int


class WebsiteEnquiryUpdateRequest(BaseModel):
    status: EnquiryStatus | None = None
    notes: str | None = Field(default=None, max_length=2000)


class WebsiteEnquiryCountResponse(BaseModel):
    new_count: int
