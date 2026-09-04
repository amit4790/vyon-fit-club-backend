"""Rebuild attendance punched_at from device raw_line (IST wall clock).

Revision ID: f1a2b3c4d5e6
Revises: e8f9a0b1c2d3
Create Date: 2026-09-04

Why:
- Original ingest labeled device-local times as UTC (times looked ~5h30m ahead).
- A later migration reinterpreted all rows as Kolkata, which also shifted rows that
  were already corrected or newly ingested — producing midnight / mixed times.
- raw_line still has the original device wall clock; rebuild from that once.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None

DEVICE_TZ = ZoneInfo("Asia/Kolkata")
_ATTLOG_LINE_RE = re.compile(
    r"^(?:ATTLOG[:\s]*)?(\d+)\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})"
)


def _parse_device_wall_clock(value: str) -> datetime:
    naive = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return naive.replace(tzinfo=DEVICE_TZ).astimezone(timezone.utc)


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, device_serial, pin, punched_at, raw_line "
            "FROM attendance_punches "
            "WHERE raw_line IS NOT NULL AND btrim(raw_line) <> '' "
            "ORDER BY id ASC"
        )
    ).mappings().all()

    conflict_check = sa.text(
        """
        SELECT id FROM attendance_punches
        WHERE device_serial = :device_serial
          AND pin = :pin
          AND punched_at = :punched_at
          AND id <> :id
        LIMIT 1
        """
    )
    update = sa.text("UPDATE attendance_punches SET punched_at = :punched_at WHERE id = :id")

    for row in rows:
        match = _ATTLOG_LINE_RE.match((row["raw_line"] or "").strip())
        if not match:
            continue
        corrected = _parse_device_wall_clock(match.group(2))
        stored = row["punched_at"]
        if stored is not None:
            if stored.tzinfo is None:
                as_utc = stored.replace(tzinfo=timezone.utc)
            else:
                as_utc = stored.astimezone(timezone.utc)
            if as_utc == corrected:
                continue

        conflict = conn.execute(
            conflict_check,
            {
                "device_serial": row["device_serial"],
                "pin": row["pin"],
                "punched_at": corrected,
                "id": row["id"],
            },
        ).scalar_one_or_none()
        if conflict is not None:
            continue

        conn.execute(update, {"id": row["id"], "punched_at": corrected})


def downgrade() -> None:
    # Irreversible data repair from raw_line; no-op.
    pass
