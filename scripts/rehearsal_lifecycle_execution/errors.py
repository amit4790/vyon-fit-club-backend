"""Execution tooling errors."""


class RehearsalExecutionError(Exception):
    """Base error for rehearsal lifecycle execution."""


class DatabaseSafetyError(RehearsalExecutionError):
    """DATABASE_URL or host validation failed."""


class SnapshotMismatchError(RehearsalExecutionError):
    """Live data does not match reviewed preflight snapshot."""


class MigrationStateError(RehearsalExecutionError):
    """Alembic revision is not the expected value."""


class ReconciliationError(RehearsalExecutionError):
    """Reconciliation precondition or transition failed."""


class RemainingDaysError(ReconciliationError):
    """remaining_days_from_today produced zero or negative."""


class DeviceSyncError(RehearsalExecutionError):
    """Device synchronisation failed or produced disallowed commands."""


class PreflightError(RehearsalExecutionError):
    """Membership queue integrity preflight check failed."""


class BackupValidationError(RehearsalExecutionError):
    """Backup export incomplete or checksum invalid."""