"""Parsed attendance punch records from ZKTeco ATTLOG."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class AttendancePunch(Base):
    """
    One device punch (check-in) resolved to a member or trainer.

    Raw ATTLOG uploads stay in device_attendance_logs; this table is the
    queryable attendance view used by admin UI and exports.
    """

    __tablename__ = "attendance_punches"
    __table_args__ = (
        UniqueConstraint(
            "device_serial",
            "pin",
            "punched_at",
            name="uq_attendance_punches_device_pin_time",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_serial: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    pin: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    person_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    person_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    punched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    raw_line: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
