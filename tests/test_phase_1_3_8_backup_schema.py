"""Backup member column introspection (L7 without device_access_enabled, M8+ with)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from rehearsal_lifecycle_execution.backup import (
    SCHEMA_NOTE_ABSENT,
    collect_backup_payload,
    resolve_member_device_backup_columns,
)
from rehearsal_lifecycle_execution.constants import (
    AFFECTED_MEMBER_IDS,
    MEMBER_DEVICE_COLUMNS,
    REHEARSAL_DB_HOST,
    SUBSCRIPTION_IDS,
)
from rehearsal_lifecycle_execution.errors import BackupValidationError


def _l7_member_columns() -> set[str]:
    return {c for c in MEMBER_DEVICE_COLUMNS if c != "device_access_enabled"}


def _m8_member_columns() -> set[str]:
    return set(MEMBER_DEVICE_COLUMNS)


def test_resolve_member_columns_l7_notes_device_access_absent():
    selected, notes = resolve_member_device_backup_columns(_l7_member_columns())
    assert "device_access_enabled" not in selected
    assert notes == {"device_access_enabled": SCHEMA_NOTE_ABSENT}


def test_resolve_member_columns_m8_includes_device_access_enabled():
    selected, notes = resolve_member_device_backup_columns(_m8_member_columns())
    assert "device_access_enabled" in selected
    assert notes == {}


def test_resolve_member_columns_required_missing_raises():
    cols = _l7_member_columns() - {"device_sync_status"}
    with pytest.raises(BackupValidationError, match="device_sync_status"):
        resolve_member_device_backup_columns(cols)


def _mock_collect_side_effect(conn, *, member_columns: set[str], member_rows: list[dict]):
    def execute(statement, *args, **kwargs):
        sql = str(statement)
        mock_result = MagicMock()
        if "information_schema.columns" in sql and "members" in sql:
            mock_result.scalars.return_value.all.return_value = list(member_columns)
        elif "FROM membership_subscriptions" in sql:
            mock_result.mappings.return_value.all.return_value = [
                {"id": sid, "member_id": 1} for sid in SUBSCRIPTION_IDS
            ]
        elif "FROM members WHERE" in sql:
            mock_result.mappings.return_value.all.return_value = member_rows
        elif "FROM invoices" in sql:
            mock_result.mappings.return_value.all.return_value = [{"id": 1, "subscription_id": 92}]
        elif "FROM device_commands" in sql:
            mock_result.mappings.return_value.all.return_value = []
        elif "FROM push_devices" in sql:
            mock_result.mappings.return_value.all.return_value = []
        else:
            mock_result.mappings.return_value.all.return_value = []
        return mock_result

    conn.execute.side_effect = execute


def test_collect_backup_payload_l7_omits_device_access_enabled_column():
    engine = MagicMock()
    conn = MagicMock()
    engine.connect.return_value.__enter__.return_value = conn

    l7_cols = _l7_member_columns()
    member_rows = [
        {col: f"v_{mid}_{col}" if col != "id" else mid for col in l7_cols}
        for mid in AFFECTED_MEMBER_IDS
    ]
    _mock_collect_side_effect(conn, member_columns=l7_cols, member_rows=member_rows)

    payload = collect_backup_payload(engine, "l7m8n9o0p1q2", rehearsal_hostname=REHEARSAL_DB_HOST)

    assert payload["member_device_state_schema_notes"] == {
        "device_access_enabled": SCHEMA_NOTE_ABSENT,
    }
    assert all("device_access_enabled" not in row for row in payload["member_device_state"])
    assert len(payload["member_device_state"]) == len(AFFECTED_MEMBER_IDS)


def test_collect_backup_payload_m8_includes_device_access_enabled():
    engine = MagicMock()
    conn = MagicMock()
    engine.connect.return_value.__enter__.return_value = conn

    m8_cols = _m8_member_columns()
    member_rows = [
        {col: (True if col == "device_access_enabled" else (mid if col == "id" else None)) for col in m8_cols}
        for mid in AFFECTED_MEMBER_IDS
    ]
    _mock_collect_side_effect(conn, member_columns=m8_cols, member_rows=member_rows)

    payload = collect_backup_payload(engine, "m8n9o0p1q2r3", rehearsal_hostname=REHEARSAL_DB_HOST)

    assert payload["member_device_state_schema_notes"] == {}
    assert all("device_access_enabled" in row for row in payload["member_device_state"])
    assert payload["member_device_state"][0]["device_access_enabled"] is True