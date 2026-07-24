"""Invoice SQLAlchemy model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
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
