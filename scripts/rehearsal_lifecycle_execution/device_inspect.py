"""Inspect queued device commands for allowed USERINFO access updates only."""

from __future__ import annotations

import re
from typing import Iterable

from rehearsal_lifecycle_execution.errors import DeviceSyncError

_BANNED_PATTERNS = (
    re.compile(r"DATA\s+DELETE\s+BIOPHOTO", re.I),
    re.compile(r"DATA\s+UPDATE\s+BIOPHOTO", re.I),
    re.compile(r"DATA\s+DELETE\s+USER\b", re.I),
    re.compile(r"DATA\s+DELETE\s+USERINFO", re.I),
    re.compile(r"DATA\s+UPDATE\s+USER\b", re.I),
)

_ALLOWED_PATTERN = re.compile(r"DATA\s+UPDATE\s+USERINFO\b", re.I)
_PRI_PATTERN = re.compile(r"\bPri=(\d+)\b")


def assert_access_sync_commands(commands: Iterable[str]) -> list[int]:
    """
    Validate commands are DATA UPDATE USERINFO with Pri in {0, 1} only.
    Returns parsed Pri values.
    """
    privileges: list[int] = []
    for command in commands:
        upper = command or ""
        for pattern in _BANNED_PATTERNS:
            if pattern.search(upper):
                raise DeviceSyncError(f"Disallowed device command pattern: {pattern.pattern}")

        if not _ALLOWED_PATTERN.search(upper):
            raise DeviceSyncError("Device sync must only queue DATA UPDATE USERINFO commands")

        match = _PRI_PATTERN.search(upper)
        if not match:
            raise DeviceSyncError("USERINFO command missing Pri=")
        pri = int(match.group(1))
        if pri not in (0, 1):
            raise DeviceSyncError(f"USERINFO Pri must be 0 or 1, got {pri}")
        privileges.append(pri)
    return privileges