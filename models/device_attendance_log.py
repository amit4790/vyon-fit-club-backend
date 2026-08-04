"""
Device Attendance Log Model
Stores raw attendance/cdata uploads from ZKTeco PUSH devices.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.sql import func
from database import Base


class DeviceAttendanceLog(Base):
    """
    Raw attendance data uploaded by ZKTeco PUSH devices.
    
    The device posts attendance records to POST /iclock/cdata.
    This model stores the complete raw payload for analysis and parsing.
    
    Architecture:
    - Device uploads attendance data in iClock format
    - Server logs the raw payload without parsing
    - Future parser will extract structured records
    - Preserves original data for debugging and protocol analysis
    
    Example raw format:
    ATTLOG:1\t2024-01-15 09:30:00\t0\t1\t0\t0
    ATTLOG:2\t2024-01-15 12:45:00\t1\t1\t0\t0
    
    Fields in ATTLOG:
    - User PIN
    - Timestamp
    - Status (check-in/check-out)
    - Verify mode
    - Work code
    - Reserved
    """
    __tablename__ = "device_attendance_logs"

    id = Column(Integer, primary_key=True, index=True)
    
    # Device identification
    device_serial = Column(String(100), nullable=False, index=True)
    
    # Raw payload from device
    raw_payload = Column(Text, nullable=False)
    
    # Upload metadata
    content_type = Column(String(100), nullable=True)
    content_length = Column(Integer, nullable=True)
    
    # Processing status
    is_processed = Column(Boolean, default=False, nullable=False, index=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    processing_error = Column(Text, nullable=True)
    
    # Record count (parsed from payload)
    record_count = Column(Integer, nullable=True)
    
    # Timestamps
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<DeviceAttendanceLog(device={self.device_serial}, records={self.record_count}, uploaded={self.uploaded_at})>"
