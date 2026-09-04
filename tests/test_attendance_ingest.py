"""Tests for ZKTeco ATTLOG/OPERLOG ingest efficiency (empty uploads + trainer-only punches)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import AttendancePunch, DeviceAttendanceLog, PushDevice
from routes.device import receive_attendance_data
from services.attendance_service import AttendanceService
from services.push_device_service import PushDeviceService


@pytest.fixture()
def db() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _attlog_line(pin: int, stamped: str = "2026-09-03 08:15:00") -> str:
    return f"{pin}\t{stamped}\t0\t1\t0\t0"


def _mock_request(*, table: str, body: str) -> MagicMock:
    request = MagicMock()
    request.method = "POST"
    request.url = f"http://test/iclock/cdata?SN=DEV&table={table}"
    request.query_params = {"SN": "DEV", "table": table}
    request.headers = {
        "content-type": "text/plain",
        "content-length": str(len(body.encode("utf-8"))),
    }

    async def _body() -> bytes:
        return body.encode("utf-8")

    request.body = _body
    return request


async def _post_cdata(db: Session, *, sn: str, table: str, body: str):
    request = _mock_request(table=table, body=body)
    request.query_params = {"SN": sn, "table": table}
    request.url = f"http://test/iclock/cdata?SN={sn}&table={table}"
    return await receive_attendance_data(request=request, SN=sn, db=db)


class TestEmptyUploadSkip:
    def test_empty_operlog_returns_ok_without_device_attendance_log(self, db: Session):
        response = asyncio.run(_post_cdata(db, sn="TBS2254700504", table="OPERLOG", body=""))
        assert response.body == b"OK"
        assert db.execute(select(DeviceAttendanceLog)).scalars().all() == []
        device = db.execute(
            select(PushDevice).where(PushDevice.serial_number == "TBS2254700504")
        ).scalar_one()
        assert device is not None

    def test_empty_attlog_returns_ok_without_device_attendance_log(self, db: Session):
        response = asyncio.run(_post_cdata(db, sn="TBS2254700504", table="ATTLOG", body="   \n"))
        assert response.body == b"OK"
        assert db.execute(select(DeviceAttendanceLog)).scalars().all() == []

    def test_service_skips_empty_upload(self, db: Session):
        service = PushDeviceService(db)
        result = service.log_device_table_upload(
            device_serial="DEV1",
            raw_payload="",
            table_name="OPERLOG",
        )
        assert result is None
        assert db.execute(select(DeviceAttendanceLog)).scalars().all() == []

    @pytest.mark.parametrize(
        "raw_payload",
        [
            "",  # completely empty ZKTeco body
            " \r\n\t \r\n",  # whitespace-only body observed in empty uploads
        ],
        ids=["empty_string", "whitespace_crlf_tabs"],
    )
    def test_observed_empty_zkteco_upload_shapes(self, db: Session, raw_payload: str):
        """
        Regression for production empty PUSH uploads (record_count was 0 in DB).

        Emptiness must be ``not raw_payload.strip()`` — not ``record_count == 0``.
        """
        assert not raw_payload.strip()

        response = asyncio.run(
            _post_cdata(
                db,
                sn="TBS2254700504",
                table="OPERLOG",
                body=raw_payload,
            )
        )
        assert response.status_code == 200
        assert response.body == b"OK"
        assert response.media_type == "text/plain"
        assert db.execute(select(DeviceAttendanceLog)).scalars().all() == []
        assert db.execute(select(AttendancePunch)).scalars().all() == []
        # Presence / registration still runs for protocol health.
        assert (
            db.execute(
                select(PushDevice).where(PushDevice.serial_number == "TBS2254700504")
            ).scalar_one_or_none()
            is not None
        )


class TestBareAttlogNotTreatedAsEmpty:
    """Bare pin\\ttime lines must not be skipped as empty uploads."""

    BARE_MEMBER_LINE = "7\t2026-09-03 07:38:49\t0\t0\t0"

    def test_bare_attlog_line_is_not_skipped_as_empty(self, db: Session):
        """
        Real ATTLOG-style data without an ``ATTLOG:`` prefix.

        Must not be treated as empty merely because some counters could report 0.
        PIN 7 is a member PIN (<= 50000): no punch, but raw log is still stored.
        """
        assert self.BARE_MEMBER_LINE.strip()  # non-empty by strip() rule

        response = asyncio.run(
            _post_cdata(
                db,
                sn="TBS2254700504",
                table="ATTLOG",
                body=self.BARE_MEMBER_LINE,
            )
        )
        assert response.status_code == 200
        assert response.body == b"OK"

        logs = db.execute(select(DeviceAttendanceLog)).scalars().all()
        assert len(logs) == 1
        assert logs[0].raw_payload == self.BARE_MEMBER_LINE
        assert logs[0].is_processed is True
        # Member PIN: ignored for punches under current gym policy.
        assert db.execute(select(AttendancePunch)).scalars().all() == []

    def test_non_blank_payload_stored_even_when_record_count_forced_zero(
        self, db: Session, monkeypatch: pytest.MonkeyPatch
    ):
        """Guardrail: skip decision must not key off record_count == 0."""
        monkeypatch.setattr(
            PushDeviceService,
            "_count_table_records",
            staticmethod(lambda raw_payload, table_name: 0),
        )
        result = PushDeviceService(db).log_device_table_upload(
            device_serial="DEV1",
            raw_payload=self.BARE_MEMBER_LINE,
            table_name="ATTLOG",
        )
        assert result is not None
        assert result.record_count == 0
        assert len(db.execute(select(DeviceAttendanceLog)).scalars().all()) == 1


class TestMemberPinIgnored:
    def test_member_pin_not_inserted(self, db: Session):
        inserted = AttendanceService(db).ingest_attlog_payload(
            device_serial="DEV1",
            raw_payload=_attlog_line(12345),
        )
        assert inserted == 0
        assert db.execute(select(AttendancePunch)).scalars().all() == []

    def test_member_pin_boundary_50000_ignored(self, db: Session):
        inserted = AttendanceService(db).ingest_attlog_payload(
            device_serial="DEV1",
            raw_payload=_attlog_line(50000),
        )
        assert inserted == 0
        assert db.execute(select(AttendancePunch)).scalars().all() == []

    def test_attlog_member_only_stores_raw_log_not_punches(self, db: Session):
        body = _attlog_line(42)
        response = asyncio.run(_post_cdata(db, sn="DEV1", table="ATTLOG", body=body))
        assert response.body == b"OK"
        logs = db.execute(select(DeviceAttendanceLog)).scalars().all()
        assert len(logs) == 1
        assert logs[0].record_count == 1
        assert logs[0].is_processed is True
        assert db.execute(select(AttendancePunch)).scalars().all() == []


class TestTrainerPinProcessed:
    def test_trainer_pin_inserted(self, db: Session):
        inserted = AttendanceService(db).ingest_attlog_payload(
            device_serial="DEV1",
            raw_payload=_attlog_line(50007),
        )
        assert inserted == 1
        punches = db.execute(select(AttendancePunch)).scalars().all()
        assert len(punches) == 1
        assert punches[0].person_type == "trainer"
        assert punches[0].person_id == 7
        assert punches[0].pin == 50007

    def test_attlog_trainer_via_cdata(self, db: Session):
        body = _attlog_line(50003, "2026-09-03 07:00:00")
        response = asyncio.run(_post_cdata(db, sn="DEV1", table="ATTLOG", body=body))
        assert response.body == b"OK"
        punches = db.execute(select(AttendancePunch)).scalars().all()
        assert len(punches) == 1
        assert punches[0].person_type == "trainer"
        assert punches[0].person_id == 3


class TestMixedPayload:
    def test_mixed_member_and_trainer(self, db: Session):
        payload = "\n".join(
            [
                _attlog_line(1001, "2026-09-03 08:00:00"),
                _attlog_line(50012, "2026-09-03 08:05:00"),
                _attlog_line(55, "2026-09-03 08:10:00"),
            ]
        )
        inserted = AttendanceService(db).ingest_attlog_payload(
            device_serial="DEV1",
            raw_payload=payload,
        )
        assert inserted == 1
        punches = db.execute(select(AttendancePunch)).scalars().all()
        assert len(punches) == 1
        assert punches[0].pin == 50012
        assert punches[0].person_id == 12
        assert punches[0].person_type == "trainer"

    def test_mixed_via_cdata(self, db: Session):
        payload = "\n".join(
            [
                _attlog_line(9, "2026-09-03 09:00:00"),
                _attlog_line(50001, "2026-09-03 09:01:00"),
            ]
        )
        response = asyncio.run(_post_cdata(db, sn="MIXED", table="ATTLOG", body=payload))
        assert response.body == b"OK"
        punches = db.execute(select(AttendancePunch)).scalars().all()
        assert len(punches) == 1
        assert punches[0].person_id == 1
        logs = db.execute(select(DeviceAttendanceLog)).scalars().all()
        assert len(logs) == 1
        assert logs[0].is_processed is True


class TestNonEmptyNoisyTablesNotLogged:
    def test_non_empty_operlog_is_not_stored(self, db: Session):
        body = "OPERLOG:OPLOG 1\t2026-09-03 10:00:00\t0"
        response = asyncio.run(_post_cdata(db, sn="DEV1", table="OPERLOG", body=body))
        assert response.body == b"OK"
        assert db.execute(select(DeviceAttendanceLog)).scalars().all() == []
        assert db.execute(select(AttendancePunch)).scalars().all() == []

    def test_non_empty_biodata_is_not_stored(self, db: Session):
        body = "BIODATA:1\t0\t50\tABCDEF"
        response = asyncio.run(_post_cdata(db, sn="DEV1", table="BIODATA", body=body))
        assert response.body == b"OK"
        assert db.execute(select(DeviceAttendanceLog)).scalars().all() == []


class TestProtocolResponseUnchanged:
    def test_ok_media_type(self, db: Session):
        response = asyncio.run(_post_cdata(db, sn="DEV1", table="OPERLOG", body=""))
        assert response.media_type == "text/plain"
        assert response.body == b"OK"


class TestDeviceTimezoneIngest:
    def test_attlog_wall_clock_stored_as_real_utc(self, db: Session):
        """
        Device sends India local time without offset.
        08:54:45 IST must become 03:24:45 UTC (not labeled as 08:54 UTC).
        """
        from datetime import timezone

        from core.device_time import parse_device_wall_clock

        expected = parse_device_wall_clock("2026-09-03 08:54:45")
        assert expected.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S") == "2026-09-03 03:24:45"

        inserted = AttendanceService(db).ingest_attlog_payload(
            device_serial="DEV1",
            raw_payload="50012\t2026-09-03 08:54:45\t0\t1\t0\t0",
        )
        assert inserted == 1
        punch = db.execute(select(AttendancePunch)).scalar_one()
        # Compare absolute instants (SQLite test DB may drop tzinfo on round-trip).
        stored = punch.punched_at
        if stored.tzinfo is None:
            stored = stored.replace(tzinfo=timezone.utc)
        assert stored.astimezone(timezone.utc) == expected.astimezone(timezone.utc)

    def test_daily_query_uses_gym_calendar_day(self, db: Session):
        from datetime import date

        # 23:30 IST on Sep 3 => 18:00 UTC Sep 3 — still Sep 3 gym day.
        AttendanceService(db).ingest_attlog_payload(
            device_serial="DEV1",
            raw_payload="50007\t2026-09-03 23:30:00\t0\t1\t0\t0",
        )
        rows = AttendanceService(db).get_daily_trainer_attendance(date(2026, 9, 3))
        assert len(rows) == 1
        assert rows[0].person_id == 7
        # Late vs 06:15 IST threshold — 23:30 is late.
        assert rows[0].is_late is True

    def test_api_exposes_ist_offset(self, db: Session):
        from datetime import timezone

        from core.device_time import parse_device_wall_clock, to_device_local

        expected_utc = parse_device_wall_clock("2026-09-04 07:02:09")
        AttendanceService(db).ingest_attlog_payload(
            device_serial="DEV1",
            raw_payload="50012\t2026-09-04 07:02:09\t0\t1\t0\t0",
        )
        punch = db.execute(select(AttendancePunch)).scalar_one()
        stored = punch.punched_at
        if stored.tzinfo is None:
            stored = stored.replace(tzinfo=timezone.utc)
        assert stored.astimezone(timezone.utc) == expected_utc.astimezone(timezone.utc)

        local = to_device_local(stored)
        assert local.strftime("%H:%M:%S") == "07:02:09"
        assert local.utcoffset().total_seconds() == 5.5 * 3600
