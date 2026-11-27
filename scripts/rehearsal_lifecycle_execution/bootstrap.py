"""Import path bootstrap for rehearsal CLI (backend app packages + scripts package)."""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_backend_import_paths() -> Path:
    """
    Ensure ``backend/`` and ``backend/scripts/`` are on ``sys.path``.

    Matches other backend scripts (e.g. queue_device_super_admins.py) that use
    ``parents[1]`` from ``backend/scripts/`` to import ``core``, ``models``, etc.
    """
    package_dir = Path(__file__).resolve().parent
    scripts_dir = package_dir.parent
    backend_dir = scripts_dir.parent
    for directory in (backend_dir, scripts_dir):
        entry = str(directory)
        if entry not in sys.path:
            sys.path.insert(0, entry)
    return backend_dir


def _load_bootstrap_module():
    """Load this file when the package is not yet importable (direct __main__.py)."""
    return ensure_backend_import_paths()