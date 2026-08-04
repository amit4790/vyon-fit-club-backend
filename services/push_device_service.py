"""
ZKTeco PUSH Protocol Device Service

Implements the official ZKTeco iClock/ADMS PUSH protocol.

Architecture Overview:
- The device initiates all communication via HTTP requests
- Device polls for commands using GET /iclock/getrequest
- Device uploads attendance data via POST /iclock/cdata
- Device acknowledges commands via POST /iclock/devicecmd
- Server maintains command queue and device registration

Protocol Documentation:
- PUSH protocol uses standard HTTP with specific endpoint conventions
- Device identifies itself via SN parameter (serial number)
- Commands use iClock protocol format (e.g., "C:ID:cmd_id:DATA UPDATE user...")
- Attendance uses ATTLOG format with tab-separated fields

Reference: ZKTeco PUSH SDK / iClock Protocol Specification
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import desc

from models import PushDevice, DeviceCommand, CommandStatus, DeviceAttendanceLog
from core.config import settings

logger = logging.getLogger(__name__)


class PushDeviceService:
    """Service for managing ZKTeco PUSH protocol devices."""

    def __init__(self, db: Session):
        self.db = db

    def register_or_update_device(
        self,
        serial_number: str,
        device_info: Optional[Dict[str, Any]] = None
    ) -> PushDevice:
        """
        Register a new device or update existing device's last_seen timestamp.

        Called when device makes any request to the server.

        Args:
            serial_number: Device serial number (from SN parameter)
            device_info: Optional metadata from device (platform, firmware, etc.)

        Returns:
            PushDevice instance
        """
        device = self.db.query(PushDevice).filter(
            PushDevice.serial_number == serial_number
        ).first()

        if device:
            # Update last_seen for existing device
            device.last_seen = datetime.utcnow()
            
            # Update metadata if provided
            if device_info:
                if 'platform' in device_info:
                    device.platform = device_info['platform']
                if 'firmware_version' in device_info:
                    device.firmware_version = device_info['firmware_version']
                if 'device_type' in device_info:
                    device.device_type = device_info['device_type']
                if 'device_name' in device_info:
                    device.device_name = device_info['device_name']
            
            logger.info(
                f"Device heartbeat: {serial_number}",
                extra={
                    "device_serial": serial_number,
                    "last_seen": device.last_seen.isoformat()
                }
            )
        else:
            # Register new device
            device = PushDevice(
                serial_number=serial_number,
                device_name=device_info.get('device_name') if device_info else None,
                platform=device_info.get('platform') if device_info else None,
                firmware_version=device_info.get('firmware_version') if device_info else None,
                device_type=device_info.get('device_type') if device_info else None,
                registration_payload=str(device_info) if device_info else None,
            )
            self.db.add(device)
            
            logger.info(
                f"Device registered: {serial_number}",
                extra={
                    "device_serial": serial_number,
                    "device_info": device_info
                }
            )

        self.db.commit()
        self.db.refresh(device)
        return device

    def get_pending_command(self, device_serial: str) -> Optional[DeviceCommand]:
        """
        Retrieve the next pending command for the device.

        Called when device polls GET /iclock/getrequest.

        Args:
            device_serial: Device serial number

        Returns:
            Next pending DeviceCommand or None if queue is empty
        """
        command = self.db.query(DeviceCommand).filter(
            DeviceCommand.device_serial == device_serial,
            DeviceCommand.status == CommandStatus.PENDING
        ).order_by(DeviceCommand.created_at).first()

        if command:
            # Mark as executing
            command.status = CommandStatus.EXECUTING
            command.executed_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(command)
            
            logger.info(
                f"Command dispatched: {command.command_id} to device {device_serial}",
                extra={
                    "device_serial": device_serial,
                    "command_id": command.command_id,
                    "command": command.command
                }
            )

        return command

    def acknowledge_command(
        self,
        command_id: str,
        device_serial: str,
        response_data: str,
        success: bool
    ) -> Optional[DeviceCommand]:
        """
        Process command acknowledgment from device.

        Called when device posts to POST /iclock/devicecmd.

        Args:
            command_id: Command identifier
            device_serial: Device serial number
            response_data: Raw response from device
            success: Whether command executed successfully

        Returns:
            Updated DeviceCommand or None if not found
        """
        command = self.db.query(DeviceCommand).filter(
            DeviceCommand.command_id == command_id,
            DeviceCommand.device_serial == device_serial
        ).first()

        if not command:
            logger.warning(
                f"Command acknowledgment for unknown command: {command_id}",
                extra={
                    "command_id": command_id,
                    "device_serial": device_serial
                }
            )
            return None

        command.response = response_data
        command.status = CommandStatus.COMPLETED if success else CommandStatus.FAILED
        command.completed_at = datetime.utcnow()
        
        if not success:
            command.error_message = response_data

        self.db.commit()
        self.db.refresh(command)

        logger.info(
            f"Command acknowledged: {command_id} - {'SUCCESS' if success else 'FAILED'}",
            extra={
                "device_serial": device_serial,
                "command_id": command_id,
                "status": command.status.value,
                "response": response_data
            }
        )

        return command

    def queue_command(
        self,
        device_serial: str,
        command_id: str,
        command: str,
        max_retries: int = 3
    ) -> DeviceCommand:
        """
        Queue a new command for the device.

        Args:
            device_serial: Target device serial number
            command_id: Unique command identifier
            command: Command string in iClock format
            max_retries: Maximum retry attempts

        Returns:
            Created DeviceCommand instance
        """
        device_command = DeviceCommand(
            command_id=command_id,
            device_serial=device_serial,
            command=command,
            status=CommandStatus.PENDING,
            max_retries=max_retries
        )
        self.db.add(device_command)
        self.db.commit()
        self.db.refresh(device_command)

        logger.info(
            f"Command queued: {command_id} for device {device_serial}",
            extra={
                "device_serial": device_serial,
                "command_id": command_id,
                "command": command
            }
        )

        return device_command

    def log_attendance_upload(
        self,
        device_serial: str,
        raw_payload: str,
        content_type: Optional[str] = None,
        content_length: Optional[int] = None
    ) -> DeviceAttendanceLog:
        """
        Log raw attendance data upload from device.

        Called when device posts to POST /iclock/cdata.
        Stores complete raw payload for future parsing.

        Args:
            device_serial: Device serial number
            raw_payload: Complete raw attendance data
            content_type: HTTP Content-Type header
            content_length: HTTP Content-Length header

        Returns:
            Created DeviceAttendanceLog instance
        """
        # Count records in payload (lines starting with ATTLOG)
        record_count = raw_payload.count('\nATTLOG:') + (1 if raw_payload.startswith('ATTLOG:') else 0)

        attendance_log = DeviceAttendanceLog(
            device_serial=device_serial,
            raw_payload=raw_payload,
            content_type=content_type,
            content_length=content_length,
            record_count=record_count
        )
        self.db.add(attendance_log)
        self.db.commit()
        self.db.refresh(attendance_log)

        if settings.device_push_log_raw:
            logger.info(
                f"Attendance uploaded: {record_count} records from device {device_serial}",
                extra={
                    "device_serial": device_serial,
                    "record_count": record_count,
                    "payload_size": len(raw_payload),
                    "raw_payload": raw_payload  # Log full payload when enabled
                }
            )
        else:
            logger.info(
                f"Attendance uploaded: {record_count} records from device {device_serial}",
                extra={
                    "device_serial": device_serial,
                    "record_count": record_count,
                    "payload_size": len(raw_payload)
                }
            )

        return attendance_log

    def get_device(self, serial_number: str) -> Optional[PushDevice]:
        """Get device by serial number."""
        return self.db.query(PushDevice).filter(
            PushDevice.serial_number == serial_number
        ).first()

    def get_all_devices(self) -> List[PushDevice]:
        """Get all registered devices."""
        return self.db.query(PushDevice).order_by(desc(PushDevice.last_seen)).all()

    def get_device_commands(
        self,
        device_serial: str,
        status: Optional[CommandStatus] = None,
        limit: int = 50
    ) -> List[DeviceCommand]:
        """Get commands for a device, optionally filtered by status."""
        query = self.db.query(DeviceCommand).filter(
            DeviceCommand.device_serial == device_serial
        )
        
        if status:
            query = query.filter(DeviceCommand.status == status)
        
        return query.order_by(desc(DeviceCommand.created_at)).limit(limit).all()

    def get_unprocessed_attendance(self, limit: int = 100) -> List[DeviceAttendanceLog]:
        """Get unprocessed attendance logs for parsing."""
        return self.db.query(DeviceAttendanceLog).filter(
            DeviceAttendanceLog.is_processed == False
        ).order_by(DeviceAttendanceLog.uploaded_at).limit(limit).all()

    def sync_member_to_devices(
        self,
        member_id: int,
        member_name: str,
        card_number: Optional[str] = None
    ) -> List[DeviceCommand]:
        """
        Queue user synchronization commands for all active PUSH devices.
        
        Called when a member is created or updated in VYON.
        Creates a DeviceCommand for each active device to add/update the user.
        
        Args:
            member_id: VYON member ID (used as device PIN)
            member_name: Member's full name (displayed on device)
            card_number: Optional card number for card-based access
            
        Returns:
            List of queued DeviceCommand instances
        """
        # Get all active devices
        devices = self.db.query(PushDevice).filter(
            PushDevice.is_active == True
        ).all()
        
        if not devices:
            logger.warning(
                f"No active PUSH devices found for member sync",
                extra={"member_id": member_id}
            )
            return []
        
        # Queue command for each device
        commands = []
        for device in devices:
            # Generate unique INTEGER command ID (required by PUSH protocol)
            # Use timestamp + member_id to ensure uniqueness
            command_id = int(datetime.utcnow().timestamp() * 1000) % 2147483647  # Keep within 32-bit int
            
            # Build iClock command
            command_str = UserSyncCommand.build_update_user_command(
                command_id=command_id,
                pin=str(member_id),
                username=member_name,
                privilege=0,
                password="",
                card=card_number or ""
            )
            
            # Queue command (store as string for database)
            device_command = self.queue_command(
                device_serial=device.serial_number,
                command_id=str(command_id),
                command=command_str,
                max_retries=3
            )
            commands.append(device_command)
            
            logger.info(
                f"Queued user sync command for member {member_id} to device {device.serial_number}",
                extra={
                    "member_id": member_id,
                    "device_serial": device.serial_number,
                    "command_id": command_id
                }
            )
        
        return commands


# User synchronization
class UserSyncCommand:
    """
    User synchronization command builders for ZKTeco PUSH protocol.
    
    Supports:
    - DATA user: Add or update user on device (no UPDATE keyword)
    - DATA DELETE user: Remove user from device
    
    ACTUAL Command format for MiniAC Plus / ZAM230 (verified by device testing):
    C:<integer_id>:DATA user pin=123\tname=John Doe\tpri=0\tpasswd=\tcard=\tgrp=1
    
    CRITICAL FINDINGS:
    - Command ID must be an integer
    - No "UPDATE" keyword after DATA (device expects: "DATA user" not "DATA UPDATE user")
    - Table name is lowercase "user" (not "USERINFO")
    - Field names are lowercase: pin, name, pri, passwd, card, grp
    - Fields are tab-separated
    - grp (group) field may be required (default: 1)
    
    Tab-separated fields:
    - pin: User ID on device (required)
    - name: Display name (required)
    - pri: Privilege level (0=normal user, 14=admin)
    - passwd: User password (optional, usually blank)
    - card: Card number (optional)
    - grp: Group number (default: 1)
    
    Reference: Verified with actual MiniAC Plus device behavior
    """

    @staticmethod
    def build_update_user_command(
        command_id: int,
        pin: str,
        username: str,
        privilege: int = 0,
        password: str = "",
        card: str = "",
        group: int = 1
    ) -> str:
        """
        Build DATA user command for adding/updating user on device.
        
        Args:
            command_id: Unique command identifier (must be integer)
            pin: User PIN (numeric ID on device)
            username: User display name
            privilege: User privilege level (0=user, 14=admin)
            password: User password (optional, blank for normal users)
            card: Card number (optional)
            group: User group number (default: 1)

        Returns:
            Command string in actual iClock protocol format
            
        Example:
            build_update_user_command(295, "456", "John Doe", 0, "", "12345")
            Returns: "C:295:DATA user pin=456\tname=John Doe\tpri=0\tpasswd=\tcard=12345\tgrp=1"
        """
        # Build tab-separated field list (lowercase field names as expected by MiniAC Plus)
        fields = [
            f"pin={pin}",
            f"name={username}",
            f"pri={privilege}",
            f"passwd={password}",
            f"card={card}",
            f"grp={group}"
        ]
        
        # Join with tabs and construct full command
        # Format: C:<id>:DATA user <tab-separated-fields>
        # Note: No "UPDATE" keyword - device expects "DATA user" directly
        command = f"C:{command_id}:DATA user {chr(9).join(fields)}"
        return command

    @staticmethod
    def build_delete_user_command(command_id: int, pin: str) -> str:
        """
        Build DATA DELETE user command for removing user from device.
        
        Args:
            command_id: Unique command identifier (must be integer)
            pin: User PIN to delete

        Returns:
            Command string in iClock format
        """
        return f"C:{command_id}:DATA DELETE user pin={pin}"
