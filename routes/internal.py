"""Internal cron endpoints (Render Cron Job / scheduled callers)."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from core.config import settings
from database import get_db
from schemas.attendance import AttendancePurgeResponse
from schemas.subscription import ExpiredMembershipCronResponse
from services.attendance_service import AttendanceService
from services.subscription_service import SubscriptionService

router = APIRouter(prefix="/api/internal/cron", tags=["internal-cron"])


def _require_cron_secret(x_cron_secret: str | None) -> None:
    expected = (settings.cron_secret or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cron secret is not configured",
        )
    provided = (x_cron_secret or "").strip()
    if len(provided) != len(expected) or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid cron secret",
        )


@router.post("/purge-attendance", response_model=AttendancePurgeResponse)
def cron_purge_attendance(
    db: Session = Depends(get_db),
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
) -> AttendancePurgeResponse:
    """
    Purge punches outside the calendar retention window and trim raw device logs.

    Intended schedule: once per month (e.g. 1st of month), not daily.
    Auth: header ``X-Cron-Secret`` must match ``CRON_SECRET``.
    """
    _require_cron_secret(x_cron_secret)
    result = AttendanceService(db).purge_old_records()
    return AttendancePurgeResponse(
        message="Old attendance data purged",
        punches_deleted=result["punches_deleted"],
        raw_logs_deleted=result["raw_logs_deleted"],
        retention_days=result["retention_days"],
        punch_retention_days=result["punch_retention_days"],
        punch_retention_months=result["punch_retention_months"],
        raw_log_retention_days=result["raw_log_retention_days"],
    )


@router.post("/sync-expired-memberships", response_model=ExpiredMembershipCronResponse)
def cron_sync_expired_memberships(
    db: Session = Depends(get_db),
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
) -> ExpiredMembershipCronResponse:
    """
    Mark subscriptions past end_date as expired and queue ZKTeco access updates for
    members who expired tonight or lack a valid plan and are not yet marked inactive
    on device (``members.device_access_enabled``).

    Intended schedule: once daily (e.g. 00:30 IST / 19:00 UTC previous day).
    Auth: header ``X-Cron-Secret`` must match ``CRON_SECRET``.
    """
    _require_cron_secret(x_cron_secret)
    result = SubscriptionService(db).run_nightly_expired_membership_sync()
    return ExpiredMembershipCronResponse(
        message="Expired membership device sync completed",
        run_date=str(result["run_date"]),
        subscriptions_marked_expired=int(result["subscriptions_marked_expired"]),
        members_device_synced=int(result["members_device_synced"]),
        members_disabled_on_device=int(result["members_disabled_on_device"]),
        members_still_enabled_on_device=int(result["members_still_enabled_on_device"]),
    )
