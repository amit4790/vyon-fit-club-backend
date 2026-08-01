"""ZKTeco device service abstraction."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.config import Settings, settings


logger = logging.getLogger(__name__)


class DeviceServiceError(Exception):
    """Base exception for device integration failures."""


class DeviceDependencyError(DeviceServiceError):
    """Raised when the ZKTeco SDK dependency is unavailable."""


class DeviceConnectionError(DeviceServiceError):
    """Raised when a device connection cannot be established."""


class DeviceOperationError(DeviceServiceError):
    """Raised when a device operation fails after a connection is established."""


class DeviceNotFoundError(DeviceOperationError):
    """Raised when an entity does not exist on the device."""


class DeviceValidationError(DeviceServiceError):
    """Raised when device request parameters are invalid."""


@dataclass(frozen=True)
class DeviceUser:
    uid: int
    user_id: str
    name: str
    privilege: int
    password: str
    group_id: str
    card: int | None
    enabled: bool


@dataclass(frozen=True)
class DeviceStatus:
    connected: bool
    device_model: str | None
    serial_number: str | None
    firmware_version: str | None
    platform: str | None
    face_algorithm_version: str | None
    current_device_time: datetime | None
    user_count: int | None
    connection_error: str | None


@dataclass(frozen=True)
class DeviceAttendanceRecord:
    uid: int | None
    user_id: str | None
    timestamp: datetime | None
    status: int | None
    punch: int | None


class DeviceService:
    """Isolated adapter around ZKTeco TCP communication."""

    def __init__(self, app_settings: Settings | None = None):
        self.settings = app_settings or settings
        self._zk_client: Any | None = None
        self._connection: Any | None = None

    def _log_context(self) -> dict[str, Any]:
        return {
            "device_host": self.settings.zkteco_device_host,
            "device_port": self.settings.zkteco_device_port,
            "device_id": self.settings.zkteco_device_id,
        }

    @staticmethod
    def _normalize_value(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    def _safe_fetch(self, field_name: str, operation: Any) -> Any:
        try:
            return self._normalize_value(operation())
        except Exception:
            logger.warning(
                "Unable to fetch ZKTeco field",
                extra={**self._log_context(), "field_name": field_name},
                exc_info=True,
            )
            return None

    def _map_user(self, user: Any) -> DeviceUser:
        return DeviceUser(
            uid=int(getattr(user, "uid", 0)),
            user_id=str(getattr(user, "user_id", "") or ""),
            name=str(getattr(user, "name", "") or ""),
            privilege=int(getattr(user, "privilege", 0)),
            password=str(getattr(user, "password", "") or ""),
            group_id=str(getattr(user, "group_id", "") or ""),
            card=int(getattr(user, "card", 0)) if getattr(user, "card", None) is not None else None,
            enabled=bool(user.is_enabled()) if hasattr(user, "is_enabled") else True,
        )

    @staticmethod
    def _normalize_user_id(user_id: str | None) -> str | None:
        if user_id is None:
            return None
        normalized = user_id.strip()
        return normalized or None

    def _guard_user_identifier(self, *, uid: int | None, user_id: str | None) -> tuple[int | None, str | None]:
        normalized_user_id = self._normalize_user_id(user_id)
        if uid is None and normalized_user_id is None:
            raise DeviceValidationError("Either uid or user_id must be provided")
        return uid, normalized_user_id

    def _build_client(self) -> Any:
        try:
            from zk import ZK
        except ModuleNotFoundError as exc:
            raise DeviceDependencyError(
                "pyzk is not installed. Add the backend dependency set before using ZKTeco integration."
            ) from exc

        return ZK(
            self.settings.zkteco_device_host,
            port=self.settings.zkteco_device_port,
            timeout=self.settings.zkteco_timeout_seconds,
            password=self.settings.zkteco_communication_key,
            force_udp=False,
            ommit_ping=self.settings.zkteco_omit_ping,
            encoding=self.settings.zkteco_encoding,
        )

    def connect(self) -> Any:
        if self._connection is not None:
            return self._connection

        logger.info(
            "Connecting to ZKTeco device",
            extra=self._log_context(),
        )

        self._zk_client = self._build_client()

        try:
            self._connection = self._zk_client.connect()
            logger.info(
                "Connected to ZKTeco device",
                extra=self._log_context(),
            )
            return self._connection
        except Exception as exc:
            logger.exception(
                "Failed to connect to ZKTeco device",
                extra=self._log_context(),
            )
            self._connection = None
            self._zk_client = None
            raise DeviceConnectionError(
                f"Unable to connect to ZKTeco device at {self.settings.zkteco_device_host}:{self.settings.zkteco_device_port}"
            ) from exc

    def disconnect(self) -> None:
        if self._connection is None:
            return

        logger.info(
            "Disconnecting from ZKTeco device",
            extra=self._log_context(),
        )

        try:
            try:
                self._connection.enable_device()
            except Exception:
                logger.warning(
                    "Unable to re-enable ZKTeco device before disconnect",
                    extra=self._log_context(),
                    exc_info=True,
                )

            self._connection.disconnect()
        except Exception as exc:
            logger.exception(
                "Failed to disconnect from ZKTeco device cleanly",
                extra=self._log_context(),
            )
            raise DeviceOperationError("Unable to disconnect cleanly from ZKTeco device") from exc
        finally:
            self._connection = None
            self._zk_client = None

    def get_status(self) -> DeviceStatus:
        logger.info("Fetching ZKTeco device status", extra=self._log_context())

        try:
            connection = self.connect()
        except DeviceServiceError as exc:
            logger.warning(
                "ZKTeco device status unavailable",
                extra={**self._log_context(), "connection_error": str(exc)},
            )
            return DeviceStatus(
                connected=False,
                device_model=None,
                serial_number=None,
                firmware_version=None,
                platform=None,
                face_algorithm_version=None,
                current_device_time=None,
                user_count=None,
                connection_error=str(exc),
            )

        user_count: int | None = None
        try:
            sizes_read = self._safe_fetch("read_sizes", connection.read_sizes)
            if sizes_read:
                user_count = self._normalize_value(getattr(connection, "users", None))
                if user_count is not None:
                    user_count = int(user_count)
            if user_count is None:
                fallback_users = self._safe_fetch("get_users", connection.get_users)
                if fallback_users is not None:
                    user_count = len(fallback_users)

            status = DeviceStatus(
                connected=True,
                device_model=self._safe_fetch("get_device_name", connection.get_device_name),
                serial_number=self._safe_fetch("get_serialnumber", connection.get_serialnumber),
                firmware_version=self._safe_fetch("get_firmware_version", connection.get_firmware_version),
                platform=self._safe_fetch("get_platform", connection.get_platform),
                face_algorithm_version=self._safe_fetch("get_face_version", connection.get_face_version),
                current_device_time=self._safe_fetch("get_time", connection.get_time),
                user_count=user_count,
                connection_error=None,
            )
            logger.info(
                "Fetched ZKTeco device status",
                extra={**self._log_context(), "connected": status.connected, "user_count": status.user_count},
            )
            return status
        except Exception as exc:
            logger.exception("Failed to fetch ZKTeco device status", extra=self._log_context())
            raise DeviceOperationError("Unable to fetch ZKTeco device status") from exc

    def get_users(self) -> list[DeviceUser]:
        connection = self.connect()
        device_disabled = False

        logger.info(
            "Fetching users from ZKTeco device",
            extra=self._log_context(),
        )

        try:
            connection.disable_device()
            device_disabled = True

            users = connection.get_users()
            mapped_users = [self._map_user(user) for user in users]

            logger.info(
                "Fetched users from ZKTeco device",
                extra={**self._log_context(), "user_count": len(mapped_users)},
            )
            return mapped_users
        except DeviceServiceError:
            raise
        except Exception as exc:
            logger.exception(
                "Failed to fetch users from ZKTeco device",
                extra=self._log_context(),
            )
            raise DeviceOperationError("Unable to fetch users from ZKTeco device") from exc
        finally:
            if device_disabled:
                try:
                    connection.enable_device()
                except Exception:
                    logger.warning(
                        "Unable to re-enable ZKTeco device after get_users",
                        extra=self._log_context(),
                        exc_info=True,
                    )

    def find_user(self, *, uid: int | None = None, user_id: str | None = None) -> DeviceUser | None:
        uid, user_id = self._guard_user_identifier(uid=uid, user_id=user_id)
        users = self.get_users()

        for user in users:
            if uid is not None and user.uid == uid:
                return user
            if user_id is not None and user.user_id == user_id:
                return user
        return None

    def create_user(
        self,
        *,
        uid: int | None = None,
        user_id: str,
        name: str,
        privilege: int = 0,
        password: str = "",
        group_id: str = "",
        card: int = 0,
    ) -> DeviceUser:
        normalized_user_id = self._normalize_user_id(user_id)
        normalized_name = name.strip()

        if normalized_user_id is None:
            raise DeviceValidationError("user_id is required")
        if not normalized_name:
            raise DeviceValidationError("name is required")

        connection = self.connect()
        device_disabled = False

        logger.info(
            "Creating or updating user on ZKTeco device",
            extra={**self._log_context(), "uid": uid, "user_id": normalized_user_id},
        )

        try:
            connection.disable_device()
            device_disabled = True

            connection.set_user(
                uid=uid,
                name=normalized_name,
                privilege=int(privilege),
                password=password or "",
                group_id=group_id or "",
                user_id=normalized_user_id,
                card=int(card),
            )

            created_user = self.find_user(uid=uid, user_id=normalized_user_id)
            if created_user is None:
                # Some firmware variants can acknowledge set_user but not return
                # user listings immediately, so return the persisted intent payload.
                return DeviceUser(
                    uid=int(uid or 0),
                    user_id=normalized_user_id,
                    name=normalized_name,
                    privilege=int(privilege),
                    password=password or "",
                    group_id=group_id or "",
                    card=int(card),
                    enabled=True,
                )

            return created_user
        except DeviceServiceError:
            raise
        except Exception as exc:
            logger.exception(
                "Failed to create user on ZKTeco device",
                extra={**self._log_context(), "uid": uid, "user_id": normalized_user_id},
            )
            raise DeviceOperationError("Unable to create user on ZKTeco device") from exc
        finally:
            if device_disabled:
                try:
                    connection.enable_device()
                except Exception:
                    logger.warning(
                        "Unable to re-enable ZKTeco device after create_user",
                        extra=self._log_context(),
                        exc_info=True,
                    )

    def delete_user(self, *, uid: int | None = None, user_id: str | None = None) -> None:
        uid, user_id = self._guard_user_identifier(uid=uid, user_id=user_id)
        connection = self.connect()
        device_disabled = False

        logger.info(
            "Deleting user from ZKTeco device",
            extra={**self._log_context(), "uid": uid, "user_id": user_id},
        )

        try:
            connection.disable_device()
            device_disabled = True

            deleted = connection.delete_user(uid=uid or 0, user_id=user_id or "")
            if deleted is False:
                raise DeviceNotFoundError("Device user not found")
        except DeviceServiceError:
            raise
        except Exception as exc:
            logger.exception(
                "Failed to delete user from ZKTeco device",
                extra={**self._log_context(), "uid": uid, "user_id": user_id},
            )
            raise DeviceOperationError("Unable to delete user from ZKTeco device") from exc
        finally:
            if device_disabled:
                try:
                    connection.enable_device()
                except Exception:
                    logger.warning(
                        "Unable to re-enable ZKTeco device after delete_user",
                        extra=self._log_context(),
                        exc_info=True,
                    )

    def get_attendance(self, *, limit: int | None = None) -> list[DeviceAttendanceRecord]:
        if limit is not None and limit <= 0:
            raise DeviceValidationError("limit must be greater than zero when provided")

        connection = self.connect()
        logger.info("Fetching attendance from ZKTeco device", extra={**self._log_context(), "limit": limit})

        try:
            attendance_rows = connection.get_attendance()
            if limit is not None:
                attendance_rows = attendance_rows[-limit:]

            mapped_rows = [
                DeviceAttendanceRecord(
                    uid=int(getattr(row, "uid", 0)) if getattr(row, "uid", None) is not None else None,
                    user_id=self._normalize_user_id(getattr(row, "user_id", None)),
                    timestamp=getattr(row, "timestamp", None),
                    status=int(getattr(row, "status", 0)) if getattr(row, "status", None) is not None else None,
                    punch=int(getattr(row, "punch", 0)) if getattr(row, "punch", None) is not None else None,
                )
                for row in attendance_rows
            ]

            logger.info(
                "Fetched attendance records from ZKTeco device",
                extra={**self._log_context(), "attendance_count": len(mapped_rows)},
            )
            return mapped_rows
        except DeviceServiceError:
            raise
        except Exception as exc:
            logger.exception("Failed to fetch attendance from ZKTeco device", extra=self._log_context())
            raise DeviceOperationError("Unable to fetch attendance from ZKTeco device") from exc