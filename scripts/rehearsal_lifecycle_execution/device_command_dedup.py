"""Detect equivalent/conflicting USERINFO access commands (rehearsal sync idempotency)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

_USERINFO_UPDATE = re.compile(r"DATA\s+UPDATE\s+USERINFO\b", re.I)
_PIN_PATTERN = re.compile(r"\bPIN=(\d+)\b", re.I)
_PRI_PATTERN = re.compile(r"\bPri=(\d+)\b", re.I)
_PENDING_STATUSES = frozenset({"pending", "executing"})
_TERMINAL_STATUSES = frozenset({"completed", "failed"})


def _status_value(raw: object) -> str:
    value = getattr(raw, "value", raw)
    return str(value).lower()


def _status_is_pending_or_executing(raw: object) -> bool:
    return _status_value(raw) in _PENDING_STATUSES


class AccessSlotAction(str, Enum):
    QUEUE_NEW = "queue_new"
    SKIP_EQUIVALENT_IN_FLIGHT = "skip_equivalent_in_flight"
    SKIP_SATISFIED_COMPLETED = "skip_satisfied_completed"
    CONFLICT_PENDING_OTHER_PRI = "conflict_pending_other_pri"
    CONFLICT_EXECUTING_OTHER_PRI = "conflict_executing_other_pri"


@dataclass(frozen=True)
class AccessSlotDecision:
    action: AccessSlotAction
    existing_command_id: int | None = None
    existing_privilege: int | None = None
    existing_status: str | None = None


@dataclass
class DeviceCommandConflict:
    device_serial: str
    member_id: int
    required_privilege: int
    existing_command_id: int
    existing_privilege: int
    existing_status: str
    conflict_kind: Literal["pending_other_pri", "executing_other_pri"]


def parse_userinfo_access(command: str) -> tuple[int, int] | None:
    """Return (member_pin, privilege) for DATA UPDATE USERINFO rows, else None."""
    if not command or not _USERINFO_UPDATE.search(command):
        return None
    pin_match = _PIN_PATTERN.search(command)
    pri_match = _PRI_PATTERN.search(command)
    if not pin_match or not pri_match:
        return None
    return int(pin_match.group(1)), int(pri_match.group(1))


def load_userinfo_commands_for_devices(
    db: Session,
    *,
    device_serials: tuple[str, ...] | list[str],
    member_ids: tuple[int, ...] | list[int],
) -> list[dict[str, Any]]:
    """Load USERINFO rows for devices; filter by exact integer PIN in Python."""
    from sqlalchemy import inspect

    member_set = {int(m) for m in member_ids}
    bind = db.get_bind()
    if bind is not None:
        inspector = inspect(bind)
        if not inspector.has_table("device_commands"):
            return []
    if not device_serials:
        return []

    serials_sql = ",".join(f"'{s}'" for s in device_serials)
    query = f"""
        SELECT id, device_serial, command, status
        FROM device_commands
        WHERE device_serial IN ({serials_sql})
          AND command LIKE '%DATA UPDATE USERINFO%'
        ORDER BY id
    """
    rows = db.execute(text(query)).mappings().all()
    out: list[dict[str, Any]] = []
    for row in rows:
        parsed = parse_userinfo_access(str(row["command"]))
        if parsed is None:
            continue
        pin, pri = parsed
        if pin not in member_set:
            continue
        status = _status_value(row["status"])
        out.append(
            {
                "id": int(row["id"]),
                "device_serial": str(row["device_serial"]),
                "member_id": pin,
                "privilege": pri,
                "status": status,
                "command": str(row["command"]),
            }
        )
    return out


def load_pending_userinfo_access(
    db: Session,
    *,
    device_serials: tuple[str, ...] | list[str],
    member_ids: tuple[int, ...] | list[int],
) -> list[dict[str, Any]]:
    rows = load_userinfo_commands_for_devices(db, device_serials=device_serials, member_ids=member_ids)
    return [r for r in rows if r["status"] in _PENDING_STATUSES]


def resolve_access_slot(
    rows: list[dict[str, Any]],
    *,
    device_serial: str,
    member_id: int,
    required_privilege: int,
) -> AccessSlotDecision:
    """
    Decide whether to queue, skip, or treat as conflict for one device/member slot.
    """
    relevant = [
        r
        for r in rows
        if r["device_serial"] == device_serial and int(r["member_id"]) == int(member_id)
    ]
    if not relevant:
        return AccessSlotDecision(action=AccessSlotAction.QUEUE_NEW)

    in_flight = [r for r in relevant if r["status"] in _PENDING_STATUSES]
    for row in in_flight:
        if int(row["privilege"]) == int(required_privilege):
            return AccessSlotDecision(
                action=AccessSlotAction.SKIP_EQUIVALENT_IN_FLIGHT,
                existing_command_id=row["id"],
                existing_privilege=int(row["privilege"]),
                existing_status=row["status"],
            )

    for row in in_flight:
        if int(row["privilege"]) != int(required_privilege):
            kind = (
                AccessSlotAction.CONFLICT_EXECUTING_OTHER_PRI
                if row["status"] == "executing"
                else AccessSlotAction.CONFLICT_PENDING_OTHER_PRI
            )
            return AccessSlotDecision(
                action=kind,
                existing_command_id=row["id"],
                existing_privilege=int(row["privilege"]),
                existing_status=row["status"],
            )

    completed = [
        r for r in relevant if r["status"] == "completed" and int(r["privilege"]) == int(required_privilege)
    ]
    if completed:
        latest = completed[-1]
        return AccessSlotDecision(
            action=AccessSlotAction.SKIP_SATISFIED_COMPLETED,
            existing_command_id=latest["id"],
            existing_privilege=int(latest["privilege"]),
            existing_status=latest["status"],
        )

    return AccessSlotDecision(action=AccessSlotAction.QUEUE_NEW)


def has_equivalent_pending_access(
    pending_rows: list[dict[str, Any]],
    *,
    device_serial: str,
    member_id: int,
    required_privilege: int,
) -> bool:
    decision = resolve_access_slot(
        pending_rows,
        device_serial=device_serial,
        member_id=member_id,
        required_privilege=required_privilege,
    )
    return decision.action == AccessSlotAction.SKIP_EQUIVALENT_IN_FLIGHT


def pending_command_ids_for_device_serials(
    db: Session,
    device_serials: tuple[str, ...] | list[str],
) -> list[int]:
    """Snapshot pending/executing command ids on eligible devices (preserves unrelated rows)."""
    from sqlalchemy import inspect

    bind = db.get_bind()
    if bind is not None:
        inspector = inspect(bind)
        if not inspector.has_table("device_commands"):
            return []
    if not device_serials:
        return []
    serials_sql = ",".join(f"'{s}'" for s in device_serials)
    rows = db.execute(
        text(
            f"""
            SELECT id, status FROM device_commands
            WHERE device_serial IN ({serials_sql})
            ORDER BY id
            """
        )
    ).mappings().all()
    ids: list[int] = []
    for r in rows:
        if _status_is_pending_or_executing(r["status"]):
            ids.append(int(r["id"]))
    return ids


def summarize_acknowledged_commands(
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    completed = sum(1 for r in rows if r["status"] == "completed")
    failed = sum(1 for r in rows if r["status"] == "failed")
    return {"completed_userinfo_rows": completed, "failed_userinfo_rows": failed}