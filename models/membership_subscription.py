"""Membership subscription SQLAlchemy model."""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from .invoice import Invoice
    from .member import Member
    from .membership_plan import MembershipPlan


class MembershipSubscription(Base):
    """Member to plan subscription record."""

    __tablename__ = "membership_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("membership_plans.id", ondelete="RESTRICT"), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    duration_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bonus_duration_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bonus_duration_unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    duration_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    base_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    tax_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    tax_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    payment_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    member: Mapped["Member"] = relationship(back_populates="subscriptions")
    plan: Mapped["MembershipPlan"] = relationship(back_populates="subscriptions")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="subscription")
