"""Alembic revision checks and upgrade orchestration (no auto-downgrade)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from rehearsal_lifecycle_execution.constants import (
    REVISION_L7,
    REVISION_M8,
    REVISION_N9A,
    REVISION_N9B,
)
from rehearsal_lifecycle_execution.errors import DatabaseSafetyError, MigrationStateError
from rehearsal_lifecycle_execution.safety import build_alembic_subprocess_env, database_hostname


BACKEND_DIR = Path(__file__).resolve().parents[2]

MIGRATION_SEQUENCE: tuple[tuple[str, str], ...] = (
    (REVISION_L7, REVISION_M8),
    (REVISION_M8, REVISION_N9A),
    (REVISION_N9A, REVISION_N9B),
)


def reject_sqlalchemy_masked_url(database_url: str) -> None:
    """``str(engine.url)`` masks passwords as ``***``; never open a new engine from that."""
    if "***" in database_url:
        raise DatabaseSafetyError(
            "Database URL appears SQLAlchemy-masked; use validated DATABASE_URL "
            "or read_alembic_version_from_engine(engine)"
        )


def _read_alembic_version_from_connection(conn: Connection) -> str:
    version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    if not version:
        raise MigrationStateError("alembic_version is empty")
    return str(version)


def read_alembic_version_from_engine(engine: Engine) -> str:
    """Read alembic_version using an already-configured engine (no URL round-trip)."""
    with engine.connect() as conn:
        return _read_alembic_version_from_connection(conn)


def read_alembic_version(database_url: str) -> str:
    reject_sqlalchemy_masked_url(database_url)
    validate_url_isolated(database_url)
    engine = create_engine(database_url)
    with engine.connect() as conn:
        return _read_alembic_version_from_connection(conn)


def validate_url_isolated(database_url: str) -> None:
    """Ensure we never accidentally read version from an unvalidated URL."""
    database_hostname(database_url)


def require_alembic_version(database_url: str, expected: str, *, context: str) -> str:
    current = read_alembic_version(database_url)
    if current != expected:
        raise MigrationStateError(
            f"{context}: expected alembic revision {expected!r}, found {current!r}"
        )
    return current


def upgrade_to_revision(database_url: str, target_revision: str, *, context: str) -> None:
    """Run alembic upgrade with isolated DATABASE_URL (ignores shell env)."""
    env = build_alembic_subprocess_env(database_url)
    if env.get("DATABASE_URL") != database_url:
        raise DatabaseSafetyError("Alembic subprocess DATABASE_URL mismatch")

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", target_revision],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise MigrationStateError(
            f"{context}: alembic upgrade {target_revision} failed (code {result.returncode})\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    require_alembic_version(database_url, target_revision, context=f"post-upgrade {target_revision}")


APPROVED_REVISION_CHAIN = (REVISION_L7, REVISION_M8, REVISION_N9A, REVISION_N9B)


def planned_migration_steps(current: str) -> list[str]:
    """Return target revisions still to apply along the approved chain."""
    if current not in APPROVED_REVISION_CHAIN:
        raise MigrationStateError(f"Unsupported alembic revision {current!r}")
    index = APPROVED_REVISION_CHAIN.index(current)
    return list(APPROVED_REVISION_CHAIN[index + 1 :])


def next_revision(current: str) -> str | None:
    steps = planned_migration_steps(current)
    return steps[0] if steps else None