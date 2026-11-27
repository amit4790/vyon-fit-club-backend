#!/usr/bin/env python3
"""Render Cron Job runner: POST sync-expired-memberships on the production API."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

EXPIRY_SYNC_PATH = "/api/internal/cron/sync-expired-memberships"
DEFAULT_TIMEOUT_SECONDS = 120.0

SAFE_RESPONSE_KEYS = (
    "message",
    "run_date",
    "subscriptions_marked_expired",
    "members_device_synced",
    "members_disabled_on_device",
    "members_still_enabled_on_device",
)

logger = logging.getLogger("run_expiry_sync")


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse HTTP redirects so X-Cron-Secret is never sent to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ARG002
        return None


def _install_no_redirect_opener() -> None:
    opener = urllib.request.build_opener(_NoRedirectHandler())
    urllib.request.install_opener(opener)


_install_no_redirect_opener()


class RunnerError(Exception):
    """Base error for the cron runner."""


class ConfigError(RunnerError):
    """Missing or invalid configuration."""


@dataclass(frozen=True)
class RunnerConfig:
    api_base_url: str
    cron_secret: str
    timeout_seconds: float


def _parse_timeout_seconds() -> float:
    raw = (os.environ.get("CRON_REQUEST_TIMEOUT_SECONDS") or "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError("CRON_REQUEST_TIMEOUT_SECONDS must be a number") from exc
    if value <= 0:
        raise ConfigError("CRON_REQUEST_TIMEOUT_SECONDS must be positive")
    return value


def validate_api_base_url(api_base_url: str) -> str:
    """Require HTTPS with a host; return base URL without trailing slash."""
    value = api_base_url.strip()
    if not value:
        raise ConfigError("API_BASE_URL is required")
    parsed = urlparse(value)
    if parsed.scheme.lower() != "https":
        raise ConfigError("API_BASE_URL must use https")
    if not parsed.netloc:
        raise ConfigError("API_BASE_URL must include a host")
    if parsed.username or parsed.password:
        raise ConfigError("API_BASE_URL must not include credentials")
    return value.rstrip("/")


def build_request_url(api_base_url: str) -> str:
    return f"{api_base_url}{EXPIRY_SYNC_PATH}"


def load_config() -> RunnerConfig:
    api_base_url = validate_api_base_url(os.environ.get("API_BASE_URL", ""))
    cron_secret = (os.environ.get("CRON_SECRET") or "").strip()
    if not cron_secret:
        raise ConfigError("CRON_SECRET is required")
    timeout_seconds = _parse_timeout_seconds()
    return RunnerConfig(
        api_base_url=api_base_url,
        cron_secret=cron_secret,
        timeout_seconds=timeout_seconds,
    )


def summarize_response_body(raw: bytes, *, status_code: int) -> str:
    """Return a JSON summary with only known safe fields from the cron contract."""
    if status_code < 200 or status_code >= 300:
        if status_code in (401, 503):
            return json.dumps({"status_code": status_code, "detail": "withheld"})
        if not raw:
            return json.dumps({"status_code": status_code, "body": "empty"})
        return json.dumps({"status_code": status_code, "body": "non_json_or_unexpected"})

    if not raw:
        return json.dumps({"warning": "empty_success_body"})
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return json.dumps({"warning": "success_body_not_json"})
    if not isinstance(data, dict):
        return json.dumps({"warning": "success_body_not_object"})
    summary: dict[str, Any] = {
        key: data[key] for key in SAFE_RESPONSE_KEYS if key in data
    }
    return json.dumps(summary, sort_keys=True)


def execute_expiry_sync(
    config: RunnerConfig,
    *,
    urlopen: Any | None = None,
) -> int:
    opener = urlopen if urlopen is not None else urllib.request.urlopen
    url = build_request_url(config.api_base_url)
    started = time.perf_counter()
    logger.info(
        "Starting expiry sync path=%s timeout_seconds=%.1f",
        EXPIRY_SYNC_PATH,
        config.timeout_seconds,
    )

    request = urllib.request.Request(
        url,
        data=b"",
        method="POST",
        headers={
            "X-Cron-Secret": config.cron_secret,
            "Accept": "application/json",
        },
    )

    try:
        with opener(request, timeout=config.timeout_seconds) as response:
            status = getattr(response, "status", response.getcode())
            body = response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read() if exc.fp else b""
        duration_ms = int((time.perf_counter() - started) * 1000)
        summary = summarize_response_body(body, status_code=status)
        if status == 401:
            logger.error(
                "Expiry sync failed: invalid cron secret (HTTP 401) duration_ms=%d",
                duration_ms,
            )
        elif status == 503:
            logger.error(
                "Expiry sync failed: cron secret not configured on API (HTTP 503) duration_ms=%d",
                duration_ms,
            )
        elif 300 <= status < 400:
            logger.error(
                "Expiry sync failed: HTTP redirect not allowed (HTTP %s) duration_ms=%d",
                status,
                duration_ms,
            )
        else:
            logger.error(
                "Expiry sync failed path=%s status=%s duration_ms=%d summary=%s",
                EXPIRY_SYNC_PATH,
                status,
                duration_ms,
                summary,
            )
        return 1
    except urllib.error.URLError as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        reason = exc.reason
        if isinstance(reason, TimeoutError) or (
            reason is not None and "timed out" in str(reason).lower()
        ):
            logger.error(
                "Expiry sync failed: request timed out duration_ms=%d",
                duration_ms,
            )
        else:
            logger.error(
                "Expiry sync failed: network error duration_ms=%d reason_type=%s",
                duration_ms,
                type(reason).__name__ if reason is not None else "unknown",
            )
        return 1
    except TimeoutError:
        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.error("Expiry sync failed: request timed out duration_ms=%d", duration_ms)
        return 1

    duration_ms = int((time.perf_counter() - started) * 1000)
    if 300 <= status < 400:
        logger.error(
            "Expiry sync failed: HTTP redirect not allowed (HTTP %s) duration_ms=%d",
            status,
            duration_ms,
        )
        return 1
    if status < 200 or status >= 300:
        summary = summarize_response_body(body, status_code=status)
        logger.error(
            "Expiry sync failed path=%s status=%s duration_ms=%d summary=%s",
            EXPIRY_SYNC_PATH,
            status,
            duration_ms,
            summary,
        )
        return 1

    summary = summarize_response_body(body, status_code=status)
    logger.info(
        "Expiry sync succeeded path=%s status=%s duration_ms=%d summary=%s",
        EXPIRY_SYNC_PATH,
        status,
        duration_ms,
        summary,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    _ = argv
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        config = load_config()
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        return 1
    return execute_expiry_sync(config)


if __name__ == "__main__":
    sys.exit(main())