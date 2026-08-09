"""Business settings model (singleton-style configuration)."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class BusinessSetting(Base):
    """
    Gym-level business settings.

    Expected to contain a single row (id=1) for current target revenue.
    """

    __tablename__ = "business_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_revenue: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
