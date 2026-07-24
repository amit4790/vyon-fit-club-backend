"""Member SQLAlchemy model."""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from .feedback import Feedback
    from .invoice import Invoice
    from .membership_subscription import MembershipSubscription
    from .user import User


class Member(Base):
    """Gym member profile model."""

    __tablename__ = "members"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    joined_at: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="member_profile")
    subscriptions: Mapped[list["MembershipSubscription"]] = relationship(back_populates="member")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="member")
    feedback_entries: Mapped[list["Feedback"]] = relationship(back_populates="member")
