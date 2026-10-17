"""Body assessment persistence."""

from datetime import date

from sqlalchemy import Select, desc, select
from sqlalchemy.orm import Session, selectinload

from models.body_assessment import BodyAssessment, BodyAssessmentMetric


class BodyAssessmentRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, assessment: BodyAssessment) -> BodyAssessment:
        self.db.add(assessment)
        self.db.flush()
        return assessment

    def get_by_id(self, assessment_id: int) -> BodyAssessment | None:
        return self.db.execute(
            select(BodyAssessment)
            .options(selectinload(BodyAssessment.metrics))
            .where(BodyAssessment.id == assessment_id)
        ).scalar_one_or_none()

    def list_for_member(
        self,
        member_id: int,
        *,
        status: str | None = "completed",
        limit: int = 100,
    ) -> list[BodyAssessment]:
        query: Select[tuple[BodyAssessment]] = (
            select(BodyAssessment)
            .options(selectinload(BodyAssessment.metrics))
            .where(BodyAssessment.member_id == member_id)
            .order_by(desc(BodyAssessment.assessed_on), desc(BodyAssessment.id))
            .limit(limit)
        )
        if status:
            query = query.where(BodyAssessment.status == status)
        return list(self.db.execute(query).scalars().all())

    def get_completed_on_date(self, member_id: int, assessed_on: date) -> BodyAssessment | None:
        return self.db.execute(
            select(BodyAssessment)
            .where(
                BodyAssessment.member_id == member_id,
                BodyAssessment.assessed_on == assessed_on,
                BodyAssessment.status == "completed",
            )
            .limit(1)
        ).scalar_one_or_none()

    def list_completed_since(self, member_id: int, since: date) -> list[BodyAssessment]:
        return list(
            self.db.execute(
                select(BodyAssessment)
                .options(selectinload(BodyAssessment.metrics))
                .where(
                    BodyAssessment.member_id == member_id,
                    BodyAssessment.status == "completed",
                    BodyAssessment.assessed_on >= since,
                )
                .order_by(BodyAssessment.assessed_on.asc(), BodyAssessment.id.asc())
            )
            .scalars()
            .all()
        )
