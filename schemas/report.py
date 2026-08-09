"""Report schemas for admin analytics."""

from pydantic import BaseModel, Field


class ReportsSummaryData(BaseModel):
    total_members: int = Field(..., description="Total members")
    active_members: int = Field(..., description="Active members")
    total_invoices: int = Field(..., description="Total invoices")
    paid_invoices: int = Field(..., description="Paid invoices")
    pending_invoices: int = Field(..., description="Pending invoices")
    collected_revenue: float = Field(..., description="Revenue from paid invoices")
    outstanding_revenue: float = Field(..., description="Outstanding amount from unpaid invoices")
    target_revenue: float = Field(..., description="Editable revenue target")
    revenue_gap: float = Field(..., description="Target revenue minus collected revenue")
    average_invoice_value: float = Field(..., description="Average invoice amount")
    expiring_memberships_next_30_days: int = Field(..., description="Memberships expiring in next 30 days")


class ReportsSummaryResponse(BaseModel):
    message: str
    data: ReportsSummaryData


class UpdateTargetRevenueRequest(BaseModel):
    target_revenue: float = Field(..., ge=0, description="Target revenue amount")


class UpdateTargetRevenueResponse(BaseModel):
    message: str
    data: ReportsSummaryData
