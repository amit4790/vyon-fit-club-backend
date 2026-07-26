"""
Subscription and Membership Plan Schemas
"""

from datetime import date
from pydantic import BaseModel, Field


class PlanOptionResponse(BaseModel):
    id: int
    sku: str
    label: str
    variant: str | None
    duration_months: int
    duration_label: str
    base_price: float
    tax_percent: float
    tax_amount: float
    total_price: float


class PlanFamilyResponse(BaseModel):
    family: str
    description: str
    includes: list[str]
    options: list[PlanOptionResponse]


class PlanCatalogResponse(BaseModel):
    message: str
    data: list[PlanFamilyResponse]


class PlanPriceUpdateRequest(BaseModel):
    base_price: float = Field(..., gt=0)
    tax_percent: float | None = Field(default=None, ge=0, le=100)


class PlanOptionOperationResponse(BaseModel):
    message: str
    data: PlanOptionResponse


class AssignSubscriptionRequest(BaseModel):
    plan_id: int = Field(..., ge=1)
    start_date: date = Field(default_factory=date.today)


class SubscriptionResponse(BaseModel):
    id: int
    member_id: int
    member_name: str | None = None
    plan_id: int
    plan_family: str
    plan_variant: str | None
    plan_label: str
    duration_label: str
    start_date: date
    end_date: date
    status: str
    base_price: float
    tax_percent: float
    tax_amount: float
    total_amount: float
    payment_status: str


class SubscriptionNotificationResponse(BaseModel):
    channel: str
    target: str | None
    status: str
    message: str
    mock_message_id: str | None


class SubscriptionOperationResponse(BaseModel):
    message: str
    data: SubscriptionResponse
    notifications: list[SubscriptionNotificationResponse] = Field(default_factory=list)


class MemberSubscriptionsResponse(BaseModel):
    message: str
    data: list[SubscriptionResponse]


class ExpiringSubscriptionsResponse(BaseModel):
    message: str
    data: list[SubscriptionResponse]
    pagination: dict
