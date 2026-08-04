"""
Device Command Queue Model
Manages commands to be sent to ZKTeco PUSH devices.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Enum as SQLEnum
from sqlalchemy.sql import func
from database import Base
import enum


class CommandStatus(str, enum.Enum):
    """Command execution status."""
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class DeviceCommand(Base):
    """
    Command queue for ZKTeco PUSH devices.
    
    Commands are queued in this table and returned to devices when they poll
    the /iclock/getrequest endpoint. The device executes the command and
    acknowledges via /iclock/devicecmd.
    
    Architecture:
    1. Backend creates a command record with status=pending
    2. Device polls GET /iclock/getrequest
    3. Server returns one pending command, marks it executing
    4. Device processes command
    5. Device posts acknowledgment to POST /iclock/devicecmd
    6. Server updates status to completed or failed with response data
    """
    __tablename__ = "device_commands"

    id = Column(Integer, primary_key=True, index=True)
    
    # Command identification
    command_id = Column(String(100), unique=True, nullable=False, index=True)
    device_serial = Column(String(100), nullable=False, index=True)
    
    # Command content (iClock protocol format)
    # Examples:
    # - "C:ID:command_id:DATA UPDATE user pin=123\tusername=John Doe\t..."
    # - "C:ID:command_id:DATA DELETE user pin=123"
    command = Column(Text, nullable=False)
    
    # Execution tracking
    status = Column(SQLEnum(CommandStatus), default=CommandStatus.PENDING, nullable=False, index=True)
    
    # Device response (raw acknowledgment from POST /iclock/devicecmd)
    response = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Retry tracking
    retry_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)

    def __repr__(self):
        return f"<DeviceCommand(id={self.command_id}, device={self.device_serial}, status={self.status})>"
