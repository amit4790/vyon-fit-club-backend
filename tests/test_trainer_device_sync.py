"""Trainer bulk device sync resilience."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from core.config import settings
from core.roles import UserRole
from database import Base
from models import DeviceCommand, PushDevice, User
from services.push_device_service import PushDeviceService
from services.trainer_service import TrainerService


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


def _add_trainer(db: Session) -> User:
    trainer = User(
        full_name="Nishant Pawar",
        email="trainer-sync@test.local",
        phone_number="9000000001",
        role=UserRole.TRAINER,
        is_active=True,
        password_hash="x",
    )
    db.add(trainer)
    db.commit()
    db.refresh(trainer)
    return trainer


def test_exclude_serials_skips_placeholder_devices(db: Session, monkeypatch):
    monkeypatch.setattr(settings, "device_push_exclude_serials", "TEST,TESTPROBE")
    db.add(PushDevice(serial_number="TBS2254700504", is_active=True))
    db.add(PushDevice(serial_number="TEST", is_active=True))
    db.commit()

    service = PushDeviceService(db)
    assert service._active_device_serials() == ["TBS2254700504"]


def test_sync_trainer_continues_when_one_device_fails(db: Session):
    db.add(PushDevice(serial_number="TBS2254700504", is_active=True))
    db.add(PushDevice(serial_number="BAD-DEVICE", is_active=True))
    db.commit()
    _add_trainer(db)

    service = PushDeviceService(db)
    original_queue = service.queue_command

    def flaky_queue(*, device_serial: str, **kwargs):
        if device_serial == "BAD-DEVICE":
            raise RuntimeError("simulated queue failure")
        return original_queue(device_serial=device_serial, **kwargs)

    with patch.object(service, "queue_command", side_effect=flaky_queue):
        commands, failures = service.sync_trainer_to_devices(1, "Nishant Pawar")

    assert len(commands) == 1
    assert failures == 1
    assert commands[0].device_serial == "TBS2254700504"


def test_sync_all_trainers_returns_partial_success(db: Session, monkeypatch):
    monkeypatch.setattr(settings, "device_push_enabled", True)
    db.add(PushDevice(serial_number="TBS2254700504", is_active=True))
    db.commit()
    _add_trainer(db)

    result = TrainerService(db).sync_all_active_trainers_to_devices()
    assert result["trainers_queued"] == 1
    assert result["commands_queued"] >= 1
    assert result["trainers_failed"] == 0
    rows = db.execute(select(DeviceCommand)).scalars().all()
    assert rows
