"""Mobile OTP + PIN authentication routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from schemas.mobile_auth import (
    MobileAuthLoginResponse,
    MobileOtpRequest,
    MobileOtpRequestResponse,
    MobileOtpVerifyRequest,
    MobileOtpVerifyResponse,
    MobilePinLoginRequest,
    MobilePinSetRequest,
)
from services.auth_service import InvalidTokenError, TokenExpiredError
from services.mobile_auth_service import (
    MobileAuthConflictError,
    MobileAuthForbiddenError,
    MobileAuthNotFoundError,
    MobileAuthService,
    MobileAuthValidationError,
)

router = APIRouter(prefix="/api/auth/mobile", tags=["Mobile Authentication"])

_CLIENT_ERRORS = (
    MobileAuthNotFoundError,
    MobileAuthConflictError,
    MobileAuthForbiddenError,
    MobileAuthValidationError,
    TokenExpiredError,
    InvalidTokenError,
)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, MobileAuthNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, MobileAuthConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, MobileAuthForbiddenError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, (MobileAuthValidationError, TokenExpiredError, InvalidTokenError)):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Mobile auth failed")


@router.post("/otp/request", response_model=MobileOtpRequestResponse)
def request_mobile_otp(payload: MobileOtpRequest, db: Session = Depends(get_db)) -> MobileOtpRequestResponse:
    service = MobileAuthService(db)
    try:
        return service.request_otp(
            mobile_number=payload.mobile_number,
            purpose=payload.purpose,
            role=payload.role,
        )
    except _CLIENT_ERRORS as exc:
        raise _http_error(exc) from exc


@router.post("/otp/verify", response_model=MobileOtpVerifyResponse)
def verify_mobile_otp(payload: MobileOtpVerifyRequest, db: Session = Depends(get_db)) -> MobileOtpVerifyResponse:
    service = MobileAuthService(db)
    try:
        return service.verify_otp(
            mobile_number=payload.mobile_number,
            purpose=payload.purpose,
            otp=payload.otp,
            role=payload.role,
        )
    except _CLIENT_ERRORS as exc:
        raise _http_error(exc) from exc


@router.post("/pin/set", response_model=MobileAuthLoginResponse)
def set_mobile_pin(payload: MobilePinSetRequest, db: Session = Depends(get_db)) -> MobileAuthLoginResponse:
    service = MobileAuthService(db)
    try:
        return service.set_pin(otp_session_token=payload.otp_session_token, pin=payload.pin)
    except _CLIENT_ERRORS as exc:
        raise _http_error(exc) from exc


@router.post("/login", response_model=MobileAuthLoginResponse)
def mobile_pin_login(payload: MobilePinLoginRequest, db: Session = Depends(get_db)) -> MobileAuthLoginResponse:
    service = MobileAuthService(db)
    try:
        return service.login_with_pin(
            mobile_number=payload.mobile_number,
            pin=payload.pin,
            role=payload.role,
        )
    except _CLIENT_ERRORS as exc:
        raise _http_error(exc) from exc
