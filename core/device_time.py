"""Device wall-clock timezone helpers for ZKTeco ATTLOG punches."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from core.config import settings


def device_zone() -> ZoneInfo:
    """Gym device timezone (ZKTeco sends local wall clock with no offset)."""
    return ZoneInfo(settings.device_timezone)


def parse_device_wall_clock(value: str) -> datetime:
    """
    Parse ``YYYY-MM-DD HH:MM:SS`` from the device as local gym time, return UTC.

    Devices do not send a timezone. Labeling the string as UTC made India times
    appear ~5h30m ahead in the admin UI.
    """
    naive = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return naive.replace(tzinfo=device_zone()).astimezone(timezone.utc)


def reinterpret_mislabeled_utc_as_device_local(stored: datetime) -> datetime:
    """
    Fix historical punches that were stored by attaching UTC to a local clock.

    Takes the UTC wall-clock components, treats them as device-local, returns UTC.
    """
    as_utc = stored.astimezone(timezone.utc)
    naive = as_utc.replace(tzinfo=None)
    return naive.replace(tzinfo=device_zone()).astimezone(timezone.utc)


def gym_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """UTC [start, end) covering one calendar day in the gym timezone."""
    start_local = datetime.combine(day, time.min, tzinfo=device_zone())
    start_utc = start_local.astimezone(timezone.utc)
    return start_utc, start_utc + timedelta(days=1)


def gym_month_bounds_utc(year: int, month: int) -> tuple[datetime, datetime]:
    """UTC [start, end) covering one calendar month in the gym timezone."""
    start_day = date(year, month, 1)
    if month == 12:
        end_day = date(year + 1, 1, 1)
    else:
        end_day = date(year, month + 1, 1)
    start_utc, _ = gym_day_bounds_utc(start_day)
    end_utc, _ = gym_day_bounds_utc(end_day)
    return start_utc, end_utc


def to_device_local(value: datetime) -> datetime:
    return value.astimezone(device_zone())
