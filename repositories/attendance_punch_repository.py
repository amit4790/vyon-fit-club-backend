"""Attendance punch persistence."""

from datetime import datetime

from sqlalchemy import Select, delete, select
from sqlalchemy.orm import Session

from models import AttendancePunch


class AttendancePunchRepository:
    def __init__(self, db: Session):
        self.db = db

    def add_punch(self, punch: AttendancePunch) -> AttendancePunch | None:
        """Insert punch; ignore duplicates on unique constraint."""
        existing = self.db.execute(
            select(AttendancePunch).where(
                AttendancePunch.device_serial == punch.device_serial,
                AttendancePunch.pin == punch.pin,
                AttendancePunch.punched_at == punch.punched_at,
            )
        ).scalar_one_or_none()
        if existing:
            return None

        self.db.add(punch)
        self.db.flush()
        return punch

    def list_punches(
        self,
        *,
        person_type: str | None,
        start_at: datetime,
        end_at: datetime,
    ) -> list[AttendancePunch]:
        statement: Select[tuple[AttendancePunch]] = (
            select(AttendancePunch)
            .where(
                AttendancePunch.punched_at >= start_at,
                AttendancePunch.punched_at < end_at,
            )
            .order_by(AttendancePunch.punched_at.asc(), AttendancePunch.id.asc())
        )
        if person_type:
            statement = statement.where(AttendancePunch.person_type == person_type)
        return list(self.db.execute(statement).scalars().all())

    def delete_older_than(self, cutoff: datetime) -> int:
        result = self.db.execute(
            delete(AttendancePunch).where(AttendancePunch.punched_at < cutoff)
        )
        return int(result.rowcount or 0)
