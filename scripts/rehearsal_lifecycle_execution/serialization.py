"""Canonical JSON and checksums."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def canonical_json_dumps(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, default=_json_default, separators=(",", ":"))


def sha256_hex(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def checksum_file_payload(*parts: Any) -> tuple[str, str]:
    body = canonical_json_dumps(parts)
    return body, sha256_hex(body)