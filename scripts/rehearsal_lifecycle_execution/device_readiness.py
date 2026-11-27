"""Read-only PUSH device readiness checks for rehearsal execution."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from core.config import settings

from services.push_device_service import PushDeviceService

from rehearsal_lifecycle_execution.errors import DeviceSyncError


def list_eligible_push_device_serials(db: Session) -> list[str]:
    push = PushDeviceService(db)
    serials = push._active_device_serials()  # noqa: SLF001 — rehearsal inspection only
    return list(serials)

logger = logging.getLogger(__name__)

ReadinessPhase = Literal["upfront", "final"]


@dataclass
class DeviceReadinessReport:
    phase: ReadinessPhase
    device_push_enabled: bool
    eligible_device_serials: list[str]
    database_only_opt_in: bool
    readiness_aborted: bool
    skip_reason: str | None = None

    @property
    def device_count(self) -> int:
        return len(self.eligible_device_serials)


def assess_device_readiness(
    db: Session,
    *,
    allow_zero_push_devices: bool,
    phase: ReadinessPhase,
) -> DeviceReadinessReport:
    """
    Read-only inspection of eligible PUSH devices.

    Aborts when device_push_enabled is false (unless database-only opt-in).
    Aborts on zero eligible devices unless allow_zero_push_devices.
    """
    enabled = bool(settings.device_push_enabled)
    serials = list_eligible_push_device_serials(db)

    if not enabled and not allow_zero_push_devices:
        raise DeviceSyncError(
            "device_push_enabled is false; enable for rehearsal or pass "
            "--allow-database-only-without-device-sync"
        )

    if not serials:
        if not allow_zero_push_devices:
            raise DeviceSyncError(
                f"Zero eligible PUSH devices at {phase} readiness; aborting. "
                "Use --allow-database-only-without-device-sync to opt in to database-only execution."
            )
        logger.warning(
            "database_only_execution_authorized",
            extra={
                "phase": phase,
                "reason": "zero_eligible_push_devices",
                "opt_in": True,
            },
        )
        return DeviceReadinessReport(
            phase=phase,
            device_push_enabled=enabled,
            eligible_device_serials=[],
            database_only_opt_in=True,
            readiness_aborted=False,
            skip_reason="no_eligible_push_devices",
        )

    logger.info(
        "device_readiness_ok",
        extra={
            "phase": phase,
            "device_push_enabled": enabled,
            "eligible_device_count": len(serials),
            "eligible_device_serials": serials,
        },
    )
    return DeviceReadinessReport(
        phase=phase,
        device_push_enabled=enabled,
        eligible_device_serials=serials,
        database_only_opt_in=False,
        readiness_aborted=False,
    )