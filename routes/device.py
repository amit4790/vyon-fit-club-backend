"""
ZKTeco PUSH Protocol Device Routes

Implements iClock/ADMS protocol endpoints for device communication.

Protocol Overview:
- Device initiates all communication via HTTP
- GET /iclock/cdata: Device info/heartbeat
- GET /iclock/getrequest: Command polling by device
- POST /iclock/devicecmd: Command acknowledgment from device
- POST /iclock/cdata: Attendance data upload

Command Format (verified with MiniAC Plus / ZAM230):
- C:<integer_id>:<COMMAND_TYPE> <tab-separated-data>
- Example: C:295:DATA user pin=123\tname=John Doe\tpri=0\tpasswd=\tcard=\tgrp=1
- Note: No "UPDATE" keyword for user commands

Acknowledgment Format:
- ID=<id>&Return=<code>&CMD=<command>
- Return=0 means success, non-zero means error
- Common errors: -1 (unknown syntax), -1002 (invalid format), -1003 (parameter error)

Reference: Verified with actual device testing
"""

from datetime import datetime
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, Body, status as http_status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import require_admin_access, require_super_admin
from models import CommandStatus, DeviceCommand
from services.push_device_service import (
    DeviceNotRegisteredError,
    MemberSyncNotFoundError,
    PushDeviceService,
)
from core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/iclock", tags=["Device PUSH Protocol"])


@router.get("/cdata")
async def device_heartbeat(
    request: Request,
    SN: str = Query(..., description="Device serial number"),
    db: Session = Depends(get_db)
):
    """
    Device heartbeat and information endpoint.
    
    The device periodically calls this endpoint to:
    - Register itself with the server
    - Provide device information
    - Check server availability
    
    Query Parameters:
    - SN: Device serial number (required)
    - options: Device options/capabilities (optional)
    - pushver: PUSH protocol version (optional)
    - language: Device language (optional)
    
    Response:
    - "OK" to acknowledge heartbeat
    - Additional server commands/config can be returned (future)
    
    Example Request:
    GET /iclock/cdata?SN=ZAM230001234&options=...&pushver=2.0
    
    Example Response:
    OK
    """
    service = PushDeviceService(db)
    
    # Extract device info from query parameters
    query_params = dict(request.query_params)
    device_info = {
        'options': query_params.get('options'),
        'pushver': query_params.get('pushver'),
        'language': query_params.get('language'),
        'platform': query_params.get('platform'),
        'firmware_version': query_params.get('FWVersion'),
        'device_type': query_params.get('DeviceType'),
        'device_name': query_params.get('DeviceName'),
    }
    
    # Remove None values
    device_info = {k: v for k, v in device_info.items() if v is not None}
    
    # Register or update device
    device = service.register_or_update_device(SN, device_info)
    
    logger.info(
        f"Device heartbeat: {SN}",
        extra={
            "device_serial": SN,
            "device_info": device_info,
            "endpoint": "GET /iclock/cdata"
        }
    )
    
    # Return OK to acknowledge heartbeat
    # Future: Could return server time, configuration, etc.
    return Response(content="OK", media_type="text/plain")


@router.get("/getrequest")
async def get_device_command(
    request: Request,
    SN: str = Query(..., description="Device serial number"),
    db: Session = Depends(get_db)
):
    """
    Command polling endpoint.
    
    The device periodically polls this endpoint to check for pending commands.
    Server returns one command at a time, marking it as executing.
    
    Query Parameters:
    - SN: Device serial number (required)
    
    Response:
    - "OK" if no commands pending
    - Command string in iClock format if command exists
    
    Command Format:
    C:<id>:<COMMAND_TYPE> <command_data>
    
    Examples:
    C:295:DATA user pin=123\tname=John Doe\tpri=0\tpasswd=\tcard=\tgrp=1
    C:296:DATA DELETE user pin=456
    
    Example Request:
    GET /iclock/getrequest?SN=ZAM230001234
    
    Example Response (no commands):
    OK
    
    Example Response (command pending):
    C:295:DATA user pin=123\tname=John Doe\tpri=0\tpasswd=\tcard=\tgrp=1
    """
    service = PushDeviceService(db)
    
    # Update device last_seen
    service.register_or_update_device(SN)

    # Get next pending command from the durable queue
    command = service.get_pending_command(SN)
    
    if command:
        # Log the exact command string being sent to device
        logger.info(
            f"Command dispatched to device {SN}\n"
            f"  Command ID: {command.command_id}\n"
            f"  Command String: {command.command}",
            extra={
                "device_serial": SN,
                "command_id": command.command_id,
                "command": command.command,
                "endpoint": "GET /iclock/getrequest"
            }
        )
        
        # Print to console for debugging
        print("\n" + "="*80)
        print("COMMAND SENT TO DEVICE")
        print("="*80)
        print(f"Device SN: {SN}")
        print(f"Command ID: {command.command_id}")
        print(f"Command String: {command.command}")
        print(f"Command Length: {len(command.command)} bytes")
        print("="*80 + "\n")
        
        return Response(content=command.command, media_type="text/plain")
    else:
        logger.debug(
            f"No pending commands for device {SN}",
            extra={
                "device_serial": SN,
                "endpoint": "GET /iclock/getrequest"
            }
        )
        return Response(content="OK", media_type="text/plain")


@router.post("/devicecmd")
async def acknowledge_device_command(
    request: Request,
    SN: str = Query(..., description="Device serial number"),
    db: Session = Depends(get_db)
):
    """
    Command acknowledgment endpoint.
    
    The device posts execution results to this endpoint after processing a command.
    Server updates command status based on device response.
    
    Query Parameters:
    - SN: Device serial number (required)
    
    Request Body:
    Raw response from device (text/plain)
    
    Response Format (from device):
    ID=<command_id>&Return=<status_code>&CMD=<command>
    
    Status Codes (Return field):
    - 0: Success
    - -1: Unknown command syntax
    - -1002: Invalid command format or unknown command
    - -1003: Command parameter error
    - -1004: Command execution failed
    - -1005: Insufficient memory
    - -1006: User already exists
    - -1007: User does not exist
    
    Example Request:
    POST /iclock/devicecmd?SN=ZAM230001234
    Body: ID=295&Return=0&CMD=
    
    Example Response:
    OK
    """
    service = PushDeviceService(db)
    
    # Update device last_seen
    service.register_or_update_device(SN)
    
    # Read raw response body
    body_bytes = await request.body()
    response_data = body_bytes.decode('utf-8', errors='replace').strip()
    
    # Print to console for debugging
    print("\n" + "="*80)
    print("COMMAND ACKNOWLEDGMENT FROM DEVICE")
    print("="*80)
    print(f"Device SN: {SN}")
    print(f"Response Data: {response_data}")
    print(f"Query Params: {dict(request.query_params)}")
    print("="*80 + "\n")
    
    logger.info(
        f"Command acknowledgment from device {SN}",
        extra={
            "device_serial": SN,
            "response_data": response_data,
            "endpoint": "POST /iclock/devicecmd"
        }
    )
    
    # Parse ACTUAL ZKTeco PUSH response format: ID=<id>&Return=<code>&CMD=<command>
    # This is URL query parameter style, not colon-separated
    command_id = None
    return_code = None
    cmd_field = None
    
    # Parse URL-encoded response (e.g., "ID=295&Return=-1002&CMD=")
    if "ID=" in response_data and "Return=" in response_data:
        parts = response_data.split("&")
        for part in parts:
            if "=" in part:
                key, value = part.split("=", 1)
                if key == "ID":
                    command_id = value
                elif key == "Return":
                    return_code = value
                elif key == "CMD":
                    cmd_field = value
        
        if command_id and return_code:
            # Return=0 means success, non-zero means error
            success = return_code == "0"
            
            # Map common return codes to error messages
            error_messages = {
                "-1": "Unknown command syntax. The command format is not recognized by the device.",
                "-1002": "Invalid command format or unknown command. Device does not recognize the command structure.",
                "-1003": "Command parameter error. One or more parameters are invalid or missing.",
                "-1004": "Command execution failed. Device could not complete the operation.",
                "-1005": "Insufficient memory. Device cannot store the data.",
                "-1006": "User already exists. Cannot add duplicate user.",
                "-1007": "User does not exist. Cannot update or delete non-existent user.",
            }
            
            error_msg = error_messages.get(return_code, f"Unknown error code: {return_code}")
            
            # Update command status
            command = service.acknowledge_command(
                command_id=command_id,
                device_serial=SN,
                response_data=response_data,
                success=success
            )
            
            if command:
                logger.info(
                    f"Command {command_id} acknowledged: {'SUCCESS' if success else 'FAILED'}\n"
                    f"  Return Code: {return_code}\n"
                    f"  Error: {error_msg if not success else 'None'}",
                    extra={
                        "device_serial": SN,
                        "command_id": command_id,
                        "success": success,
                        "return_code": return_code,
                        "error_message": error_msg if not success else None
                    }
                )
                
                # Print detailed info to console
                print("\n" + "="*80)
                print("COMMAND RESULT")
                print("="*80)
                print(f"Command ID: {command_id}")
                print(f"Status: {'SUCCESS' if success else 'FAILED'}")
                print(f"Return Code: {return_code}")
                if not success:
                    print(f"Error: {error_msg}")
                    print(f"Original Command: {command.command}")
                print("="*80 + "\n")
            else:
                logger.warning(
                    f"Unknown command acknowledgment: {command_id}",
                    extra={
                        "device_serial": SN,
                        "command_id": command_id,
                        "response_data": response_data
                    }
                )
        else:
            logger.warning(
                f"Incomplete acknowledgment data from device {SN}: {response_data}",
                extra={
                    "device_serial": SN,
                    "response_data": response_data
                }
            )
    else:
        logger.warning(
            f"Unexpected command acknowledgment format from device {SN}: {response_data}",
            extra={
                "device_serial": SN,
                "response_data": response_data
            }
        )
    
    return Response(content="OK", media_type="text/plain")


@router.post("/cdata")
async def receive_attendance_data(
    request: Request,
    SN: str = Query(..., description="Device serial number"),
    db: Session = Depends(get_db)
):
    """
    Device data upload endpoint (ATTLOG, USERINFO, BIODATA, OPERLOG, etc.).
    
    The device posts table payloads to this endpoint after capture or QUERY commands.
    Server logs the raw payload for analysis/processing.
    
    Query Parameters:
    - SN: Device serial number (required)
    - table: Data type (ATTLOG, USERINFO, BIODATA, OPERLOG, ...)
    - Stamp: Timestamp (optional)
    
    Request Body:
    Raw table data (text/plain)
    
    Example Request:
    POST /iclock/cdata?SN=ZAM230001234&table=ATTLOG&Stamp=1234567890
    Body:
    ATTLOG:123\t2024-01-15 09:30:00\t0\t1\t0\t0
    
    Example Response:
    OK
    """
    service = PushDeviceService(db)
    
    # Update device last_seen
    service.register_or_update_device(SN)
    
    table = (request.query_params.get("table") or "").strip().upper()
    body_bytes = await request.body()
    raw_payload = body_bytes.decode('utf-8', errors='replace')

    banner = "USERINFO PAYLOAD RECEIVED" if table == "USERINFO" else "DEVICE PUSH RECEIVED"
    print("\n" + "=" * 80)
    print(banner)
    print("=" * 80)
    print(f"Method: {request.method}")
    print(f"URL: {request.url}")
    print(f"Query Params: {dict(request.query_params)}")
    print(f"Table: {table or request.query_params.get('table')}")
    print(f"Headers: {dict(request.headers)}")
    print("Payload:")
    print(raw_payload)
    print("=" * 80 + "\n")
        
    # Get request metadata
    content_type = request.headers.get('content-type')
    content_length = request.headers.get('content-length')
    content_length_int = int(content_length) if content_length else len(body_bytes)
    
    # Persist raw upload (ATTLOG, USERINFO, and other tables)
    attendance_log = service.log_device_table_upload(
        device_serial=SN,
        raw_payload=raw_payload,
        table_name=table or None,
        content_type=content_type,
        content_length=content_length_int
    )
    
    logger.info(
        f"Device table data received: table={table or 'UNKNOWN'} "
        f"records={attendance_log.record_count} from device {SN}",
        extra={
            "device_serial": SN,
            "table": table or None,
            "record_count": attendance_log.record_count,
            "payload_size": content_length_int,
            "log_id": attendance_log.id,
            "endpoint": "POST /iclock/cdata",
            "raw_payload": raw_payload if settings.device_push_log_raw else None,
        }
    )
    
    # Return OK to acknowledge receipt
    return Response(content="OK", media_type="text/plain")


@router.get("/devices")
async def list_devices(
    db: Session = Depends(get_db)
):
    """
    List all registered PUSH devices (admin endpoint).
    
    Returns device registration info and last seen timestamps.
    This is an admin endpoint for monitoring device connectivity.
    """
    if not settings.device_push_enabled:
        return {"error": "PUSH protocol is not enabled"}
    
    service = PushDeviceService(db)
    devices = service.get_all_devices()
    
    return {
        "devices": [
            {
                "id": device.id,
                "serial_number": device.serial_number,
                "device_name": device.device_name,
                "platform": device.platform,
                "firmware_version": device.firmware_version,
                "device_type": device.device_type,
                "is_active": device.is_active,
                "first_seen": device.first_seen.isoformat() if device.first_seen else None,
                "last_seen": device.last_seen.isoformat() if device.last_seen else None,
            }
            for device in devices
        ]
    }


@router.get("/devices/{serial_number}/commands")
async def list_device_commands(
    serial_number: str,
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db)
):
    """
    List commands for a device (admin endpoint).
    
    Returns command history for monitoring and debugging.
    """
    if not settings.device_push_enabled:
        return {"error": "PUSH protocol is not enabled"}
    
    service = PushDeviceService(db)
    
    from models import CommandStatus
    status_filter = None
    if status:
        try:
            status_filter = CommandStatus(status.lower())
        except ValueError:
            pass
    
    commands = service.get_device_commands(serial_number, status_filter)
    
    return {
        "device_serial": serial_number,
        "commands": [
            {
                "id": cmd.id,
                "command_id": cmd.command_id,
                "command": cmd.command,
                "status": cmd.status.value,
                "response": cmd.response,
                "error_message": cmd.error_message,
                "created_at": cmd.created_at.isoformat() if cmd.created_at else None,
                "executed_at": cmd.executed_at.isoformat() if cmd.executed_at else None,
                "completed_at": cmd.completed_at.isoformat() if cmd.completed_at else None,
            }
            for cmd in commands
        ]
    }


# Authenticated device management / re-sync APIs (not part of ADMS /iclock protocol).
mgmt_router = APIRouter(prefix="/api/device", tags=["Device Sync"])


@mgmt_router.get("/devices")
def list_push_devices(
    db: Session = Depends(get_db),
    _session=Depends(require_admin_access),
):
    """
    List registered PUSH devices for admin UI (device_sn resolution).
    ADMIN and SUPER_ADMIN.
    """
    if not settings.device_push_enabled:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PUSH protocol is not enabled",
        )

    service = PushDeviceService(db)
    devices = service.get_all_devices()
    return {
        "devices": [
            {
                "id": device.id,
                "serial_number": device.serial_number,
                "device_name": device.device_name,
                "is_active": device.is_active,
                "last_seen": device.last_seen.isoformat() if device.last_seen else None,
            }
            for device in devices
        ]
    }


@mgmt_router.post("/{device_sn}/resync")
def resync_device_members(
    device_sn: str,
    db: Session = Depends(get_db),
    _session=Depends(require_super_admin),
):
    """
    Bulk re-sync all active members to a device.
    SUPER_ADMIN only.
    """
    if not settings.device_push_enabled:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PUSH protocol is not enabled",
        )

    service = PushDeviceService(db)
    try:
        return service.resync_all_members_to_device(device_sn)
    except DeviceNotRegisteredError as exc:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@mgmt_router.post("/{device_sn}/sync-user/{user_id}")
def sync_single_device_user(
    device_sn: str,
    user_id: int,
    db: Session = Depends(get_db),
    _session=Depends(require_admin_access),
):
    """
    Re-sync one member (by VYON member id / device PIN) to a device.
    ADMIN and SUPER_ADMIN.
    """
    if not settings.device_push_enabled:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PUSH protocol is not enabled",
        )

    service = PushDeviceService(db)
    try:
        return service.sync_single_member_to_device(user_id=user_id, device_sn=device_sn)
    except DeviceNotRegisteredError as exc:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except MemberSyncNotFoundError as exc:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
