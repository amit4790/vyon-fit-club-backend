"""Schemas for mobile OTP + PIN authentication."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


MobileAuthRole = Literal["MEMBER", "TRAINER"]
MobileOtpPurpose = Literal["activate", "reset_pin"]


class MobileOtpRequest(BaseModel):
    mobile_number: str = Field(..., min_length=8, max_length=20)
    purpose: MobileOtpPurpose
    role: MobileAuthRole | None = None


class MobileOtpRequestResponse(BaseModel):
    success: bool = True
    message: str
    expires_in_seconds: int
    role: MobileAuthRole
    # Only populated in local/dev environments for testing without SMS.
    debug_otp: str | None = None


class MobileOtpVerifyRequest(BaseModel):
    mobile_number: str = Field(..., min_length=8, max_length=20)
    purpose: MobileOtpPurpose
    otp: str = Field(..., min_length=4, max_length=8)
    role: MobileAuthRole | None = None


class MobileOtpVerifyResponse(BaseModel):
    success: bool = True
    otp_session_token: str
    role: MobileAuthRole
    expires_in_seconds: int


class MobilePinSetRequest(BaseModel):
    otp_session_token: str
    pin: str = Field(..., min_length=4, max_length=6)

    @field_validator("pin")
    @classmethod
    def pin_digits_only(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("PIN must contain digits only")
        return value


class MobilePinLoginRequest(BaseModel):
    mobile_number: str = Field(..., min_length=8, max_length=20)
    pin: str = Field(..., min_length=4, max_length=6)
    role: MobileAuthRole | None = None

    @field_validator("pin")
    @classmethod
    def pin_digits_only(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("PIN must contain digits only")
        return value


class MobileAuthUserResponse(BaseModel):
    id: str
    name: str
    email: str | None
    mobile_number: str | None
    role: MobileAuthRole
    member_id: int | None = None


class MobileAuthLoginResponse(BaseModel):
    success: bool = True
    token: str
    user: MobileAuthUserResponse
