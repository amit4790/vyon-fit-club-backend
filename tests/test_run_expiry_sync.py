"""Unit tests for scripts/run_expiry_sync.py (no HTTP to prod/rehearsal)."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = BACKEND_DIR / "scripts" / "run_expiry_sync.py"


def _load_runner_module():
    spec = importlib.util.spec_from_file_location("run_expiry_sync", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_expiry_sync"] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner_module()

HTTPS_BASE = "https://api.example.com"
VALID_ENV = {
    "API_BASE_URL": HTTPS_BASE,
    "CRON_SECRET": "test-secret",
}


def _success_response(payload: dict) -> MagicMock:
    body = json.dumps(payload).encode("utf-8")
    response = MagicMock()
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    response.status = 200
    response.getcode = MagicMock(return_value=200)
    response.read = MagicMock(return_value=body)
    return response


@patch.dict("os.environ", VALID_ENV, clear=True)
@patch("run_expiry_sync.urllib.request.urlopen")
def test_success_http_200(mock_urlopen):
    mock_urlopen.return_value = _success_response(
        {
            "message": "Expired membership device sync completed",
            "run_date": "2026-11-27",
            "subscriptions_marked_expired": 2,
            "members_device_synced": 3,
            "members_disabled_on_device": 1,
            "members_still_enabled_on_device": 0,
        }
    )
    config = runner.load_config()
    assert runner.execute_expiry_sync(config) == 0
    mock_urlopen.assert_called_once()
    request = mock_urlopen.call_args[0][0]
    assert request.get_full_url() == f"{HTTPS_BASE}{runner.EXPIRY_SYNC_PATH}"
    assert request.get_method() == "POST"
    assert request.headers["X-cron-secret"] == "test-secret"


@patch.dict("os.environ", {"CRON_SECRET": "x"}, clear=True)
def test_missing_api_base_url():
    with pytest.raises(runner.ConfigError, match="API_BASE_URL is required"):
        runner.load_config()


@patch.dict("os.environ", {"API_BASE_URL": HTTPS_BASE}, clear=True)
def test_missing_cron_secret():
    with pytest.raises(runner.ConfigError, match="CRON_SECRET is required"):
        runner.load_config()


@pytest.mark.parametrize(
    "api_base_url",
    [
        "http://api.example.com",
        "ftp://api.example.com",
        "https://",
        "not-a-url",
    ],
)
def test_invalid_or_non_https_url(api_base_url):
    with patch.dict(
        "os.environ",
        {"API_BASE_URL": api_base_url, "CRON_SECRET": "secret"},
        clear=True,
    ):
        with pytest.raises(runner.ConfigError):
            runner.load_config()


@patch.dict("os.environ", VALID_ENV, clear=True)
def test_http_401():
    body = io.BytesIO(b'{"detail":"Invalid cron secret"}')
    err = urllib.error.HTTPError(
        url=f"{HTTPS_BASE}{runner.EXPIRY_SYNC_PATH}",
        code=401,
        msg="Unauthorized",
        hdrs=None,
        fp=body,
    )
    with patch("run_expiry_sync.urllib.request.urlopen", side_effect=err):
        config = runner.load_config()
        assert runner.execute_expiry_sync(config) == 1


@patch.dict("os.environ", VALID_ENV, clear=True)
def test_http_503():
    body = io.BytesIO(b'{"detail":"Cron secret is not configured"}')
    err = urllib.error.HTTPError(
        url=f"{HTTPS_BASE}{runner.EXPIRY_SYNC_PATH}",
        code=503,
        msg="Service Unavailable",
        hdrs=None,
        fp=body,
    )
    with patch("run_expiry_sync.urllib.request.urlopen", side_effect=err):
        config = runner.load_config()
        assert runner.execute_expiry_sync(config) == 1


@patch.dict("os.environ", VALID_ENV, clear=True)
def test_network_timeout():
    err = urllib.error.URLError("timed out")
    with patch("run_expiry_sync.urllib.request.urlopen", side_effect=err):
        config = runner.load_config()
        assert runner.execute_expiry_sync(config) == 1


@patch.dict("os.environ", VALID_ENV, clear=True)
def test_other_non_2xx_via_http_error():
    body = io.BytesIO(b'{"detail":"Something went wrong"}')
    err = urllib.error.HTTPError(
        url=f"{HTTPS_BASE}{runner.EXPIRY_SYNC_PATH}",
        code=500,
        msg="Internal Server Error",
        hdrs=None,
        fp=body,
    )
    with patch("run_expiry_sync.urllib.request.urlopen", side_effect=err):
        config = runner.load_config()
        assert runner.execute_expiry_sync(config) == 1


@patch.dict("os.environ", VALID_ENV, clear=True)
def test_other_non_2xx_success_channel():
    response = MagicMock()
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    response.status = 418
    response.getcode = MagicMock(return_value=418)
    response.read = MagicMock(return_value=b"")
    with patch("run_expiry_sync.urllib.request.urlopen", return_value=response):
        config = runner.load_config()
        assert runner.execute_expiry_sync(config) == 1


@patch.dict("os.environ", VALID_ENV, clear=True)
def test_redirect_not_followed_single_request():
    """A 3xx must fail with one request only; secret must not reach Location host."""
    expected_url = f"{HTTPS_BASE}{runner.EXPIRY_SYNC_PATH}"
    redirect_target = "https://evil.example.com/steal-secret"
    request_urls: list[str] = []

    def tracking_urlopen(req, timeout=None):
        _ = timeout
        request_urls.append(req.get_full_url())
        if len(request_urls) > 1:
            raise AssertionError("redirect must not trigger a second HTTP request")
        assert redirect_target not in req.get_full_url()
        raise urllib.error.HTTPError(
            expected_url,
            302,
            "Found",
            {"Location": redirect_target},
            io.BytesIO(b""),
        )

    config = runner.load_config()
    assert runner.execute_expiry_sync(config, urlopen=tracking_urlopen) == 1
    assert request_urls == [expected_url]


def test_no_redirect_handler_refuses_redirect():
    handler = runner._NoRedirectHandler()
    req = urllib.request.Request(f"{HTTPS_BASE}{runner.EXPIRY_SYNC_PATH}")
    assert (
        handler.redirect_request(
            req,
            None,
            302,
            "Found",
            {"Location": "https://evil.example.com/"},
            "https://evil.example.com/",
        )
        is None
    )