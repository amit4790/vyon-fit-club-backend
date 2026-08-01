"""Device integration response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class DeviceConnectionStatusResponse(BaseModel):
    """Connection test response for the configured ZKTeco device."""

    message: str
    data: dict = Field(..., description="Connection status details")


class DeviceStatusData(BaseModel):
    connected: bool
    device_model: str | None
    serial_number: str | None
    firmware_version: str | None
    platform: str | None
    face_algorithm_version: str | None
    current_device_time: datetime | None
    user_count: int | None
    connection_error: str | None


class DeviceStatusResponse(BaseModel):
    message: str
    data: DeviceStatusData


class DeviceUserResponse(BaseModel):
    """Sanitized device user payload returned by admin diagnostics."""

    uid: int
    user_id: str
    name: str
    privilege: int
    card: int | None


class DeviceUsersResponse(BaseModel):
    """User list response from the configured ZKTeco device."""

    message: str
    data: list[DeviceUserResponse]


class DeviceAttendanceRecordResponse(BaseModel):
    uid: int | None
    user_id: str | None
    timestamp: datetime | None
    status: int | None
    punch: int | None


class DeviceAttendanceResponse(BaseModel):
    message: str
    data: list[DeviceAttendanceRecordResponse]


class MemberDeviceMappingRequest(BaseModel):
    device_user_id: str | None = Field(default=None, min_length=1, max_length=64)
    device_uid: int | None = Field(default=None, ge=0)
    device_card: int | None = Field(default=None, ge=0)
    push_to_device: bool = Field(default=False)


class MemberDeviceUnlinkRequest(BaseModel):
    delete_from_device: bool = Field(default=False)


class MemberDeviceMappingData(BaseModel):
    member_id: int
    device_user_id: str | None
    device_uid: int | None
    device_card: int | None
    device_sync_status: str
    last_device_sync_at: datetime | None


class MemberDeviceMappingResponse(BaseModel):
    message: str
    data: MemberDeviceMappingData
