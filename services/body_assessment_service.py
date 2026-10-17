"""Body assessment business logic."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from core.body_metrics import (
    METRIC_BMI,
    METRIC_BODY_FAT_PCT,
    METRIC_BMR_KCAL,
    METRIC_HEIGHT_CM,
    METRIC_UNITS,
    METRIC_WEIGHT_KG,
    METRIC_SOURCE_CALCULATED,
    METRIC_SOURCE_MACHINE,
    PROGRESS_SUMMARY_METRICS,
    calculate_bmi,
)
from models.body_assessment import BodyAssessment, BodyAssessmentMetric
from repositories.body_assessment_repository import BodyAssessmentRepository
from repositories.member_repository import MemberRepository
from repositories.trainer_repository import TrainerRepository
from schemas.body_assessment import (
    BodyAssessmentCreateRequest,
    BodyAssessmentResponse,
    BodyAnalysisOverviewResponse,
    BodyProgressResponse,
    MetricResponse,
    ProgressMetricChange,
)


class DuplicateAssessmentDateError(Exception):
    pass


class BodyAssessmentService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = BodyAssessmentRepository(db)
        self.member_repo = MemberRepository(db)
        self.trainer_repo = TrainerRepository(db)

    def _trainer_name(self, trainer_id: int) -> str | None:
        trainer = self.trainer_repo.get_trainer_by_id(trainer_id)
        return trainer.full_name if trainer else None

    def _metrics_map(self, assessment: BodyAssessment) -> dict[str, float]:
        return {metric.metric_key: metric.value_numeric for metric in assessment.metrics}

    def _to_response(self, assessment: BodyAssessment) -> BodyAssessmentResponse:
        return BodyAssessmentResponse(
            id=assessment.id,
            member_id=assessment.member_id,
            conducted_by_trainer_id=assessment.conducted_by_trainer_id,
            conducted_by_trainer_name=self._trainer_name(assessment.conducted_by_trainer_id),
            assessed_on=assessment.assessed_on,
            assessment_type=assessment.assessment_type,
            measurement_method=assessment.measurement_method,
            device_name=assessment.device_name,
            status=assessment.status,
            primary_goal=assessment.primary_goal,
            trainer_observations=assessment.trainer_observations,
            medical_history=assessment.medical_history,
            next_assessment_date=assessment.next_assessment_date,
            completed_at=assessment.completed_at,
            metrics=[
                MetricResponse(
                    metric_key=m.metric_key,
                    value=m.value_numeric,
                    unit=m.unit,
                    source=m.source,
                )
                for m in assessment.metrics
            ],
        )

    def create_assessment(self, member_id: int, payload: BodyAssessmentCreateRequest) -> BodyAssessmentResponse:
        if not self.member_repo.get_member_by_id(member_id):
            raise ValueError("Member not found")

        trainer = self.trainer_repo.get_trainer_by_id(payload.conducted_by_trainer_id)
        if not trainer or not trainer.is_active:
            raise ValueError("Trainer not found")

        if self.repo.get_completed_on_date(member_id, payload.assessed_on):
            raise DuplicateAssessmentDateError("An assessment already exists for this date")

        now = datetime.now(timezone.utc)
        assessment = BodyAssessment(
            member_id=member_id,
            conducted_by_trainer_id=payload.conducted_by_trainer_id,
            assessed_on=payload.assessed_on,
            assessment_type=payload.assessment_type,
            measurement_method=payload.measurement_method,
            device_name=payload.device_name,
            status="completed",
            primary_goal=payload.primary_goal,
            trainer_observations=payload.trainer_observations,
            medical_history=payload.medical_history,
            next_assessment_date=payload.next_assessment_date,
            completed_at=now,
        )

        weight: float | None = None
        height: float | None = None
        has_bmi = False

        self.repo.add(assessment)
        for item in payload.metrics:
            unit = METRIC_UNITS.get(item.metric_key)
            if not unit:
                raise ValueError(f"Unknown metric key: {item.metric_key}")
            if item.metric_key == METRIC_WEIGHT_KG:
                weight = item.value
            if item.metric_key == METRIC_HEIGHT_CM:
                height = item.value
            if item.metric_key == METRIC_BMI:
                has_bmi = True
            assessment.metrics.append(
                BodyAssessmentMetric(
                    metric_key=item.metric_key,
                    value_numeric=item.value,
                    unit=unit,
                    source=item.source,
                )
            )

        bmi = calculate_bmi(weight, height)
        if bmi is not None and not has_bmi:
            assessment.metrics.append(
                BodyAssessmentMetric(
                    metric_key=METRIC_BMI,
                    value_numeric=bmi,
                    unit=METRIC_UNITS[METRIC_BMI],
                    source=METRIC_SOURCE_CALCULATED,
                )
            )

        self.db.commit()
        self.db.refresh(assessment)
        return self._to_response(assessment)

    def list_assessments(self, member_id: int) -> list[BodyAssessmentResponse]:
        rows = self.repo.list_for_member(member_id)
        return [self._to_response(row) for row in rows]

    def get_assessment(self, assessment_id: int) -> BodyAssessmentResponse | None:
        row = self.repo.get_by_id(assessment_id)
        if not row:
            return None
        return self._to_response(row)

    def get_overview(self, member_id: int) -> BodyAnalysisOverviewResponse:
        rows = self.repo.list_for_member(member_id, limit=1)
        latest = rows[0] if rows else None
        all_rows = self.repo.list_for_member(member_id, limit=500)
        latest_metrics: dict[str, float] = self._metrics_map(latest) if latest else {}
        return BodyAnalysisOverviewResponse(
            message="Body analysis overview",
            member_id=member_id,
            assessment_count=len(all_rows),
            latest_assessed_on=latest.assessed_on if latest else None,
            next_assessment_date=latest.next_assessment_date if latest else None,
            latest_metrics=latest_metrics,
        )

    def get_progress(self, member_id: int, months: int = 3) -> BodyProgressResponse:
        months = max(1, min(months, 24))
        since = date.today() - timedelta(days=months * 31)
        rows = self.repo.list_completed_since(member_id, since)
        baseline = rows[0] if rows else None
        latest = rows[-1] if rows else None
        baseline_map = self._metrics_map(baseline) if baseline else {}
        latest_map = self._metrics_map(latest) if latest else {}

        changes: list[ProgressMetricChange] = []
        for key in PROGRESS_SUMMARY_METRICS:
            unit = METRIC_UNITS[key]
            base_val = baseline_map.get(key)
            latest_val = latest_map.get(key)
            change = None
            label = None
            if base_val is not None and latest_val is not None:
                change = round(latest_val - base_val, 2)
                if key == METRIC_BODY_FAT_PCT:
                    label = f"{change:+.1f} percentage points"
                elif key == METRIC_WEIGHT_KG or key.endswith("_kg"):
                    label = f"{change:+.1f} kg"
                elif key.endswith("_cm"):
                    label = f"{change:+.1f} cm"
                elif key == METRIC_BMR_KCAL:
                    label = f"{change:+.0f} kcal"
            changes.append(
                ProgressMetricChange(
                    metric_key=key,
                    unit=unit,
                    baseline_value=base_val,
                    latest_value=latest_val,
                    change=change,
                    change_label=label,
                )
            )

        return BodyProgressResponse(
            message="Body progress",
            member_id=member_id,
            months=months,
            baseline_assessed_on=baseline.assessed_on if baseline else None,
            latest_assessed_on=latest.assessed_on if latest else None,
            changes=changes,
        )
