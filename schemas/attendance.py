"""Attendance API schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class DailyAttendanceRow(BaseModel):
    person_id: int
    person_name: str
    specialization: str | None = None
    pin: int
    punched_at: datetime
    is_late: bool


class DailyAttendanceResponse(BaseModel):
    message: str
    date: str
    data: list[DailyAttendanceRow]


class MonthlyAttendanceRow(BaseModel):
    person_id: int
    person_name: str
    specialization: str | None = None
    days_present: int
    on_time_days: int
    late_days: int
    last_check_in: datetime | None = None


class MonthlyAttendanceResponse(BaseModel):
    message: str
    year: int
    month: int
    data: list[MonthlyAttendanceRow]


class AttendancePurgeResponse(BaseModel):
    message: str
    punches_deleted: int
    raw_logs_deleted: int
    retention_days: int = Field(default=90, description="Punch retention days (compat)")
    punch_retention_days: int = Field(default=90)
    raw_log_retention_days: int = Field(default=14)
