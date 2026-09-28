"""Regression: device_commands.command_id must not collide on re-sync."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import CommandStatus, DeviceCommand, PushDevice
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


def test_next_command_id_avoids_existing_row(db: Session, monkeypatch):
    db.add(
        DeviceCommand(
            command_id="602399355",
            device_serial="TBS2254700504",
            command="C:602399355:DATA UPDATE USERINFO PIN=50001\tName=Old\tPri=0\tPasswd=",
            status=CommandStatus.COMPLETED,
        )
    )
    db.commit()

    service = PushDeviceService(db)
    # Force the generator to keep proposing the colliding id, then a free one.
    values = iter([602399355, 602399355, 991122334])
    monkeypatch.setattr(
        PushDeviceService,
        "_generate_command_id",
        staticmethod(lambda **_kwargs: next(values)),
    )

    allocated = service._next_command_id(member_id=50001, salt=700)
    assert allocated == 991122334


def test_sync_trainer_twice_does_not_raise_unique_violation(db: Session):
    db.add(PushDevice(serial_number="TBS2254700504", is_active=True))
    db.commit()

    service = PushDeviceService(db)
    first = service.sync_trainer_to_devices(trainer_id=1, trainer_name="Nishant Pawar")
    second = service.sync_trainer_to_devices(trainer_id=1, trainer_name="Nishant Pawar")

    assert first
    assert second
    ids = {cmd.command_id for cmd in first + second}
    assert len(ids) == len(first) + len(second)
