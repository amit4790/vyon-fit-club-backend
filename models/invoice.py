"""Invoice SQLAlchemy model."""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from .member import Member
    from .membership_subscription import MembershipSubscription


class Invoice(Base):
    """Billing invoice for membership payments."""

    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("membership_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invoice_number: Mapped[str | None] = mapped_column(String(40), unique=True, nullable=True, index=True)
    original_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    final_amount_received: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    discount_amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    discount_percentage: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    gst_amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    total_paid: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    payment_mode: Mapped[str | None] = mapped_column(String(30), nullable=True)
    transaction_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    invoice_pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    member: Mapped["Member"] = relationship(back_populates="invoices")
    subscription: Mapped["MembershipSubscription"] = relationship(back_populates="invoices")
