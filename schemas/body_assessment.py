"""Body assessment API schemas."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from core.body_metrics import METRIC_UNITS, TARGETABLE_METRIC_KEYS
from schemas.medical_questionnaire import MedicalQuestionnaire


class MetricInput(BaseModel):
    metric_key: str = Field(..., min_length=1, max_length=60)
    value: float
    source: Literal["machine", "manual", "calculated"] = "machine"


class BodyAssessmentCreateRequest(BaseModel):
    conducted_by_trainer_id: int = Field(..., ge=1)
    assessed_on: date
    assessment_type: Literal["initial", "monthly_review", "follow_up", "other"] = "monthly_review"
    measurement_method: str | None = Field(None, max_length=80)
    device_name: str | None = Field(None, max_length=120)
    primary_goal: str | None = Field(None, max_length=200)
    trainer_observations: str | None = Field(None, max_length=4000)
    medical_history: str | None = Field(None, max_length=4000)
    medical_questionnaire: MedicalQuestionnaire | None = None
    metric_targets: dict[str, float] | None = None
    next_assessment_date: date | None = None
    metrics: list[MetricInput] = Field(default_factory=list)

    @field_validator("metric_targets")
    @classmethod
    def validate_metric_targets(cls, targets: dict[str, float] | None) -> dict[str, float] | None:
        if not targets:
            return None
        cleaned: dict[str, float] = {}
        for key, value in targets.items():
            if key not in TARGETABLE_METRIC_KEYS:
                raise ValueError(f"Invalid target metric key: {key}")
            if key not in METRIC_UNITS:
                raise ValueError(f"Unknown target metric key: {key}")
            cleaned[key] = float(value)
        return cleaned or None

    @field_validator("metrics")
    @classmethod
    def require_weight(cls, metrics: list[MetricInput]) -> list[MetricInput]:
        if not any(m.metric_key == "weight_kg" for m in metrics):
            raise ValueError("weight_kg is required")
        return metrics


class MetricResponse(BaseModel):
    metric_key: str
    value: float
    unit: str
    source: str


class BodyAssessmentResponse(BaseModel):
    id: int
    member_id: int
    conducted_by_trainer_id: int
    conducted_by_trainer_name: str | None = None
    assessed_on: date
    assessment_type: str
    measurement_method: str | None
    device_name: str | None
    status: str
    primary_goal: str | None
    trainer_observations: str | None
    medical_history: str | None
    medical_questionnaire: MedicalQuestionnaire | None = None
    metric_targets: dict[str, float] | None = None
    next_assessment_date: date | None
    completed_at: datetime | None
    metrics: list[MetricResponse]


class BodyAssessmentListResponse(BaseModel):
    message: str
    data: list[BodyAssessmentResponse]


class BodyAssessmentOperationResponse(BaseModel):
    message: str
    data: BodyAssessmentResponse


class BodyAnalysisOverviewResponse(BaseModel):
    message: str
    member_id: int
    assessment_count: int
    latest_assessed_on: date | None
    next_assessment_date: date | None
    latest_metrics: dict[str, float]


class ProgressMetricChange(BaseModel):
    metric_key: str
    unit: str
    baseline_value: float | None
    latest_value: float | None
    change: float | None
    change_label: str | None = None


class BodyProgressResponse(BaseModel):
    message: str
    member_id: int
    months: int
    baseline_assessed_on: date | None
    latest_assessed_on: date | None
    changes: list[ProgressMetricChange]


class GymTrainerOption(BaseModel):
    id: int
    full_name: str


class GymTrainerListResponse(BaseModel):
    message: str
    data: list[GymTrainerOption]
