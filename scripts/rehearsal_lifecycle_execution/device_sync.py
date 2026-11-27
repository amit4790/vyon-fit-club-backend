"""Post-reconciliation device access synchronisation."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from core.device_pins import DEVICE_PRIVILEGE_INACTIVE, DEVICE_PRIVILEGE_NORMAL
from repositories.subscription_repository import SubscriptionRepository
from services.push_device_service import PushDeviceService, UserSyncCommand

from rehearsal_lifecycle_execution.constants import AFFECTED_MEMBER_IDS
from rehearsal_lifecycle_execution.device_command_dedup import (
    AccessSlotAction,
    DeviceCommandConflict,
    load_userinfo_commands_for_devices,
    parse_userinfo_access,
    pending_command_ids_for_device_serials,
    resolve_access_slot,
    summarize_acknowledged_commands,
)
from rehearsal_lifecycle_execution.device_inspect import assert_access_sync_commands
from rehearsal_lifecycle_execution.device_readiness import assess_device_readiness, list_eligible_push_device_serials
from rehearsal_lifecycle_execution.errors import DeviceSyncError

__all__ = [
    "DeviceSyncReport",
    "list_eligible_push_device_serials",
    "run_device_access_sync",
    "run_device_access_sync_idempotent",
]

logger = logging.getLogger(__name__)


@dataclass
class DeviceSyncReport:
    member_ids: tuple[int, ...]
    eligible_device_serials: list[str]
    enabled_count: int
    disabled_count: int
    command_strings: list[str]
    privilege_values: list[int]
    pending_ids_before: list[int] = field(default_factory=list)
    pending_ids_after: list[int] = field(default_factory=list)
    commands_newly_queued: int = 0
    commands_satisfied_in_flight: int = 0
    commands_satisfied_completed_ack: int = 0
    conflicting_commands: list[dict[str, Any]] = field(default_factory=list)
    failed_ack_userinfo_count: int = 0
    completed_ack_userinfo_count: int = 0
    device_physically_verified: bool = False
    sync_queue_complete: bool = True
    device_sync_skipped: bool = False
    skip_reason: str | None = None

    # Back-compat alias
    @property
    def commands_satisfied_by_existing(self) -> int:
        return self.commands_satisfied_in_flight + self.commands_satisfied_completed_ack


def _assert_pending_preserved(before: list[int], after: list[int]) -> None:
    missing = sorted(set(before) - set(after))
    if missing:
        raise DeviceSyncError(
            f"Pending device commands were lost during sync (ids missing: {missing})"
        )


def _required_privilege(enabled: bool) -> int:
    return DEVICE_PRIVILEGE_NORMAL if enabled else DEVICE_PRIVILEGE_INACTIVE


def _conflict_from_decision(
    *,
    device_serial: str,
    member_id: int,
    required_privilege: int,
    decision,
) -> DeviceCommandConflict:
    kind = "executing_other_pri" if decision.action == AccessSlotAction.CONFLICT_EXECUTING_OTHER_PRI else "pending_other_pri"
    return DeviceCommandConflict(
        device_serial=device_serial,
        member_id=member_id,
        required_privilege=required_privilege,
        existing_command_id=int(decision.existing_command_id or 0),
        existing_privilege=int(
            decision.existing_privilege if decision.existing_privilege is not None else -1
        ),
        existing_status=str(decision.existing_status or ""),
        conflict_kind=kind,
    )


def _queue_member_access_idempotent(
    db: Session,
    *,
    member_id: int,
    member_name: str,
    enabled: bool,
    eligible_serials: list[str],
    userinfo_rows: list[dict[str, Any]],
    conflicts: list[DeviceCommandConflict],
) -> list[str]:
    push = PushDeviceService(db)
    privilege = _required_privilege(enabled)
    queued_strings: list[str] = []
    serials_to_commit: list[str] = []

    for index, serial in enumerate(eligible_serials):
        decision = resolve_access_slot(
            userinfo_rows,
            device_serial=serial,
            member_id=member_id,
            required_privilege=privilege,
        )
        if decision.action in (
            AccessSlotAction.SKIP_EQUIVALENT_IN_FLIGHT,
            AccessSlotAction.SKIP_SATISFIED_COMPLETED,
        ):
            continue
        if decision.action in (
            AccessSlotAction.CONFLICT_PENDING_OTHER_PRI,
            AccessSlotAction.CONFLICT_EXECUTING_OTHER_PRI,
        ):
            conflicts.append(
                _conflict_from_decision(
                    device_serial=serial,
                    member_id=member_id,
                    required_privilege=privilege,
                    decision=decision,
                )
            )
            continue
        command_id = push._next_command_id(member_id=member_id, salt=index + 900)  # noqa: SLF001
        command_str = UserSyncCommand.build_update_userinfo_command(
            command_id=command_id,
            pin=str(member_id),
            name=member_name,
            privilege=privilege,
            password="",
        )
        push.queue_command(
            device_serial=serial,
            command_id=str(command_id),
            command=command_str,
            max_retries=3,
            commit=False,
        )
        queued_strings.append(command_str)
        serials_to_commit.append(serial)

    if queued_strings:
        from models import Member

        member = db.query(Member).filter(Member.id == member_id).first()
        if member:
            push._mark_member_sync_pending(member)  # noqa: SLF001
        push._commit_and_mark(serials_to_commit)  # noqa: SLF001

    return queued_strings


def run_device_access_sync(
    db: Session,
    *,
    member_ids: tuple[int, ...] | None = None,
    allow_zero_push_devices: bool = False,
    reconciliation_already_done: bool = True,
) -> DeviceSyncReport:
    """
    Queue USERINFO Pri=0/1 updates after reconciliation commits (idempotent on retry).
    Does not verify physical device state (device_physically_verified=False always).
    """
    member_ids = member_ids or AFFECTED_MEMBER_IDS
    readiness = assess_device_readiness(
        db,
        allow_zero_push_devices=allow_zero_push_devices,
        phase="final",
    )
    eligible = readiness.eligible_device_serials
    pending_before = pending_command_ids_for_device_serials(db, eligible)

    if readiness.skip_reason == "no_eligible_push_devices":
        pending_after = pending_command_ids_for_device_serials(db, eligible)
        _assert_pending_preserved(pending_before, pending_after)
        return DeviceSyncReport(
            member_ids=member_ids,
            eligible_device_serials=[],
            enabled_count=0,
            disabled_count=0,
            command_strings=[],
            privilege_values=[],
            pending_ids_before=pending_before,
            pending_ids_after=pending_after,
            device_sync_skipped=True,
            skip_reason="no_eligible_push_devices",
        )

    userinfo_rows = load_userinfo_commands_for_devices(
        db,
        device_serials=eligible,
        member_ids=member_ids,
    )
    ack_summary = summarize_acknowledged_commands(userinfo_rows)

    command_strings: list[str] = []
    conflicts: list[DeviceCommandConflict] = []
    repo = SubscriptionRepository(db)
    today = date.today()
    enabled_total = 0
    disabled_total = 0
    satisfied_in_flight = 0
    satisfied_completed = 0
    newly_queued = 0

    for member_id in member_ids:
        member = repo.get_member_by_id(member_id)
        if not member:
            raise DeviceSyncError(f"Member {member_id} not found for device sync")
        enabled = repo.member_has_active_membership(member_id, today)
        privilege = _required_privilege(enabled)

        slots_to_queue = 0
        for serial in eligible:
            decision = resolve_access_slot(
                userinfo_rows,
                device_serial=serial,
                member_id=member_id,
                required_privilege=privilege,
            )
            if decision.action == AccessSlotAction.SKIP_EQUIVALENT_IN_FLIGHT:
                satisfied_in_flight += 1
            elif decision.action == AccessSlotAction.SKIP_SATISFIED_COMPLETED:
                satisfied_completed += 1
            elif decision.action in (
                AccessSlotAction.CONFLICT_PENDING_OTHER_PRI,
                AccessSlotAction.CONFLICT_EXECUTING_OTHER_PRI,
            ):
                pass
            else:
                slots_to_queue += 1

        new_cmds = _queue_member_access_idempotent(
            db,
            member_id=member_id,
            member_name=member.full_name,
            enabled=enabled,
            eligible_serials=eligible,
            userinfo_rows=userinfo_rows,
            conflicts=conflicts,
        )
        for cmd in new_cmds:
            command_strings.append(cmd)
        newly_queued += len(new_cmds)

        userinfo_rows = load_userinfo_commands_for_devices(
            db,
            device_serials=eligible,
            member_ids=member_ids,
        )

        if enabled:
            enabled_total += 1
        else:
            disabled_total += 1

    conflict_dicts = [
        {
            "device_serial": c.device_serial,
            "member_id": c.member_id,
            "required_pri": c.required_privilege,
            "existing_command_id": c.existing_command_id,
            "existing_pri": c.existing_privilege,
            "existing_status": c.existing_status,
            "kind": c.conflict_kind,
        }
        for c in conflicts
    ]

    if conflicts:
        executing = [c for c in conflicts if c.conflict_kind == "executing_other_pri"]
        msg_parts = [
            f"{len(conflicts)} USERINFO access conflict(s) on device queue",
        ]
        if executing:
            msg_parts.append(
                f"{len(executing)} executing with conflicting Pri "
                "(older command may still be applied; required state not assured)"
            )
        raise DeviceSyncError(f"{'; '.join(msg_parts)}: {conflict_dicts}")

    required_slots = len(eligible) * len(member_ids)
    covered = satisfied_in_flight + satisfied_completed + newly_queued
    if covered < required_slots:
        raise DeviceSyncError(
            f"Access sync incomplete: covered {covered}/{required_slots} member-device slots "
            "(queue representation only; device not polled)"
        )

    if command_strings:
        privileges = assert_access_sync_commands(command_strings)
        for cmd in command_strings:
            if re.search(r"DATA\s+DELETE", cmd, re.I):
                raise DeviceSyncError("Forbidden DELETE command queued during access sync")
    else:
        privileges = []

    pending_after = pending_command_ids_for_device_serials(db, eligible)
    _assert_pending_preserved(pending_before, pending_after)

    logger.info(
        "device_access_sync_complete",
        extra={
            "member_ids": list(member_ids),
            "eligible_devices": eligible,
            "commands_newly_queued": newly_queued,
            "commands_satisfied_in_flight": satisfied_in_flight,
            "commands_satisfied_completed_ack": satisfied_completed,
            "failed_ack_userinfo_rows": ack_summary["failed_userinfo_rows"],
            "device_physically_verified": False,
            "reconciliation_already_done": reconciliation_already_done,
        },
    )
    return DeviceSyncReport(
        member_ids=member_ids,
        eligible_device_serials=eligible,
        enabled_count=enabled_total,
        disabled_count=disabled_total,
        command_strings=command_strings,
        privilege_values=privileges,
        pending_ids_before=pending_before,
        pending_ids_after=pending_after,
        commands_newly_queued=newly_queued,
        commands_satisfied_in_flight=satisfied_in_flight,
        commands_satisfied_completed_ack=satisfied_completed,
        conflicting_commands=[],
        failed_ack_userinfo_count=ack_summary["failed_userinfo_rows"],
        completed_ack_userinfo_count=ack_summary["completed_userinfo_rows"],
        device_physically_verified=False,
        sync_queue_complete=True,
        device_sync_skipped=False,
    )


def run_device_access_sync_idempotent(
    db: Session,
    *,
    member_ids: tuple[int, ...] | None = None,
    allow_zero_push_devices: bool = False,
) -> DeviceSyncReport:
    """Retry-safe device sync without repeating reconciliation."""
    return run_device_access_sync(
        db,
        member_ids=member_ids,
        allow_zero_push_devices=allow_zero_push_devices,
        reconciliation_already_done=True,
    )