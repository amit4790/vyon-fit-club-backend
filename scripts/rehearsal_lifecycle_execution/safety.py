"""DATABASE_URL loading and hostname safety checks."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values
from sqlalchemy.engine import Engine

from rehearsal_lifecycle_execution.constants import REHEARSAL_DB_HOST
from rehearsal_lifecycle_execution.errors import DatabaseSafetyError


def backend_env_path() -> Path:
    """Resolve backend/.env relative to repository layout."""
    return Path(__file__).resolve().parents[2] / ".env"


def load_backend_env() -> dict[str, str | None]:
    """Load only backend/.env (no process-wide env merge before validation)."""
    path = backend_env_path()
    if not path.is_file():
        raise DatabaseSafetyError(f"Missing backend environment file: {path}")
    return dotenv_values(path)


def resolve_database_url(env: dict[str, str | None] | None = None) -> str:
    """Return DATABASE_URL from backend/.env after safety checks."""
    env = env if env is not None else load_backend_env()
    url = (env.get("DATABASE_URL") or "").strip()
    if not url:
        raise DatabaseSafetyError("DATABASE_URL is missing in backend/.env")

    prod = (env.get("DATABASE_URL_PROD") or "").strip()
    if prod and prod == url:
        raise DatabaseSafetyError(
            "DATABASE_URL_PROD equals active DATABASE_URL; refusing to proceed"
        )

    validate_database_hostname(url)
    return url


def database_hostname(database_url: str) -> str:
    host = urlparse(database_url).hostname
    if not host:
        raise DatabaseSafetyError("DATABASE_URL has no hostname")
    return host


def validate_database_hostname(database_url: str) -> None:
    """
    Require exact hostname equality with the verified rehearsal endpoint.
    Substring matching is intentionally rejected.
    """
    host = database_hostname(database_url)
    if host != REHEARSAL_DB_HOST:
        raise DatabaseSafetyError(
            f"DATABASE_URL hostname {host!r} does not exactly match rehearsal host "
            f"{REHEARSAL_DB_HOST!r}"
        )


def assert_write_phase_hostname(database_url: str) -> None:
    """Re-validate hostname immediately before every write phase."""
    validate_database_hostname(database_url)


def assert_engine_uses_validated_url(engine: Engine, validated_url: str) -> None:
    """Abort if SQLAlchemy engine host differs from the validated rehearsal URL."""
    engine_host = urlparse(str(engine.url)).hostname
    validated_host = database_hostname(validated_url)
    if engine_host != validated_host:
        raise DatabaseSafetyError(
            f"Engine hostname {engine_host!r} != validated {validated_host!r}"
        )


def build_alembic_subprocess_env(validated_database_url: str) -> dict[str, str]:
    """
    Minimal subprocess environment for Alembic.

    Does not inherit shell DATABASE_URL or DATABASE_URL_PROD.
    """
    validate_database_hostname(validated_database_url)
    allowed_keys = (
        "PATH",
        "SYSTEMROOT",
        "HOME",
        "USERPROFILE",
        "TEMP",
        "TMP",
        "PYTHONPATH",
        "VIRTUAL_ENV",
    )
    env: dict[str, str] = {}
    for key in allowed_keys:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    env["DATABASE_URL"] = validated_database_url
    if os.environ.get("DATABASE_URL") and os.environ.get("DATABASE_URL") != validated_database_url:
        # Shell conflict is expected; subprocess must not see the shell value.
        pass
    return env