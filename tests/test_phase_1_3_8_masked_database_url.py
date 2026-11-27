"""Regression: never reconnect using SQLAlchemy str(engine.url) (password masked as ***)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine

from rehearsal_lifecycle_execution.constants import (
    REHEARSAL_DB_HOST,
    REVIEWED_SUBSCRIPTION_SNAPSHOT,
    REVISION_L7,
)
from rehearsal_lifecycle_execution.errors import DatabaseSafetyError
from rehearsal_lifecycle_execution.migrations import (
    read_alembic_version,
    read_alembic_version_from_engine,
    reject_sqlalchemy_masked_url,
)
from rehearsal_lifecycle_execution.plan import build_dry_run_plan


def _snapshot_row_dicts() -> dict[int, dict]:
    return {
        sid: {
            "id": snap.id,
            "member_id": snap.member_id,
            "status": snap.status,
            "payment_status": snap.payment_status,
            "start_date": snap.start_date,
            "end_date": snap.end_date,
        }
        for sid, snap in REVIEWED_SUBSCRIPTION_SNAPSHOT.items()
    }


def test_sqlalchemy_str_engine_url_masks_password():
    url = f"postgresql+psycopg://neondb_owner:actual_secret@{REHEARSAL_DB_HOST}/neondb"
    engine = create_engine(url)
    rendered = str(engine.url)
    assert "***" in rendered
    assert "actual_secret" not in rendered


def test_reject_sqlalchemy_masked_url():
    masked = f"postgresql+psycopg://neondb_owner:***@{REHEARSAL_DB_HOST}/neondb"
    with pytest.raises(DatabaseSafetyError, match="masked"):
        reject_sqlalchemy_masked_url(masked)


def test_read_alembic_version_rejects_masked_url_without_new_engine():
    masked = f"postgresql+psycopg://user:***@{REHEARSAL_DB_HOST}/neondb"
    with patch("rehearsal_lifecycle_execution.migrations.create_engine") as mock_create:
        with pytest.raises(DatabaseSafetyError, match="masked"):
            read_alembic_version(masked)
        mock_create.assert_not_called()


def test_read_alembic_version_from_engine_does_not_create_engine():
    mock_conn = MagicMock()
    mock_conn.execute.return_value.scalar_one_or_none.return_value = REVISION_L7
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    mock_engine.connect.return_value.__exit__.return_value = False

    with patch("rehearsal_lifecycle_execution.migrations.create_engine") as mock_create:
        version = read_alembic_version_from_engine(mock_engine)
        assert version == REVISION_L7
        mock_create.assert_not_called()
    mock_engine.connect.assert_called_once()


@patch("rehearsal_lifecycle_execution.plan._load_subscription_rows")
@patch("rehearsal_lifecycle_execution.migrations.create_engine")
def test_build_dry_run_plan_reads_alembic_via_engine_not_str_url(
    mock_create,
    mock_load,
):
    mock_load.return_value = _snapshot_row_dicts()
    engine = create_engine(f"postgresql+psycopg://u:secret@{REHEARSAL_DB_HOST}/neondb")

    with patch(
        "rehearsal_lifecycle_execution.plan.read_alembic_version_from_engine",
        return_value=REVISION_L7,
    ) as read_from_engine:
        plan = build_dry_run_plan(engine, execution_date=date(2026, 11, 27))

    read_from_engine.assert_called_once_with(engine)
    mock_create.assert_not_called()
    assert plan.alembic_current == REVISION_L7