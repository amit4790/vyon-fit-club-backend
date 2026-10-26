"""Member-facing (read-only) body assessment API schemas."""

from datetime import date

from pydantic import BaseModel

from schemas.body_assessment import MetricResponse


class MemberBodyAssessmentSummary(BaseModel):
    id: int
    assessed_on: date
    fitness_goals: str | None = None


class MemberBodyAssessmentDetail(BaseModel):
    id: int
    assessed_on: date
    fitness_goals: str | None = None
    metrics: list[MetricResponse]
    metric_targets: dict[str, float] | None = None


class MemberBodyAssessmentListResponse(BaseModel):
    message: str
    data: list[MemberBodyAssessmentSummary]


class MemberBodyAssessmentOperationResponse(BaseModel):
    message: str
    data: MemberBodyAssessmentDetail
