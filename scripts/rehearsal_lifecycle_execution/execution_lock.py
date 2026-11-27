"""Single-run safeguard for rehearsal execution (no new infrastructure)."""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.orm import Session

from rehearsal_lifecycle_execution.errors import RehearsalExecutionError

# Stable 32-bit advisory lock key (phase 1.3.8 rehearsal).
_PG_ADVISORY_LOCK_KEY = 138138138


class RehearsalExecutionLock:
    """Base handle released on context exit."""

    def release(self) -> None:
        raise NotImplementedError


class _PgAdvisoryLock(RehearsalExecutionLock):
    def __init__(self, db: Session, key: int) -> None:
        self._db = db
        self._key = key
        self._held = True

    def release(self) -> None:
        if not self._held:
            return
        self._db.execute(
            text("SELECT pg_advisory_unlock(:k)"),
            {"k": self._key},
        )
        self._held = False


class _FileRehearsalLock(RehearsalExecutionLock):
    """Process-local lock file (used for SQLite tests and non-PostgreSQL)."""

    def __init__(self, path: Path, fd: int) -> None:
        self._path = path
        self._fd = fd
        self._held = True

    def release(self) -> None:
        if not self._held:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._held = False


def _default_lock_path() -> Path:
    base = Path(os.environ.get("PHASE_138_LOCK_DIR", "")).expanduser() if os.environ.get("PHASE_138_LOCK_DIR") else Path.home() / ".vyon"
    base.mkdir(parents=True, exist_ok=True)
    return base / "rehearsal_phase_1_3_8.lock"


def _try_acquire_file_lock(path: Path) -> _FileRehearsalLock:
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if sys.platform == "win32":
            import msvcrt

            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                os.close(fd)
                raise RehearsalExecutionError(
                    "Another rehearsal process holds the local execution lock"
                ) from exc
        else:
            import fcntl

            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                os.close(fd)
                raise RehearsalExecutionError(
                    "Another rehearsal process holds the local execution lock"
                ) from exc
        return _FileRehearsalLock(path, fd)
    except Exception:
        os.close(fd)
        raise


def acquire_rehearsal_execution_lock(db: Session) -> RehearsalExecutionLock:
    """
    Prevent concurrent rehearsal execute / device-sync queue phases.

    PostgreSQL: session-level pg_try_advisory_lock (no schema change).
    Other dialects: exclusive file lock under ~/.vyon/ (documented limitation).
    """
    bind = db.get_bind()
    dialect = bind.dialect.name if bind is not None else ""

    if dialect == "postgresql":
        acquired = db.execute(
            text("SELECT pg_try_advisory_lock(:k)"),
            {"k": _PG_ADVISORY_LOCK_KEY},
        ).scalar()
        if not acquired:
            raise RehearsalExecutionError(
                "Another rehearsal session holds the PostgreSQL advisory lock "
                f"(key {_PG_ADVISORY_LOCK_KEY}); aborting to avoid duplicate queue inserts"
            )
        return _PgAdvisoryLock(db, _PG_ADVISORY_LOCK_KEY)

    return _try_acquire_file_lock(_default_lock_path())


@contextmanager
def rehearsal_execution_lock(db: Session) -> Iterator[None]:
    handle = acquire_rehearsal_execution_lock(db)
    try:
        yield
    finally:
        handle.release()


@contextmanager
def rehearsal_run_lock(engine) -> Iterator[None]:
    """
    Hold lock for an entire run_execute / device-sync-only invocation.

    PostgreSQL: connection-scoped advisory lock (released when connection closes).
    """
    dialect = engine.dialect.name if engine.dialect is not None else ""
    if dialect == "postgresql":
        conn = engine.connect()
        acquired = conn.execute(
            text("SELECT pg_try_advisory_lock(:k)"),
            {"k": _PG_ADVISORY_LOCK_KEY},
        ).scalar()
        if not acquired:
            conn.close()
            raise RehearsalExecutionError(
                "Another rehearsal session holds the PostgreSQL advisory lock; aborting"
            )
        try:
            yield
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _PG_ADVISORY_LOCK_KEY})
            conn.close()
    else:
        handle = _try_acquire_file_lock(_default_lock_path())
        try:
            yield
        finally:
            handle.release()