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
        """Log raw ATTLOG upload. Prefer log_device_table_upload for multi-table support."""
        return self.log_device_table_upload(
            device_serial=device_serial,
            raw_payload=raw_payload,
            table_name="ATTLOG",
            content_type=content_type,
            content_length=content_length,
        )

    def log_device_table_upload(
        self,
        device_serial: str,
        raw_payload: str,
        table_name: Optional[str] = None,
        content_type: Optional[str] = None,
        content_length: Optional[int] = None
    ) -> DeviceAttendanceLog:
        """
        Log raw device table upload (ATTLOG, USERINFO, BIODATA, OPERLOG, ...).

        Called when device posts to POST /iclock/cdata.
        Stores complete raw payload for analysis and future parsing.
        """
        normalized_table = (table_name or "").strip().upper()
        record_count = self._count_table_records(raw_payload, normalized_table)

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

        log_message = (
            f"Device table uploaded: table={normalized_table or 'UNKNOWN'} "
            f"records={record_count} from device {device_serial}"
        )
        log_extra = {
            "device_serial": device_serial,
            "table": normalized_table or None,
            "record_count": record_count,
            "payload_size": len(raw_payload),
        }
        if settings.device_push_log_raw:
            log_extra["raw_payload"] = raw_payload

        logger.info(log_message, extra=log_extra)
        return attendance_log

    @staticmethod
    def _count_table_records(raw_payload: str, table_name: str) -> int:
        """Best-effort record count for known ADMS table payloads."""
        if not raw_payload.strip():
            return 0

        if table_name == "ATTLOG":
            return raw_payload.count("\nATTLOG:") + (1 if raw_payload.startswith("ATTLOG:") else 0)

        if table_name == "USERINFO":
            # USERINFO rows are typically newline-separated; count non-empty lines.
            return sum(1 for line in raw_payload.splitlines() if line.strip())

        if table_name in {"BIODATA", "OPERLOG"}:
            prefix = f"{table_name}:"
            return raw_payload.count(f"\n{prefix}") + (1 if raw_payload.startswith(prefix) else 0)

        return sum(1 for line in raw_payload.splitlines() if line.strip())

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
        Queue user add/update commands for all active PUSH devices.
        
        Called when a member is created or updated in VYON.
        Device PIN is the VYON member.id.
        """
        devices = self.db.query(PushDevice).filter(
            PushDevice.is_active == True
        ).all()
        
        if not devices:
            logger.warning(
                "No active PUSH devices found for member sync",
                extra={"member_id": member_id}
            )
            return []
        
        commands = []
        for index, device in enumerate(devices):
            command_id = self._next_command_id(member_id=member_id, salt=index)
            command_str = UserSyncCommand.build_update_user_command(
                command_id=command_id,
                pin=str(member_id),
                username=member_name,
                privilege=0,
                password="",
                card=card_number or "",
            )
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
                    "command_id": command_id,
                },
            )
        
        return commands

    def remove_member_from_devices(self, member_id: int) -> List[DeviceCommand]:
        """
        Queue user delete commands for all active PUSH devices.
        
        Called when a member is deleted in VYON.
        Device PIN is the VYON member.id.
        """
        devices = self.db.query(PushDevice).filter(
            PushDevice.is_active == True
        ).all()

        if not devices:
            logger.warning(
                "No active PUSH devices found for member delete sync",
                extra={"member_id": member_id},
            )
            return []

        commands = []
        for index, device in enumerate(devices):
            command_id = self._next_command_id(member_id=member_id, salt=index + 500)
            command_str = UserSyncCommand.build_delete_user_command(
                command_id=command_id,
                pin=str(member_id),
            )
            device_command = self.queue_command(
                device_serial=device.serial_number,
                command_id=str(command_id),
                command=command_str,
                max_retries=3,
            )
            commands.append(device_command)
            logger.info(
                f"Queued user delete command for member {member_id} to device {device.serial_number}",
                extra={
                    "member_id": member_id,
                    "device_serial": device.serial_number,
                    "command_id": command_id,
                },
            )

        return commands

    def resync_all_members_to_device(self, device_sn: str) -> dict[str, Any]:
        """
        Bulk re-sync all active members to a specific PUSH device.

        Queues DATA UPDATE USERINFO for each member (and BIOPHOTO when available),
        sequentially with status=PENDING.
        """
        from models import Member

        device = self.get_device(device_sn)
        if not device or not device.is_active:
            raise DeviceNotRegisteredError(f"Device not found or inactive: {device_sn}")

        members = (
            self.db.query(Member)
            .filter(
                Member.deleted_at.is_(None),
                Member.status == "active",
            )
            .order_by(Member.id.asc())
            .all()
        )

        queued: List[DeviceCommand] = []
        for index, member in enumerate(members):
            queued.extend(
                self._queue_member_sync_commands(
                    member=member,
                    device_serial=device.serial_number,
                    salt_base=index * 10,
                )
            )

        logger.info(
            "Bulk device re-sync queued",
            extra={
                "device_serial": device_sn,
                "member_count": len(members),
                "queued_commands": len(queued),
            },
        )
        return {
            "status": "success",
            "device_sn": device_sn,
            "members_synced": len(members),
            "queued_commands": len(queued),
        }

    def sync_single_member_to_device(self, user_id: int, device_sn: str) -> dict[str, Any]:
        """
        Queue USERINFO (and BIOPHOTO if present) for one member to one device.
        `user_id` is the VYON member.id used as device PIN.
        """
        from models import Member

        device = self.get_device(device_sn)
        if not device or not device.is_active:
            raise DeviceNotRegisteredError(f"Device not found or inactive: {device_sn}")

        member = (
            self.db.query(Member)
            .filter(
                Member.id == user_id,
                Member.deleted_at.is_(None),
            )
            .first()
        )
        if not member:
            raise MemberSyncNotFoundError(f"Member not found: {user_id}")

        queued = self._queue_member_sync_commands(
            member=member,
            device_serial=device.serial_number,
            salt_base=user_id,
        )

        logger.info(
            "Single member device sync queued",
            extra={
                "device_serial": device_sn,
                "member_id": user_id,
                "queued_commands": len(queued),
            },
        )
        return {
            "status": "success",
            "device_sn": device_sn,
            "user_id": user_id,
            "queued_commands": len(queued),
        }

    def _queue_member_sync_commands(
        self,
        *,
        member: Any,
        device_serial: str,
        salt_base: int,
    ) -> List[DeviceCommand]:
        """Queue USERINFO then optional BIOPHOTO for one member, in order."""
        commands: List[DeviceCommand] = []
        passwd = str(getattr(member, "pin", None) or "")
        member_name = getattr(member, "full_name", None) or getattr(member, "name", "") or ""

        userinfo_cmd_id = self._next_command_id(member_id=member.id, salt=salt_base)
        userinfo_command = UserSyncCommand.build_update_userinfo_command(
            command_id=userinfo_cmd_id,
            pin=str(member.id),
            name=member_name,
            privilege=0,
            password=passwd,
        )
        commands.append(
            self.queue_command(
                device_serial=device_serial,
                command_id=str(userinfo_cmd_id),
                command=userinfo_command,
                max_retries=3,
            )
        )

        biophoto_content = (
            getattr(member, "biophoto_content", None)
            or getattr(member, "biophoto_template", None)
            or getattr(member, "face_template", None)
        )
        biophoto_type = getattr(member, "biophoto_type", None)
        if biophoto_content:
            biophoto_cmd_id = self._next_command_id(member_id=member.id, salt=salt_base + 1)
            biophoto_command = UserSyncCommand.build_update_biophoto_command(
                command_id=biophoto_cmd_id,
                pin=str(member.id),
                content=str(biophoto_content),
                photo_type=int(biophoto_type) if biophoto_type is not None else 9,
            )
            commands.append(
                self.queue_command(
                    device_serial=device_serial,
                    command_id=str(biophoto_cmd_id),
                    command=biophoto_command,
                    max_retries=3,
                )
            )

        return commands

    @staticmethod
    def _next_command_id(*, member_id: int, salt: int = 0) -> int:
        """Generate a unique integer command ID within 32-bit signed range."""
        base = int(datetime.utcnow().timestamp() * 1000) % 2000000000
        return (base + (member_id * 17) + salt) % 2147483647 or 1


class DeviceNotRegisteredError(Exception):
    """Raised when a PUSH device serial is missing or inactive."""


class MemberSyncNotFoundError(Exception):
    """Raised when a member cannot be synced because it does not exist."""


# User synchronization
class UserSyncCommand:
    """
    User synchronization command builders for ZKTeco PUSH / ADMS protocol.
    
    Formats:
    C:<id>:DATA USER PIN=31\tName=Jasleen Kaur\tPri=0\tGroup=1
    C:<id>:DATA UPDATE USERINFO PIN=31\tName=Jasleen Kaur\tPri=0\tPasswd=
    C:<id>:DATA DELETE USERINFO PIN=31
    C:<id>:DATA UPDATE BIOPHOTO PIN=31\tType=9\tSize=...\tContent=...
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
        Build DATA USER command for adding/updating user on device.
        
        PIN on device = VYON member.id
        """
        fields = [
            f"PIN={pin}",
            f"Name={username}",
            f"Pri={privilege}",
            f"Group={group}",
        ]
        if password:
            fields.append(f"Passwd={password}")
        if card:
            fields.append(f"Card={card}")

        return f"C:{command_id}:DATA USER {chr(9).join(fields)}"

    @staticmethod
    def build_update_userinfo_command(
        command_id: int,
        pin: str,
        name: str,
        privilege: int = 0,
        password: str = "",
    ) -> str:
        """Build DATA UPDATE USERINFO command used by bulk/single device re-sync."""
        fields = [
            f"PIN={pin}",
            f"Name={name}",
            f"Pri={privilege}",
            f"Passwd={password or ''}",
        ]
        return f"C:{command_id}:DATA UPDATE USERINFO {chr(9).join(fields)}"

    @staticmethod
    def build_update_biophoto_command(
        command_id: int,
        pin: str,
        content: str,
        photo_type: int = 9,
    ) -> str:
        """Build DATA UPDATE BIOPHOTO command when face/photo template is available."""
        size = len(content)
        fields = [
            f"PIN={pin}",
            f"Type={photo_type}",
            f"Size={size}",
            f"Content={content}",
        ]
        return f"C:{command_id}:DATA UPDATE BIOPHOTO {chr(9).join(fields)}"

    @staticmethod
    def build_delete_user_command(command_id: int, pin: str) -> str:
        """Build DATA DELETE USERINFO command for removing user from device."""
        return f"C:{command_id}:DATA DELETE USERINFO PIN={pin}"
