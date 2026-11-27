"""Pre-execution backup export."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from rehearsal_lifecycle_execution.constants import (
    AFFECTED_MEMBER_IDS,
    MEMBER_DEVICE_COLUMNS,
    SUBSCRIPTION_IDS,
)
from rehearsal_lifecycle_execution.errors import BackupValidationError
from rehearsal_lifecycle_execution.serialization import canonical_json_dumps, sha256_hex

MEMBER_DEVICE_COLUMN_DEVICE_ACCESS_ENABLED = "device_access_enabled"
SCHEMA_NOTE_ABSENT = "absent_from_source_schema"


def default_export_dir() -> Path:
    override = os.environ.get("PHASE_138_EXPORT_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".vyon" / "rehearsal-phase-1-3-8-exports").resolve()


def _in_clause_ints(values: tuple[int, ...] | list[int]) -> str:
    return ",".join(str(int(v)) for v in values)


def _fetch_all(conn, query: str) -> list[dict[str, Any]]:
    rows = conn.execute(text(query)).mappings().all()
    return [dict(r) for r in rows]


def _members_table_column_names(conn) -> set[str]:
    """Introspect live ``members`` columns (supports pre-M8 backups without device_access_enabled)."""
    rows = conn.execute(
        text(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'members'
            """
        )
    ).scalars().all()
    return {str(name) for name in rows}


def resolve_member_device_backup_columns(
    member_columns: set[str],
) -> tuple[tuple[str, ...], dict[str, str]]:
    """
    Choose SELECT columns and record schema notes for fields omitted from the source table.

    ``device_access_enabled`` is included only after migration M8; when missing, a schema note
    is emitted instead of fabricating NULL values in row data.
    """
    selected: list[str] = []
    schema_notes: dict[str, str] = {}
    for col in MEMBER_DEVICE_COLUMNS:
        if col in member_columns:
            selected.append(col)
            continue
        if col == MEMBER_DEVICE_COLUMN_DEVICE_ACCESS_ENABLED:
            schema_notes[col] = SCHEMA_NOTE_ABSENT
            continue
        raise BackupValidationError(f"Required members column {col!r} not present in source schema")
    if not selected:
        raise BackupValidationError("No member device columns available for backup")
    return tuple(selected), schema_notes


def collect_backup_payload(
    engine: Engine,
    alembic_version: str,
    *,
    rehearsal_hostname: str,
) -> dict[str, Any]:
    sub_in = _in_clause_ints(SUBSCRIPTION_IDS)
    member_in = _in_clause_ints(AFFECTED_MEMBER_IDS)
    pin_filters = " OR ".join(f"command LIKE '%PIN={mid}%'" for mid in AFFECTED_MEMBER_IDS)

    with engine.connect() as conn:
        member_col_names = _members_table_column_names(conn)
        member_select_cols, member_schema_notes = resolve_member_device_backup_columns(member_col_names)
        member_cols_sql = ", ".join(member_select_cols)

        subscriptions = _fetch_all(conn, f"SELECT * FROM membership_subscriptions WHERE id IN ({sub_in})")
        invoices = _fetch_all(
            conn, f"SELECT * FROM invoices WHERE subscription_id IN ({sub_in}) ORDER BY id"
        )
        members = _fetch_all(
            conn, f"SELECT {member_cols_sql} FROM members WHERE id IN ({member_in}) ORDER BY id"
        )
        device_commands = _fetch_all(
            conn,
            f"""
            SELECT id, command_id, device_serial, command, status, created_at, executed_at, completed_at
            FROM device_commands
            WHERE {pin_filters}
            ORDER BY id
            """,
        )
        push_devices = _fetch_all(
            conn,
            "SELECT serial_number, is_active FROM push_devices WHERE is_active = true ORDER BY serial_number",
        )

    payload = {
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "rehearsal_hostname": rehearsal_hostname,
        "alembic_version": alembic_version,
        "subscription_ids": list(SUBSCRIPTION_IDS),
        "affected_member_ids": list(AFFECTED_MEMBER_IDS),
        "subscriptions": subscriptions,
        "invoices": invoices,
        "member_device_state": members,
        "member_device_state_schema_notes": member_schema_notes,
        "device_commands": device_commands,
        "push_devices_active": push_devices,
    }
    validate_backup_payload(payload)
    return payload


def validate_backup_payload(payload: dict[str, Any]) -> None:
    subs = payload.get("subscriptions") or []
    if len(subs) != len(SUBSCRIPTION_IDS):
        raise BackupValidationError(
            f"Expected {len(SUBSCRIPTION_IDS)} subscriptions, got {len(subs)}"
        )
    sub_ids = {int(s["id"]) for s in subs}
    if sub_ids != set(SUBSCRIPTION_IDS):
        raise BackupValidationError(f"Subscription id set mismatch: {sub_ids}")

    invoices = payload.get("invoices") or []
    if not invoices:
        raise BackupValidationError("Expected at least one invoice row in backup")

    members = payload.get("member_device_state") or []
    if len(members) != len(AFFECTED_MEMBER_IDS):
        raise BackupValidationError(
            f"Expected {len(AFFECTED_MEMBER_IDS)} member device rows, got {len(members)}"
        )

    for key in ("exported_at_utc", "rehearsal_hostname", "alembic_version"):
        if not payload.get(key):
            raise BackupValidationError(f"Backup missing required field {key!r}")

    if payload.get("device_commands") is None:
        raise BackupValidationError("device_commands key missing from backup")

    notes = payload.get("member_device_state_schema_notes")
    if notes is not None and not isinstance(notes, dict):
        raise BackupValidationError("member_device_state_schema_notes must be a mapping")


def verify_backup_checksum(json_path: Path, checksum_path: Path) -> str:
    body = json_path.read_text(encoding="utf-8")
    expected = sha256_hex(body)
    checksum_line = checksum_path.read_text(encoding="utf-8").strip()
    if not checksum_line.startswith(expected):
        raise BackupValidationError("Checksum file does not match backup JSON")
    payload = json.loads(body)
    validate_backup_payload(payload)
    return expected


def write_backup_bundle(
    engine: Engine,
    alembic_version: str,
    *,
    rehearsal_hostname: str,
    export_dir: Path | None = None,
) -> dict[str, Any]:
    export_dir = export_dir or default_export_dir()
    export_dir.mkdir(parents=True, exist_ok=True)

    payload = collect_backup_payload(engine, alembic_version, rehearsal_hostname=rehearsal_hostname)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = export_dir / f"phase_1_3_8_backup_{stamp}.json"
    body = canonical_json_dumps(payload)
    digest = sha256_hex(body)
    json_path.write_text(body, encoding="utf-8")
    checksum_path = export_dir / f"phase_1_3_8_backup_{stamp}.sha256"
    checksum_path.write_text(f"{digest}  {json_path.name}\n", encoding="utf-8")
    verify_backup_checksum(json_path, checksum_path)

    return {
        "json_path": str(json_path),
        "checksum_path": str(checksum_path),
        "sha256": digest,
        "export_dir": str(export_dir),
        "subscription_count": len(payload["subscriptions"]),
        "invoice_count": len(payload["invoices"]),
        "device_command_count": len(payload["device_commands"]),
    }


def create_engine_for_url(database_url: str) -> Engine:
    return create_engine(database_url)