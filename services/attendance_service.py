"""Attendance ingest, query, export, and retention."""

from __future__ import annotations

import csv
import io
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from core.config import settings
from core.device_pins import resolve_device_pin
from core.device_time import (
    gym_day_bounds_utc,
    gym_month_bounds_utc,
    parse_device_wall_clock,
    to_device_local,
)
from models import AttendancePunch, DeviceAttendanceLog, Member, User
from repositories.attendance_punch_repository import AttendancePunchRepository
from repositories.member_repository import MemberRepository
from repositories.trainer_repository import TrainerRepository

logger = logging.getLogger(__name__)

# Gym-wide late rule for trainers (can move to business_settings later). Evaluated in device TZ.
DEFAULT_SHIFT_START = time(6, 0)
DEFAULT_GRACE_MINUTES = 15
# Punch export window (alias of settings for callers that import the constant).
RETENTION_DAYS = settings.attendance_punch_retention_days

_ATTLOG_LINE_RE = re.compile(
    r"^(?:ATTLOG[:\s]*)?(\d+)\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})"
)

PersonType = str  # "trainer" | "member"


@dataclass
class DailyPunchRow:
    person_id: int
    person_name: str
    specialization: str | None
    phone_number: str | None
    pin: int
    punched_at: datetime
    is_late: bool


@dataclass
class MonthlyTrainerRow:
    person_id: int
    person_name: str
    specialization: str | None
    phone_number: str | None
    days_present: int
    on_time_days: int
    late_days: int
    last_check_in: datetime | None


@dataclass
class AttendancePunchDetail:
    punched_at: datetime
    pin: int
    is_late: bool


class AttendanceService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = AttendancePunchRepository(db)
        self.trainer_repo = TrainerRepository(db)
        self.member_repo = MemberRepository(db)

    @staticmethod
    def _parse_attlog_lines(raw_payload: str) -> list[tuple[int, datetime, str]]:
        parsed: list[tuple[int, datetime, str]] = []
        for raw_line in (raw_payload or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            match = _ATTLOG_LINE_RE.match(line)
            if not match:
                continue
            pin = int(match.group(1))
            # Device sends local gym wall clock (no TZ). Convert to real UTC.
            punched_at = parse_device_wall_clock(match.group(2))
            parsed.append((pin, punched_at, line[:500]))
        return parsed

    @staticmethod
    def payload_has_trainer_punches(raw_payload: str) -> bool:
        """Pure text check, no DB. True if any ATTLOG line belongs to a trainer PIN."""
        for pin, _punched_at, _raw_line in AttendanceService._parse_attlog_lines(raw_payload):
            resolved = resolve_device_pin(pin)
            if resolved and resolved[0] == "trainer":
                return True
        return False

    @staticmethod
    def payload_has_storable_punches(raw_payload: str) -> bool:
        """True if any ATTLOG line maps to a member or trainer PIN."""
        for pin, _punched_at, _raw_line in AttendanceService._parse_attlog_lines(raw_payload):
            if resolve_device_pin(pin):
                return True
        return False

    def ingest_attlog_payload(self, *, device_serial: str, raw_payload: str) -> int:
        """
        Parse ATTLOG text and insert member/trainer punches. Returns inserted count.

        PIN convention: member PIN = member_id; trainer PIN = 50000 + trainer_id.
        Unknown PINs and deleted members are skipped.
        """
        inserted = 0
        for pin, punched_at, raw_line in self._parse_attlog_lines(raw_payload):
            resolved = resolve_device_pin(pin)
            if not resolved:
                continue
            person_type, person_id = resolved

            if person_type == "member":
                if not self.member_repo.get_member_by_id(person_id):
                    continue
            elif person_type == "trainer":
                if not self.trainer_repo.get_trainer_by_id(person_id):
                    continue
            else:
                continue

            punch = AttendancePunch(
                device_serial=device_serial,
                pin=pin,
                person_type=person_type,
                person_id=person_id,
                punched_at=punched_at,
                raw_line=raw_line,
            )
            created = self.repo.add_punch(punch)
            if created:
                inserted += 1

        if inserted:
            self.db.commit()
        return inserted

    def process_raw_log(self, log: DeviceAttendanceLog) -> int:
        inserted = self.ingest_attlog_payload(
            device_serial=log.device_serial,
            raw_payload=log.raw_payload or "",
        )
        log.is_processed = True
        log.processed_at = datetime.now(timezone.utc)
        log.processing_error = None
        self.db.commit()
        return inserted

    @staticmethod
    def _is_late(punched_at: datetime) -> bool:
        local_time = to_device_local(punched_at).time()
        threshold_minutes = DEFAULT_SHIFT_START.hour * 60 + DEFAULT_SHIFT_START.minute + DEFAULT_GRACE_MINUTES
        punch_minutes = local_time.hour * 60 + local_time.minute
        return punch_minutes > threshold_minutes

    @staticmethod
    def _normalize_person_type(person_type: str) -> PersonType:
        value = (person_type or "").strip().lower()
        if value not in {"trainer", "member"}:
            raise ValueError("person_type must be trainer or member")
        return value

    def _trainer_name_map(self) -> dict[int, User]:
        trainers = self.trainer_repo.list_trainers()
        return {trainer.id: trainer for trainer in trainers}

    def _member_name_map(self, member_ids: set[int]) -> dict[int, Member]:
        if not member_ids:
            return {}
        members = self.member_repo.list_members_by_ids(sorted(member_ids))
        return {member.id: member for member in members}

    def get_daily_trainer_attendance(self, day: date) -> list[DailyPunchRow]:
        return self.get_daily_attendance(day, "trainer")

    def get_daily_attendance(self, day: date, person_type: str) -> list[DailyPunchRow]:
        person_type = self._normalize_person_type(person_type)
        start, end = gym_day_bounds_utc(day)
        punches = self.repo.list_punches(person_type=person_type, start_at=start, end_at=end)

        first_by_person: dict[int, AttendancePunch] = {}
        for punch in punches:
            if punch.person_id not in first_by_person:
                first_by_person[punch.person_id] = punch

        trainers = self._trainer_name_map() if person_type == "trainer" else {}
        members = (
            self._member_name_map(set(first_by_person.keys()))
            if person_type == "member"
            else {}
        )

        rows: list[DailyPunchRow] = []
        for person_id, punch in sorted(first_by_person.items(), key=lambda item: item[1].punched_at):
            if person_type == "trainer":
                trainer = trainers.get(person_id)
                rows.append(
                    DailyPunchRow(
                        person_id=person_id,
                        person_name=trainer.full_name if trainer else f"Trainer #{person_id}",
                        specialization=trainer.specialization if trainer else None,
                        phone_number=None,
                        pin=punch.pin,
                        punched_at=punch.punched_at,
                        is_late=self._is_late(punch.punched_at),
                    )
                )
            else:
                member = members.get(person_id)
                rows.append(
                    DailyPunchRow(
                        person_id=person_id,
                        person_name=member.full_name if member else f"Member #{person_id}",
                        specialization=None,
                        phone_number=member.mobile_number if member else None,
                        pin=punch.pin,
                        punched_at=punch.punched_at,
                        is_late=False,
                    )
                )
        return rows

    def get_person_day_punches(
        self, day: date, person_type: str, person_id: int
    ) -> list[AttendancePunchDetail]:
        person_type = self._normalize_person_type(person_type)
        start, end = gym_day_bounds_utc(day)
        punches = self.repo.list_punches(person_type=person_type, start_at=start, end_at=end)
        apply_late = person_type == "trainer"
        return [
            AttendancePunchDetail(
                punched_at=punch.punched_at,
                pin=punch.pin,
                is_late=self._is_late(punch.punched_at) if apply_late else False,
            )
            for punch in punches
            if punch.person_id == person_id
        ]

    def get_monthly_trainer_summary(self, year: int, month: int) -> list[MonthlyTrainerRow]:
        return self.get_monthly_summary(year, month, "trainer")

    def get_monthly_summary(self, year: int, month: int, person_type: str) -> list[MonthlyTrainerRow]:
        person_type = self._normalize_person_type(person_type)
        start, end = gym_month_bounds_utc(year, month)

        punches = self.repo.list_punches(person_type=person_type, start_at=start, end_at=end)
        trainers = self._trainer_name_map() if person_type == "trainer" else {}
        members = (
            self._member_name_map({punch.person_id for punch in punches})
            if person_type == "member"
            else {}
        )

        first_punch_by_day: dict[tuple[int, date], AttendancePunch] = {}
        for punch in punches:
            day_key = (punch.person_id, to_device_local(punch.punched_at).date())
            if day_key not in first_punch_by_day:
                first_punch_by_day[day_key] = punch

        stats: dict[int, dict] = defaultdict(
            lambda: {"days_present": 0, "on_time_days": 0, "late_days": 0, "last_check_in": None}
        )
        for (person_id, _day), punch in first_punch_by_day.items():
            bucket = stats[person_id]
            bucket["days_present"] += 1
            if person_type == "trainer" and self._is_late(punch.punched_at):
                bucket["late_days"] += 1
            else:
                bucket["on_time_days"] += 1
            if bucket["last_check_in"] is None or punch.punched_at > bucket["last_check_in"]:
                bucket["last_check_in"] = punch.punched_at

        if person_type == "trainer":
            person_ids = set(stats.keys()) | {
                trainer.id for trainer in trainers.values() if trainer.is_active
            }
        else:
            person_ids = set(stats.keys())

        rows: list[MonthlyTrainerRow] = []
        for person_id in sorted(person_ids):
            bucket = stats[person_id]
            if person_type == "trainer":
                trainer = trainers.get(person_id)
                rows.append(
                    MonthlyTrainerRow(
                        person_id=person_id,
                        person_name=trainer.full_name if trainer else f"Trainer #{person_id}",
                        specialization=trainer.specialization if trainer else None,
                        phone_number=None,
                        days_present=bucket["days_present"],
                        on_time_days=bucket["on_time_days"],
                        late_days=bucket["late_days"],
                        last_check_in=bucket["last_check_in"],
                    )
                )
            else:
                member = members.get(person_id)
                rows.append(
                    MonthlyTrainerRow(
                        person_id=person_id,
                        person_name=member.full_name if member else f"Member #{person_id}",
                        specialization=None,
                        phone_number=member.mobile_number if member else None,
                        days_present=bucket["days_present"],
                        on_time_days=bucket["on_time_days"],
                        late_days=bucket["late_days"],
                        last_check_in=bucket["last_check_in"],
                    )
                )
        return rows

    def build_month_csv(self, year: int, month: int, person_type: str = "trainer") -> str:
        person_type = self._normalize_person_type(person_type)
        start, end = gym_month_bounds_utc(year, month)

        punches = self.repo.list_punches(person_type=person_type, start_at=start, end_at=end)
        trainers = self._trainer_name_map() if person_type == "trainer" else {}
        members = (
            self._member_name_map({punch.person_id for punch in punches})
            if person_type == "member"
            else {}
        )

        output = io.StringIO()
        writer = csv.writer(output)
        if person_type == "trainer":
            writer.writerow(
                ["date", "check_in_time", "trainer_id", "trainer_name", "specialization", "pin"]
            )
            for punch in punches:
                trainer = trainers.get(punch.person_id)
                punched_at = to_device_local(punch.punched_at)
                writer.writerow(
                    [
                        punched_at.date().isoformat(),
                        punched_at.strftime("%H:%M:%S"),
                        punch.person_id,
                        trainer.full_name if trainer else f"Trainer #{punch.person_id}",
                        trainer.specialization if trainer else "",
                        punch.pin,
                    ]
                )
        else:
            writer.writerow(
                ["date", "check_in_time", "member_id", "member_name", "mobile", "pin"]
            )
            for punch in punches:
                member = members.get(punch.person_id)
                punched_at = to_device_local(punch.punched_at)
                writer.writerow(
                    [
                        punched_at.date().isoformat(),
                        punched_at.strftime("%H:%M:%S"),
                        punch.person_id,
                        member.full_name if member else f"Member #{punch.person_id}",
                        member.mobile_number if member else "",
                        punch.pin,
                    ]
                )
        return output.getvalue()

    def build_day_csv(self, day: date, person_type: str = "trainer") -> str:
        """Export first check-in per person for one gym-local day (IST)."""
        person_type = self._normalize_person_type(person_type)
        start, end = gym_day_bounds_utc(day)
        punches = self.repo.list_punches(person_type=person_type, start_at=start, end_at=end)
        trainers = self._trainer_name_map() if person_type == "trainer" else {}
        members = (
            self._member_name_map({punch.person_id for punch in punches})
            if person_type == "member"
            else {}
        )

        first_by_person: dict[int, AttendancePunch] = {}
        for punch in punches:
            if punch.person_id not in first_by_person:
                first_by_person[punch.person_id] = punch

        output = io.StringIO()
        writer = csv.writer(output)
        if person_type == "trainer":
            writer.writerow(
                [
                    "date",
                    "check_in_time",
                    "trainer_id",
                    "trainer_name",
                    "specialization",
                    "pin",
                    "is_late",
                ]
            )
            for person_id, punch in sorted(first_by_person.items(), key=lambda item: item[1].punched_at):
                trainer = trainers.get(person_id)
                punched_at = to_device_local(punch.punched_at)
                writer.writerow(
                    [
                        punched_at.date().isoformat(),
                        punched_at.strftime("%H:%M:%S"),
                        person_id,
                        trainer.full_name if trainer else f"Trainer #{person_id}",
                        trainer.specialization if trainer else "",
                        punch.pin,
                        "yes" if self._is_late(punch.punched_at) else "no",
                    ]
                )
        else:
            writer.writerow(
                ["date", "check_in_time", "member_id", "member_name", "mobile", "pin"]
            )
            for person_id, punch in sorted(first_by_person.items(), key=lambda item: item[1].punched_at):
                member = members.get(person_id)
                punched_at = to_device_local(punch.punched_at)
                writer.writerow(
                    [
                        punched_at.date().isoformat(),
                        punched_at.strftime("%H:%M:%S"),
                        person_id,
                        member.full_name if member else f"Member #{person_id}",
                        member.mobile_number if member else "",
                        punch.pin,
                    ]
                )
        return output.getvalue()

    @staticmethod
    def calendar_retention_cutoff_utc(now: datetime | None = None) -> datetime:
        """
        Oldest punch instant to keep when purging on a schedule (e.g. 1st of month).

        Keeps the current calendar month plus (retention_months - 1) prior full months.
        Example: purge on 1 Oct with retention_months=3 deletes punches before 1 Aug IST.
        """
        months = max(1, int(settings.attendance_punch_retention_months))
        now = now or datetime.now(timezone.utc)
        today_local = to_device_local(now).date()
        year = today_local.year
        month = today_local.month - (months - 1)
        while month <= 0:
            month += 12
            year -= 1
        cutoff_day = date(year, month, 1)
        cutoff_utc, _ = gym_day_bounds_utc(cutoff_day)
        return cutoff_utc

    def purge_old_records(self) -> dict[str, int]:
        punch_days = settings.attendance_punch_retention_days
        raw_days = settings.device_raw_log_retention_days
        now = datetime.now(timezone.utc)
        punch_cutoff = self.calendar_retention_cutoff_utc(now)
        raw_cutoff = now - timedelta(days=raw_days)

        punches_deleted = self.repo.delete_older_than(punch_cutoff)

        raw_result = self.db.execute(
            delete(DeviceAttendanceLog).where(DeviceAttendanceLog.uploaded_at < raw_cutoff)
        )
        raw_deleted = int(raw_result.rowcount or 0)
        self.db.commit()
        return {
            "punches_deleted": punches_deleted,
            "raw_logs_deleted": raw_deleted,
            "retention_days": punch_days,
            "punch_retention_days": punch_days,
            "punch_retention_months": settings.attendance_punch_retention_months,
            "raw_log_retention_days": raw_days,
            "punch_cutoff_utc": punch_cutoff.isoformat(),
        }
