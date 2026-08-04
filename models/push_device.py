"""
ZKTeco PUSH Device Model
Tracks registered devices communicating via the iClock/ADMS PUSH protocol.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.sql import func
from database import Base


class PushDevice(Base):
    """
    ZKTeco device registered via PUSH protocol.
    
    The device initiates communication with the server using HTTP requests.
    This model tracks device identity, connection state, and metadata.
    """
    __tablename__ = "push_devices"

    id = Column(Integer, primary_key=True, index=True)
    serial_number = Column(String(100), unique=True, nullable=False, index=True)
    device_name = Column(String(200), nullable=True)
    
    # Device metadata (extracted from initial registration)
    platform = Column(String(100), nullable=True)  # e.g., "ZAM230_TFT"
    firmware_version = Column(String(100), nullable=True)  # e.g., "Ver1.0.27"
    device_type = Column(String(50), nullable=True)  # e.g., "T&A PUSH"
    
    # Connection tracking
    first_seen = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Raw registration data for diagnostics
    registration_payload = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<PushDevice(serial={self.serial_number}, last_seen={self.last_seen})>"
