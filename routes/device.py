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

Design rules (keep Neon able to suspend, keep the device happy):
1. Traffic that carries no new information never touches the DB.
2. Device routes ALWAYS answer plain-text "OK" on failure (never JSON errors),
   otherwise the firmware enters exponential backoff.
3. Blocking SQLAlchemy work never runs on the event loop: DB-only handlers are
   plain `def`; handlers that must read the body are `async` and hand the DB
   work to a threadpool function.

Recommended .env values (must be LONGER than Neon's suspend delay, 5 min default):
    DEVICE_EMPTY_POLL_SKIP_SECONDS=1800
    DEVICE_PRESENCE_WRITE_INTERVAL_SECONDS=1800
    DEVICE_PERSIST_CDATA_TABLES=ATTLOG
Run with a single worker (--workers 1) while device_poll_cache is process-local.
"""

from datetime import datetime, timezone
import logging
from typing import Callable, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status as http_status
from fastapi.concurrency import run_in_threadpool
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from dependencies import require_admin_access, require_super_admin
from models import CommandStatus
from services.push_device_service import (
    DeviceNotRegisteredError,
    MemberSyncNotFoundError,
    PushDeviceService,
    device_poll_cache,
)
from core.config import settings

logger = logging.getLogger(__name__)

# device_poll_cache is intentionally process-local to avoid database traffic on
# high-frequency device polls. In a multi-worker or multi-instance deployment,
# replace it with a shared, TTL-backed store (for example Redis) so throttling
# and command-delivery hints remain consistent across instances.
# NOTE: because handlers now run in a threadpool, device_poll_cache must guard
# its check-then-set operations with a threading.Lock.

OK_BODY = "OK"


def _ok() -> Response:
    return Response(content=OK_BODY, media_type="text/plain")


# ---------------------------------------------------------------------------
# Protocol safety net
# ---------------------------------------------------------------------------
class DeviceProtocolRoute(APIRoute):
    """
    Device firmware only understands plain text. Any failure on a device route
    (validation error, DB error, cache bug, cold-start connection error, ...)
    is converted into a plain-text "OK" instead of a JSON 4xx/5xx body.
    """

    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)  # also catches 422 validation errors
            except Exception:
                logger.exception(
                    "Device route failed, replying OK: %s %s",
                    request.method,
                    request.url.path,
                )
                return _ok()

        return handler


router = APIRouter(
    prefix="/iclock",
    tags=["Device PUSH Protocol"],
    route_class=DeviceProtocolRoute,
)


def _safe_rollback(db: Session) -> None:
    """Rollback that can never raise (the connection may already be dead)."""
    try:
        db.rollback()
    except Exception:
        logger.debug("Rollback failed (connection likely dead)", exc_info=True)


def _safe_close(db: Session) -> None:
    try:
        db.close()
    except Exception:
        logger.debug("Session close failed", exc_info=True)


def _new_session() -> Session:
    """
    Session for device routes. expire_on_commit=False keeps objects readable
    after commit, so reading attendance_log.id / command.command afterwards does
    not trigger an extra SELECT round trip.
    """
    return SessionLocal(expire_on_commit=False)


# While a dispatched command is still awaiting its ACK, use a short empty-poll
# window (must exceed STALE_EXECUTING_AFTER = 2 min in push_device_service) so a
# lost ACK is reclaimed within minutes rather than after the full skip window.
_EXECUTING_RECHECK_SECONDS = 150


# ---------------------------------------------------------------------------
# GET /iclock/cdata  (heartbeat / handshake)
# ---------------------------------------------------------------------------
@router.get("/cdata")
def device_heartbeat(
    request: Request,
    SN: str = Query(..., description="Device serial number"),
):
    """
    Device heartbeat and information endpoint.

    Plain `def`: FastAPI runs it in the threadpool, so blocking DB calls do not
    stall the event loop. Presence writes are throttled so frequent heartbeats
    do not keep Neon awake. Transient heartbeat params (options/pushver/language)
    do not force a DB hit when the device is already known and identity
    metadata is unchanged.
    """
    device_poll_cache.note_contact(SN)  # memory only, never touches the DB

    query_params = dict(request.query_params)
    device_info = {
        "options": query_params.get("options"),
        "pushver": query_params.get("pushver"),
        "language": query_params.get("language"),
        "platform": query_params.get("platform"),
        "firmware_version": query_params.get("FWVersion"),
        "device_type": query_params.get("DeviceType"),
        "device_name": query_params.get("DeviceName"),
    }
    device_info = {k: v for k, v in device_info.items() if v is not None}

    if device_poll_cache.can_skip_heartbeat_db(
        SN,
        device_info,
        interval_seconds=settings.device_presence_write_interval_seconds,
    ):
        logger.debug(
            "Device heartbeat skipped DB: %s",
            SN,
            extra={"device_serial": SN, "endpoint": "GET /iclock/cdata"},
        )
        return _ok()

    db = _new_session()
    try:
        PushDeviceService(db).register_or_update_device(SN, device_info or None)
    except Exception:
        _safe_rollback(db)
        logger.exception("Heartbeat DB update failed: serial=%s", SN)
        return _ok()  # keep device connected
    finally:
        _safe_close(db)

    logger.info(
        "Device heartbeat: %s",
        SN,
        extra={
            "device_serial": SN,
            "device_info": device_info,
            "endpoint": "GET /iclock/cdata",
        },
    )
    return _ok()


# ---------------------------------------------------------------------------
# GET /iclock/getrequest  (command polling)
# ---------------------------------------------------------------------------
@router.get("/getrequest")
def get_device_command(
    request: Request,
    SN: str = Query(..., description="Device serial number"),
):
    """
    Command polling endpoint.

    Empty polls skip the DB entirely for DEVICE_EMPTY_POLL_SKIP_SECONDS.
    Presence (last_seen) writes respect DEVICE_PRESENCE_WRITE_INTERVAL_SECONDS.
    Every code path that creates a DeviceCommand MUST call
    device_poll_cache.mark_command_queued(serial) after committing, so the same
    process delivers immediately; cross-instance delay is at most the
    empty-poll window.
    """
    device_poll_cache.note_contact(SN)  # memory only, never touches the DB

    if (
        settings.device_empty_poll_skip_seconds > 0
        and device_poll_cache.should_skip_empty_poll_db(SN)
    ):
        logger.debug(
            "Empty-poll cache hit for device %s",
            SN,
            extra={"device_serial": SN, "endpoint": "GET /iclock/getrequest"},
        )
        return _ok()

    # Read BEFORE the DB query. If a command is committed while this poll is
    # running, mark_empty_poll sees the version changed and will not overwrite
    # the "command pending" hint with a long skip window.
    seen_version = device_poll_cache.queue_version(SN)

    db = _new_session()
    try:
        service = PushDeviceService(db)
        # Do not force_touch: getrequest is high-frequency; use presence throttle.
        service.register_or_update_device(SN)
        command = service.get_pending_command(SN)
        db.commit()  # no-op if the service already committed

        if command:
            device_poll_cache.mark_command_queued(SN)
            logger.info(
                "Command dispatched: serial=%s command_id=%s command=%r",
                SN,
                command.command_id,
                command.command,
                extra={
                    "device_serial": SN,
                    "command_id": command.command_id,
                    "command": command.command,
                    "endpoint": "GET /iclock/getrequest",
                },
            )
            if settings.device_push_log_raw:
                logger.debug(
                    "Command sent to device: serial=%s command_id=%s command=%r length=%d",
                    SN,
                    command.command_id,
                    command.command,
                    len(command.command),
                )
            return Response(content=command.command, media_type="text/plain")

        skip_seconds = settings.device_empty_poll_skip_seconds
        if service.has_executing_outstanding:
            skip_seconds = min(skip_seconds, _EXECUTING_RECHECK_SECONDS)
        device_poll_cache.mark_empty_poll(
            SN,
            skip_seconds=skip_seconds,
            seen_version=seen_version,
        )
        logger.debug(
            "No pending commands for device %s",
            SN,
            extra={"device_serial": SN, "endpoint": "GET /iclock/getrequest"},
        )
        return _ok()
    except Exception:
        _safe_rollback(db)
        logger.exception("getrequest failed: serial=%s", SN)
        # Deliberately NOT recording an empty poll here: if the DB was just
        # cold-starting, the next poll should retry rather than be skipped for
        # the whole window (a queued command would be delayed).
        return _ok()
    finally:
        _safe_close(db)


# ---------------------------------------------------------------------------
# POST /iclock/devicecmd  (command acknowledgment)
# ---------------------------------------------------------------------------
_ACK_ERROR_MESSAGES = {
    "-1": "Unknown command syntax. The command format is not recognized by the device.",
    "-1002": "Invalid command format or unknown command. Device does not recognize the command structure.",
    "-1003": "Command parameter error. One or more parameters are invalid or missing.",
    "-1004": "Command execution failed. Device could not complete the operation.",
    "-1005": "Insufficient memory. Device cannot store the data.",
    "-1006": "User already exists. Cannot add duplicate user.",
    "-1007": "User does not exist. Cannot update or delete non-existent user.",
}


def _parse_ack(response_data: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Parse 'ID=<id>&Return=<code>&CMD=<command>' into its three fields."""
    command_id = return_code = cmd_field = None
    if "ID=" in response_data and "Return=" in response_data:
        for part in response_data.split("&"):
            if "=" in part:
                key, value = part.split("=", 1)
                if key == "ID":
                    command_id = value
                elif key == "Return":
                    return_code = value
                elif key == "CMD":
                    cmd_field = value
    return command_id, return_code, cmd_field


def _process_command_ack(SN: str, response_data: str) -> None:
    """Sync DB work for /devicecmd. Runs in the threadpool with its own session."""
    if not ("ID=" in response_data and "Return=" in response_data):
        logger.warning(
            "Unexpected command acknowledgment format from device %s: %s",
            SN,
            response_data,
            extra={"device_serial": SN, "response_data": response_data},
        )
        return

    command_id, return_code, _cmd_field = _parse_ack(response_data)
    if not (command_id and return_code):
        logger.warning(
            "Incomplete acknowledgment data from device %s: %s",
            SN,
            response_data,
            extra={"device_serial": SN, "response_data": response_data},
        )
        return

    success = return_code == "0"
    error_msg = _ACK_ERROR_MESSAGES.get(return_code, f"Unknown error code: {return_code}")

    db = _new_session()
    try:
        service = PushDeviceService(db)
        # The device just talked to us, so the DB is awake anyway; still let the
        # normal presence throttle decide instead of forcing a write.
        service.register_or_update_device(SN, force_touch=False)

        command = service.acknowledge_command(
            command_id=command_id,
            device_serial=SN,
            response_data=response_data,
            success=success,
        )
        db.commit()  # no-op if the service already committed
    except Exception:
        _safe_rollback(db)
        logger.exception(
            "Failed to record command acknowledgment: serial=%s command_id=%s",
            SN,
            command_id,
        )
        return
    finally:
        _safe_close(db)

    if command:
        logger.info(
            "Command %s acknowledged: %s | return_code=%s error=%s",
            command_id,
            "SUCCESS" if success else "FAILED",
            return_code,
            error_msg if not success else "None",
            extra={
                "device_serial": SN,
                "command_id": command_id,
                "success": success,
                "return_code": return_code,
                "error_message": error_msg if not success else None,
            },
        )
    else:
        logger.warning(
            "Unknown command acknowledgment: %s",
            command_id,
            extra={
                "device_serial": SN,
                "command_id": command_id,
                "response_data": response_data,
            },
        )


@router.post("/devicecmd")
async def acknowledge_device_command(
    request: Request,
    SN: str = Query(..., description="Device serial number"),
):
    """
    Command acknowledgment endpoint.

    The device posts execution results after processing a command.
    Body format: ID=<command_id>&Return=<status_code>&CMD=<command>
    Return=0 is success; see _ACK_ERROR_MESSAGES for known error codes.

    async only to read the body; all DB work runs in the threadpool.
    """
    device_poll_cache.note_contact(SN)  # memory only, never touches the DB

    body_bytes = await request.body()
    response_data = body_bytes.decode("utf-8", errors="replace").strip()

    if settings.device_push_log_raw:
        logger.debug(
            "Command acknowledgment received: serial=%s response=%r query_params=%r",
            SN,
            response_data,
            dict(request.query_params),
        )

    logger.info(
        "Command acknowledgment from device %s",
        SN,
        extra={
            "device_serial": SN,
            "response_data": response_data,
            "endpoint": "POST /iclock/devicecmd",
        },
    )

    await run_in_threadpool(_process_command_ack, SN, response_data)
    return _ok()


# ---------------------------------------------------------------------------
# POST /iclock/cdata  (table uploads: ATTLOG, OPERLOG, USERINFO, ...)
# ---------------------------------------------------------------------------
def _store_upload(
    SN: str,
    table: str,
    raw_payload: str,
    payload_size: int,
    content_type: Optional[str],
    content_length: Optional[str],
    request_meta: Optional[dict],
) -> None:
    """Sync DB work for POST /cdata. Runs in the threadpool with its own session."""
    db = _new_session()
    try:
        service = PushDeviceService(db)

        # cdata may be frequent; let the standard presence throttle decide when
        # last_seen is written instead of forcing an UPDATE for every upload.
        service.register_or_update_device(SN, force_touch=False)

        if request_meta is not None:  # only populated when device_push_log_raw is on
            logger.debug(
                "Device PUSH payload received: method=%s url=%s query_params=%r "
                "table=%s headers=%r payload=%r",
                request_meta["method"],
                request_meta["url"],
                request_meta["query_params"],
                table,
                request_meta["headers"],
                raw_payload,
            )

        try:
            content_length_int = int(content_length) if content_length else payload_size
        except ValueError:
            content_length_int = payload_size

        # Persist only allowlisted non-empty tables (default: ATTLOG).
        attendance_log = service.log_device_table_upload(
            device_serial=SN,
            raw_payload=raw_payload,
            table_name=table or None,
            content_type=content_type,
            content_length=content_length_int,
        )

        # Capture now: after a commit/rollback these attributes are expired and
        # reading them later costs an extra SELECT (or fails after a rollback).
        log_id = attendance_log.id if attendance_log is not None else None
        record_count = attendance_log.record_count if attendance_log is not None else 0

        # Parse ATTLOG punches even when raw blob persistence is disabled for the table.
        if table == "ATTLOG":
            try:
                from services.attendance_service import AttendanceService

                inserted = AttendanceService(db).ingest_attlog_payload(
                    device_serial=SN,
                    raw_payload=raw_payload,
                )
                if attendance_log is not None:
                    attendance_log.is_processed = True
                    attendance_log.processed_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(
                    "ATTLOG parsed into attendance punches: inserted=%s",
                    inserted,
                    extra={"device_serial": SN, "inserted": inserted},
                )
            except Exception:
                # The raw-log insert may already be committed, but a failed
                # punch ingest can leave this session in a failed transaction
                # state. Reset it before the session is closed.
                _safe_rollback(db)
                logger.exception(
                    "Failed to parse ATTLOG into attendance punches",
                    extra={"device_serial": SN},
                )

        if log_id is None:
            logger.info(
                "Device table data received (not stored): table=%s from device %s",
                table or "UNKNOWN",
                SN,
                extra={
                    "device_serial": SN,
                    "table": table or None,
                    "record_count": 0,
                    "payload_size": content_length_int,
                    "endpoint": "POST /iclock/cdata",
                },
            )
            return

        logger.info(
            "Device table data received: table=%s records=%s from device %s",
            table or "UNKNOWN",
            record_count,
            SN,
            extra={
                "device_serial": SN,
                "table": table or None,
                "record_count": record_count,
                "payload_size": content_length_int,
                "log_id": log_id,
                "endpoint": "POST /iclock/cdata",
                "raw_payload": raw_payload if settings.device_push_log_raw else None,
            },
        )
    except Exception:
        _safe_rollback(db)
        logger.exception("Device table upload failed: serial=%s table=%s", SN, table)
    finally:
        _safe_close(db)


@router.post("/cdata")
async def receive_attendance_data(
    request: Request,
    SN: str = Query(..., description="Device serial number"),
):
    """
    Device data upload endpoint (ATTLOG, USERINFO, BIODATA, OPERLOG, etc.).

    Query Parameters:
    - SN: Device serial number (required)
    - table: Data type (ATTLOG, USERINFO, BIODATA, OPERLOG, ...)
    - Stamp: Timestamp (optional)

    Body: raw table data (text/plain), e.g.
    ATTLOG:123\t2024-01-15 09:30:00\t0\t1\t0\t0

    Always answers "OK". Anything that is not an allowlisted, non-empty table is
    acknowledged without touching the DB. The handler is async only to read the
    body; DB work runs in the threadpool via _store_upload.
    """
    device_poll_cache.note_contact(SN)  # memory only, covers OPERLOG/empty uploads too

    table = (request.query_params.get("table") or "").strip().upper()

    # Most cdata traffic is operational/noisy data (OPERLOG etc.). Decide before
    # reading the body or creating a session so Neon is never woken for it.
    if not table or table not in settings.device_persist_cdata_table_set:
        logger.debug(
            "Device table upload acknowledged without DB access: table=%s device=%s",
            table or "UNKNOWN",
            SN,
        )
        return _ok()

    body_bytes = await request.body()
    raw_payload = body_bytes.decode("utf-8", errors="replace")

    # Empty payload has nothing to persist or parse.
    if not raw_payload.strip():
        logger.debug(
            "Empty device table upload acknowledged without DB access: table=%s device=%s",
            table,
            SN,
        )
        return _ok()

    request_meta = None
    if settings.device_push_log_raw:
        request_meta = {
            "method": request.method,
            "url": str(request.url),
            "query_params": dict(request.query_params),
            "headers": dict(request.headers),
        }

    await run_in_threadpool(
        _store_upload,
        SN,
        table,
        raw_payload,
        len(body_bytes),
        request.headers.get("content-type"),
        request.headers.get("content-length"),
        request_meta,
    )
    return _ok()


# ---------------------------------------------------------------------------
# Authenticated device management / admin APIs (NOT part of the ADMS protocol).
# Deliberately a plain APIRouter: real HTTP errors (401/403/404/503) must reach
# the caller, so DeviceProtocolRoute must not wrap these.
# ---------------------------------------------------------------------------
mgmt_router = APIRouter(prefix="/api/device", tags=["Device Sync"])


def _require_push_enabled() -> None:
    if not settings.device_push_enabled:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PUSH protocol is not enabled",
        )


@mgmt_router.get("/devices")
def list_push_devices(
    db: Session = Depends(get_db),
    _session=Depends(require_admin_access),
):
    """
    List registered PUSH devices for admin UI (device_sn resolution).
    ADMIN and SUPER_ADMIN.

    Replaces the old unauthenticated GET /iclock/devices.
    Note: last_seen is written at most once per
    DEVICE_PRESENCE_WRITE_INTERVAL_SECONDS, so it can lag by that much. For a
    live online/offline indicator, read the in-memory last-contact time from
    device_poll_cache instead.
    """
    _require_push_enabled()

    service = PushDeviceService(db)
    devices = service.get_all_devices()

    def _effective_last_seen(device):
        # DB last_seen is written at most once per presence interval, so merge in
        # the in-memory last contact for an accurate online/offline indicator.
        candidates = [t for t in (device.last_seen, device_poll_cache.last_contact(device.serial_number)) if t]
        return max(candidates) if candidates else None

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
                "last_seen": (
                    _effective_last_seen(device).isoformat()
                    if _effective_last_seen(device)
                    else None
                ),
            }
            for device in devices
        ]
    }


@mgmt_router.get("/devices/{serial_number}/commands")
def list_device_commands(
    serial_number: str,
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
    _session=Depends(require_admin_access),
):
    """
    List commands for a device (ADMIN and SUPER_ADMIN).

    Replaces the old unauthenticated GET /iclock/devices/{serial}/commands.
    """
    _require_push_enabled()

    service = PushDeviceService(db)

    status_filter = None
    if status:
        try:
            status_filter = CommandStatus(status.lower())
        except ValueError:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status}",
            )

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
        ],
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
    _require_push_enabled()

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
    _require_push_enabled()

    service = PushDeviceService(db)
    try:
        return service.sync_single_member_to_device(user_id=user_id, device_sn=device_sn)
    except DeviceNotRegisteredError as exc:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except MemberSyncNotFoundError as exc:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
