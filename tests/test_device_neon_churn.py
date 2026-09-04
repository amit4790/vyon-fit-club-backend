"""Neon churn controls: raw retention, cron purge, presence throttle on cdata."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from core.config import settings
from database import Base
from models import DeviceAttendanceLog, PushDevice
from routes.device import receive_attendance_data
from routes.internal import cron_purge_attendance
from services.attendance_service import AttendanceService
from services.push_device_service import PushDeviceService, device_poll_cache


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


@pytest.fixture(autouse=True)
def _clear_poll_cache():
    device_poll_cache.clear_last_seen_stamp("DEV-THROTTLE")
    device_poll_cache.clear_last_seen_stamp("DEV1")
    yield
    device_poll_cache.clear_last_seen_stamp("DEV-THROTTLE")
    device_poll_cache.clear_last_seen_stamp("DEV1")


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


def test_cdata_force_touches_presence_on_upload(db: Session, monkeypatch):
    monkeypatch.setattr(settings, "device_presence_write_interval_seconds", 600)

    first = asyncio.run(_post_cdata(db, sn="DEV-THROTTLE", table="OPERLOG", body=""))
    assert first.body == b"OK"
    device = db.execute(
        select(PushDevice).where(PushDevice.serial_number == "DEV-THROTTLE")
    ).scalar_one()
    first_seen = device.last_seen
    assert first_seen is not None

    # Force-touch on cdata must refresh last_seen even inside the throttle window.
    second = asyncio.run(_post_cdata(db, sn="DEV-THROTTLE", table="OPERLOG", body=""))
    assert second.body == b"OK"
    db.refresh(device)
    assert device.last_seen >= first_seen


def test_purge_uses_shorter_raw_retention(db: Session, monkeypatch):
    monkeypatch.setattr(settings, "attendance_punch_retention_days", 90)
    monkeypatch.setattr(settings, "device_raw_log_retention_days", 14)

    now = datetime.now(timezone.utc)
    old_raw = DeviceAttendanceLog(
        device_serial="DEV1",
        raw_payload="ATTLOG:1\t2026-01-01 08:00:00\t0",
        record_count=1,
        uploaded_at=now - timedelta(days=20),
    )
    recent_raw = DeviceAttendanceLog(
        device_serial="DEV1",
        raw_payload="ATTLOG:1\t2026-01-02 08:00:00\t0",
        record_count=1,
        uploaded_at=now - timedelta(days=2),
    )
    db.add_all([old_raw, recent_raw])
    db.commit()

    result = AttendanceService(db).purge_old_records()
    assert result["raw_logs_deleted"] == 1
    assert result["raw_log_retention_days"] == 14
    assert result["punch_retention_days"] == 90
    remaining = db.execute(select(DeviceAttendanceLog)).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].uploaded_at == recent_raw.uploaded_at


def test_cron_purge_requires_secret(db: Session, monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "")
    with pytest.raises(HTTPException) as missing:
        cron_purge_attendance(db=db, x_cron_secret="anything")
    assert missing.value.status_code == 503

    monkeypatch.setattr(settings, "cron_secret", "test-cron-secret")
    with pytest.raises(HTTPException) as bad:
        cron_purge_attendance(db=db, x_cron_secret="wrong")
    assert bad.value.status_code == 401

    response = cron_purge_attendance(db=db, x_cron_secret="test-cron-secret")
    assert response.punches_deleted == 0
    assert response.raw_log_retention_days == settings.device_raw_log_retention_days


def test_userinfo_is_stored(db: Session):
    service = PushDeviceService(db)
    result = service.log_device_table_upload(
        device_serial="DEV1",
        raw_payload="PIN=1\tName=Test",
        table_name="USERINFO",
    )
    assert result is not None
    assert len(db.execute(select(DeviceAttendanceLog)).scalars().all()) == 1
