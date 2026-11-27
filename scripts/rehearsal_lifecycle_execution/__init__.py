"""Phase 1.3.8 — Neon rehearsal membership lifecycle execution tooling."""

import importlib.util
from pathlib import Path

_bootstrap_path = Path(__file__).resolve().with_name("bootstrap.py")
_spec = importlib.util.spec_from_file_location(
    "rehearsal_lifecycle_execution.bootstrap",
    _bootstrap_path,
)
if _spec is not None and _spec.loader is not None:
    _bootstrap_mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_bootstrap_mod)
    _bootstrap_mod.ensure_backend_import_paths()

from rehearsal_lifecycle_execution.constants import REHEARSAL_DB_HOST

__all__ = ["REHEARSAL_DB_HOST"]