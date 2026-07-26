"""Invoice and payment schemas."""

from datetime import date, datetime
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
    invoice_number: str | None
    member_id: int
    member_name: str
    member_email: str | None
    member_phone: str | None
    subscription_id: int
    plan_label: str
    amount: float
    original_price: float | None
    final_amount_received: float | None
    discount_amount: float | None
    discount_percentage: float | None
    gst_amount: float | None
    total_paid: float | None
    payment_mode: str | None
    transaction_reference: str | None
    payment_date: date | None
    notes: str | None
    invoice_download_url: str | None
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


PaymentMode = Literal["cash", "upi", "card", "bank_transfer"]


class CapturePaymentRequest(BaseModel):
    final_amount_received: float = Field(..., gt=0)
    payment_mode: PaymentMode
    transaction_reference: str | None = Field(default=None, max_length=120)
    payment_date: date = Field(default_factory=date.today)
    notes: str | None = Field(default=None, max_length=500)


class CapturePaymentResponse(BaseModel):
    message: str
    data: InvoiceResponse
