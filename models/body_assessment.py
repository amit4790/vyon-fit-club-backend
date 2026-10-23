"""Body composition assessments for gym members."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class BodyAssessment(Base):
    __tablename__ = "body_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), nullable=False, index=True)
    conducted_by_trainer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    assessed_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    assessment_type: Mapped[str] = mapped_column(String(40), nullable=False, server_default="monthly_review")
    measurement_method: Mapped[str | None] = mapped_column(String(80), nullable=True)
    device_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="completed", index=True)
    primary_goal: Mapped[str | None] = mapped_column(String(200), nullable=True)
    trainer_observations: Mapped[str | None] = mapped_column(Text, nullable=True)
    medical_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    medical_questionnaire: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    next_assessment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    metrics: Mapped[list["BodyAssessmentMetric"]] = relationship(
        "BodyAssessmentMetric",
        back_populates="assessment",
        cascade="all, delete-orphan",
    )


class BodyAssessmentMetric(Base):
    __tablename__ = "body_assessment_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("body_assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_key: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    value_numeric: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="machine")
    body_region: Mapped[str | None] = mapped_column(String(40), nullable=True)
    side: Mapped[str | None] = mapped_column(String(10), nullable=True)

    assessment: Mapped[BodyAssessment] = relationship("BodyAssessment", back_populates="metrics")
