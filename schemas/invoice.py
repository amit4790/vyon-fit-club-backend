"""
Invoice and payment schemas.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


InvoiceStatus = Literal["pending", "paid", "failed", "cancelled"]
DeliveryStatus = Literal["sent", "skipped"]


class DeliveryResultResponse(BaseModel):
    channel: Literal["email", "sms"]
    target: str | None
    status: DeliveryStatus
    message: str
    mock_message_id: str | None


class InvoiceResponse(BaseModel):
    id: int
    member_id: int
    member_name: str
    member_email: str | None
    member_phone: str | None
    subscription_id: int
    plan_label: str
    amount: float
    status: InvoiceStatus
    issued_at: datetime
    paid_at: datetime | None


class InvoiceListResponse(BaseModel):
    message: str
    data: list[InvoiceResponse]
    pagination: dict


class InvoiceOperationResponse(BaseModel):
    message: str
    data: InvoiceResponse
    notifications: list[DeliveryResultResponse] = Field(default_factory=list)


class InvoiceStatusUpdateRequest(BaseModel):
    status: InvoiceStatus
