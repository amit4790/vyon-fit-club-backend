"""GET /iclock/getrequest Neon-sparing behavior."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from core.config import settings
from database import Base
from models import CommandStatus, DeviceCommand, PushDevice
from routes.device import get_device_command
from services.push_device_service import PushDeviceService, device_poll_cache


SN = "TBS2254700504"


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
def _reset_poll_cache():
    device_poll_cache._empty_until.clear()
    device_poll_cache._pending_hint.clear()
    device_poll_cache._last_seen_written_at.clear()
    device_poll_cache._device_metadata.clear()
    yield
    device_poll_cache._empty_until.clear()
    device_poll_cache._pending_hint.clear()
    device_poll_cache._last_seen_written_at.clear()
    device_poll_cache._device_metadata.clear()


def _request(sn: str = SN) -> MagicMock:
    request = MagicMock()
    request.method = "GET"
    request.url = f"http://test/iclock/getrequest?SN={sn}"
    request.query_params = {"SN": sn}
    return request


async def _getrequest(sn: str = SN):
    return await get_device_command(request=_request(sn), SN=sn)


def _seed_device(db: Session, sn: str = SN) -> PushDevice:
    device = PushDevice(serial_number=sn, is_active=True)
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def test_empty_poll_cache_skips_session_within_window(db: Session, monkeypatch):
    monkeypatch.setattr(settings, "device_empty_poll_skip_seconds", 10)
    monkeypatch.setattr(settings, "device_presence_write_interval_seconds", 120)

    session_factory = sessionmaker(bind=db.get_bind())

    with patch("routes.device.SessionLocal", session_factory):
        first = asyncio.run(_getrequest())
        assert first.body == b"OK"
        assert device_poll_cache.should_skip_empty_poll_db(SN)

        session_calls = {"n": 0}
        real_factory = session_factory

        def counting_factory():
            session_calls["n"] += 1
            return real_factory()

        with patch("routes.device.SessionLocal", counting_factory):
            second = asyncio.run(_getrequest())
            assert second.body == b"OK"
            assert session_calls["n"] == 0


def test_last_seen_not_updated_on_every_poll(db: Session, monkeypatch):
    monkeypatch.setattr(settings, "device_empty_poll_skip_seconds", 0)
    monkeypatch.setattr(settings, "device_presence_write_interval_seconds", 120)

    device = _seed_device(db)
    # Stamp presence throttle as if last_seen was just written.
    device_poll_cache.note_device_persisted(SN, {})

    before = device.last_seen
    session_factory = sessionmaker(bind=db.get_bind())
    with patch("routes.device.SessionLocal", session_factory):
        response = asyncio.run(_getrequest())
    assert response.body == b"OK"

    db.refresh(device)
    assert device.last_seen == before


def test_last_seen_updates_after_presence_interval(db: Session, monkeypatch):
    monkeypatch.setattr(settings, "device_empty_poll_skip_seconds", 0)
    monkeypatch.setattr(settings, "device_presence_write_interval_seconds", 120)

    device = _seed_device(db)
    device_poll_cache.note_device_persisted(SN, {})
    # Expire the 120s presence window.
    device_poll_cache._last_seen_written_at[SN] = (
        device_poll_cache._now() - timedelta(seconds=121)
    )
    before = device.last_seen

    session_factory = sessionmaker(bind=db.get_bind())
    with patch("routes.device.SessionLocal", session_factory):
        response = asyncio.run(_getrequest())
    assert response.body == b"OK"

    db.refresh(device)
    assert device.last_seen is not None
    assert before is None or device.last_seen >= before
    assert not device_poll_cache.needs_last_seen_write(SN, interval_seconds=120)


def test_pending_command_is_delivered(db: Session, monkeypatch):
    monkeypatch.setattr(settings, "device_empty_poll_skip_seconds", 10)
    device = _seed_device(db)
    db.add(
        DeviceCommand(
            command_id="cmd-deliver-1",
            device_serial=SN,
            command="C:1:DATA UPDATE USERINFO PIN=99901\tName=Amit\tPri=14\tPasswd=9999",
            status=CommandStatus.PENDING,
        )
    )
    db.commit()

    session_factory = sessionmaker(bind=db.get_bind())
    with patch("routes.device.SessionLocal", session_factory):
        response = asyncio.run(_getrequest())

    assert response.body.startswith(b"C:1:DATA UPDATE USERINFO")
    cmd = db.execute(
        select(DeviceCommand).where(DeviceCommand.command_id == "cmd-deliver-1")
    ).scalar_one()
    assert cmd.status == CommandStatus.EXECUTING
    assert cmd.executed_at is not None
    assert device.id is not None


def test_empty_poll_cache_cleared_when_command_queued(db: Session, monkeypatch):
    monkeypatch.setattr(settings, "device_empty_poll_skip_seconds", 10)
    monkeypatch.setattr(settings, "device_presence_write_interval_seconds", 120)

    _seed_device(db)
    session_factory = sessionmaker(bind=db.get_bind())

    with patch("routes.device.SessionLocal", session_factory):
        empty = asyncio.run(_getrequest())
        assert empty.body == b"OK"
        assert device_poll_cache.should_skip_empty_poll_db(SN)

        # Same-process queue invalidates empty-poll skip.
        service = PushDeviceService(db)
        service.queue_command(
            device_serial=SN,
            command_id="cmd-after-empty",
            command="C:99:DATA UPDATE USERINFO PIN=1\tName=Test\tPri=0\tPasswd=",
        )
        assert not device_poll_cache.should_skip_empty_poll_db(SN)

        response = asyncio.run(_getrequest())
        assert b"C:99:DATA UPDATE USERINFO" in response.body


def test_stale_executing_command_is_reclaimed(db: Session, monkeypatch):
    monkeypatch.setattr(settings, "device_empty_poll_skip_seconds", 0)
    _seed_device(db)
    stale_at = datetime.now(timezone.utc) - timedelta(minutes=3)
    db.add(
        DeviceCommand(
            command_id="cmd-stale-1",
            device_serial=SN,
            command="C:7:DATA UPDATE USERINFO PIN=2\tName=Reclaim\tPri=0\tPasswd=",
            status=CommandStatus.EXECUTING,
            executed_at=stale_at,
        )
    )
    db.commit()

    session_factory = sessionmaker(bind=db.get_bind())
    with patch("routes.device.SessionLocal", session_factory):
        response = asyncio.run(_getrequest())

    assert b"C:7:DATA UPDATE USERINFO" in response.body
    cmd = db.execute(
        select(DeviceCommand).where(DeviceCommand.command_id == "cmd-stale-1")
    ).scalar_one()
    assert cmd.status == CommandStatus.EXECUTING
    assert cmd.executed_at is not None
    assert cmd.executed_at > stale_at.replace(tzinfo=None) or (
        cmd.executed_at.tzinfo is not None and cmd.executed_at > stale_at
    )
