"""CLI import path regression (no database)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BACKEND_DIR / "scripts"
REHEARSAL_PKG = SCRIPTS_DIR / "rehearsal_lifecycle_execution"


def test_bootstrap_puts_backend_and_scripts_on_path():
    from rehearsal_lifecycle_execution.bootstrap import ensure_backend_import_paths

    backend = ensure_backend_import_paths()
    assert backend == BACKEND_DIR
    assert str(BACKEND_DIR) in sys.path
    assert str(SCRIPTS_DIR) in sys.path
    import core.config  # noqa: F401


def test_cli_module_help_with_scripts_only_pythonpath():
    """Reproduce user startup: PYTHONPATH=scripts only, cwd not required to be backend."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SCRIPTS_DIR)
    proc = subprocess.run(
        [sys.executable, "-m", "rehearsal_lifecycle_execution", "--help"],
        cwd=str(BACKEND_DIR.parent),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "--dry-run" in proc.stdout


def test_direct_main_py_help_without_backend_cwd():
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(
        [sys.executable, str(REHEARSAL_PKG / "__main__.py"), "--help"],
        cwd=str(BACKEND_DIR.parent),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "--execute" in proc.stdout