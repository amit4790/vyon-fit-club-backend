"""CLI entry: python -m rehearsal_lifecycle_execution (from backend or repo root)."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from datetime import date
from pathlib import Path

# Bootstrap before any app/rehearsal imports (direct script run may skip package __init__).
_bootstrap_path = Path(__file__).resolve().with_name("bootstrap.py")
_spec = importlib.util.spec_from_file_location("_rehearsal_cli_bootstrap", _bootstrap_path)
if _spec is not None and _spec.loader is not None:
    _bootstrap_mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_bootstrap_mod)
    _bootstrap_mod.ensure_backend_import_paths()

from rehearsal_lifecycle_execution.runner import run_dry_run, run_execute


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase 1.3.8 Neon rehearsal lifecycle execution tooling (vyon-lifecycle-rehearsal only)."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Read-only inspection; no writes or migrations")
    mode.add_argument("--execute", action="store_true", help="Run migrations, reconciliation, and device sync")
    parser.add_argument(
        "--device-sync-only",
        action="store_true",
        help="Requires --execute; retry device sync without repeating reconciliation",
    )
    parser.add_argument("--execution-date", type=str, default=None, help="ISO date override (default: today)")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--allow-database-only-without-device-sync",
        action="store_true",
        help="Opt in when zero eligible PUSH devices exist (no device commands queued)",
    )
    args = parser.parse_args()

    if args.device_sync_only and not args.execute:
        parser.error("--device-sync-only requires --execute")

    execution_date = date.fromisoformat(args.execution_date) if args.execution_date else None

    if args.dry_run:
        return run_dry_run(execution_date=execution_date, verbose=args.verbose)

    return run_execute(
        execution_date=execution_date,
        device_sync_only=args.device_sync_only,
        allow_zero_push_devices=args.allow_database_only_without_device_sync,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    raise SystemExit(main())