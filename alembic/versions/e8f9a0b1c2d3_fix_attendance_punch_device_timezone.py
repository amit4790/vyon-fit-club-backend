"""Correct ATTLOG punches that were stored with device-local times labeled as UTC.

Revision ID: e8f9a0b1c2d3
Revises: d4e5f6a7b8c9
Create Date: 2026-09-04
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import op

revision = "e8f9a0b1c2d3"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None

DEVICE_TZ = ZoneInfo("Asia/Kolkata")


def upgrade() -> None:
    """
    Historical ingest attached timezone.utc to ZKTeco local wall clocks.
    Reinterpret those clock values as Asia/Kolkata and store real UTC.
    """
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, punched_at FROM attendance_punches ORDER BY id ASC")
    ).mappings().all()

    update = sa.text("UPDATE attendance_punches SET punched_at = :punched_at WHERE id = :id")
    for row in rows:
        stored = row["punched_at"]
        if stored is None:
            continue
        if stored.tzinfo is None:
            as_utc = stored.replace(tzinfo=timezone.utc)
        else:
            as_utc = stored.astimezone(timezone.utc)
        naive = as_utc.replace(tzinfo=None)
        corrected = naive.replace(tzinfo=DEVICE_TZ).astimezone(timezone.utc)
        if corrected == as_utc:
            continue
        conn.execute(update, {"id": row["id"], "punched_at": corrected})


def downgrade() -> None:
    """Reverse the correction (reattach UTC label to the previous local clock)."""
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, punched_at FROM attendance_punches ORDER BY id ASC")
    ).mappings().all()

    update = sa.text("UPDATE attendance_punches SET punched_at = :punched_at WHERE id = :id")
    for row in rows:
        stored = row["punched_at"]
        if stored is None:
            continue
        local = stored.astimezone(DEVICE_TZ) if stored.tzinfo else stored.replace(tzinfo=DEVICE_TZ)
        mislabeled = local.replace(tzinfo=None).replace(tzinfo=timezone.utc)
        conn.execute(update, {"id": row["id"], "punched_at": mislabeled})
