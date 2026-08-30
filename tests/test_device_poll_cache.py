"""Unit tests for ZKTeco poll/heartbeat Neon- sparring cache."""

from __future__ import annotations

import unittest
from datetime import timedelta
from unittest.mock import MagicMock

from services.push_device_service import _DevicePollCache


class DevicePollCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cache = _DevicePollCache()

    def test_heartbeat_with_transient_metadata_skips_db_after_persist(self) -> None:
        sn = "ZAM230001234"
        self.cache.note_device_persisted(
            sn,
            {
                "platform": "ZAM230_TFT",
                "firmware_version": "Ver1.0.27",
                "device_type": "T&A PUSH",
                "device_name": "Front Desk",
            },
        )

        # Typical ZKTeco heartbeat includes options/pushver/language every time.
        heartbeat_info = {
            "options": "all",
            "pushver": "2.0",
            "language": "69",
            "platform": "ZAM230_TFT",
            "firmware_version": "Ver1.0.27",
            "device_type": "T&A PUSH",
            "device_name": "Front Desk",
        }

        self.assertTrue(
            self.cache.can_skip_heartbeat_db(sn, heartbeat_info, interval_seconds=600)
        )
        self.assertFalse(self.cache.needs_last_seen_write(sn, interval_seconds=600))

    def test_heartbeat_skips_when_only_transient_params_present(self) -> None:
        sn = "ZAM230001234"
        self.cache.note_device_persisted(
            sn,
            {"platform": "ZAM230_TFT", "firmware_version": "Ver1.0.27"},
        )
        self.assertTrue(
            self.cache.can_skip_heartbeat_db(
                sn,
                {"options": "all", "pushver": "2.0", "language": "69"},
                interval_seconds=600,
            )
        )

    def test_heartbeat_does_not_skip_unknown_device(self) -> None:
        self.assertFalse(
            self.cache.can_skip_heartbeat_db(
                "UNKNOWN",
                {"options": "all", "platform": "ZAM230_TFT"},
                interval_seconds=600,
            )
        )

    def test_heartbeat_does_not_skip_when_identity_metadata_changes(self) -> None:
        sn = "ZAM230001234"
        self.cache.note_device_persisted(sn, {"firmware_version": "Ver1.0.27"})
        self.assertFalse(
            self.cache.can_skip_heartbeat_db(
                sn,
                {"firmware_version": "Ver1.0.28"},
                interval_seconds=600,
            )
        )

    def test_failed_commit_does_not_poison_last_seen_throttle(self) -> None:
        sn = "ZAM230001234"
        # Peek must not stamp.
        self.assertTrue(self.cache.needs_last_seen_write(sn, interval_seconds=600))
        self.assertTrue(self.cache.needs_last_seen_write(sn, interval_seconds=600))

        # Simulate successful persist.
        self.cache.note_device_persisted(sn, {"platform": "ZAM230_TFT"})
        self.assertFalse(self.cache.needs_last_seen_write(sn, interval_seconds=600))

        # Simulate discovering the write never landed — clear stamp and retry.
        self.cache.clear_last_seen_stamp(sn)
        self.assertTrue(self.cache.needs_last_seen_write(sn, interval_seconds=600))

    def test_empty_poll_skip_and_command_queue_invalidation(self) -> None:
        sn = "ZAM230001234"
        self.cache.mark_empty_poll(sn, skip_seconds=180)
        self.assertTrue(self.cache.should_skip_empty_poll_db(sn))

        self.cache.mark_command_queued(sn)
        self.assertFalse(self.cache.should_skip_empty_poll_db(sn))

    def test_expired_last_seen_interval_requires_db(self) -> None:
        sn = "ZAM230001234"
        self.cache.note_device_persisted(sn, {"platform": "ZAM230_TFT"})
        # Force the stamp into the past.
        self.cache._last_seen_written_at[sn] = self.cache._now() - timedelta(seconds=601)
        self.assertFalse(
            self.cache.can_skip_heartbeat_db(
                sn,
                {"platform": "ZAM230_TFT", "options": "all"},
                interval_seconds=600,
            )
        )
        self.assertTrue(self.cache.needs_last_seen_write(sn, interval_seconds=600))


class RegisterOrUpdateStampTests(unittest.TestCase):
    def test_note_device_persisted_only_after_successful_commit(self) -> None:
        from services import push_device_service as module

        cache = _DevicePollCache()
        original = module.device_poll_cache
        module.device_poll_cache = cache
        self.addCleanup(setattr, module, "device_poll_cache", original)

        sn = "ZAM230009999"
        existing = MagicMock()
        existing.platform = "ZAM230_TFT"
        existing.firmware_version = "Ver1.0.27"
        existing.device_type = "T&A PUSH"
        existing.device_name = "Gate"
        existing.last_seen = None

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = existing
        db.commit.side_effect = RuntimeError("neon unavailable")

        service = module.PushDeviceService(db)
        with self.assertRaises(RuntimeError):
            service.register_or_update_device(sn, force_touch=True)

        # Failed commit must not stamp the throttle window.
        self.assertTrue(cache.needs_last_seen_write(sn, interval_seconds=600))
        self.assertFalse(
            cache.can_skip_heartbeat_db(
                sn,
                {"platform": "ZAM230_TFT", "options": "all"},
                interval_seconds=600,
            )
        )


if __name__ == "__main__":
    unittest.main()
