"""Mobile OTP + PIN authentication for members and trainers."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from core.config import settings
from core.roles import UserRole
from core.security import hash_password, verify_password
from models import Member, OtpChallenge, User
from schemas.auth import UserInfo
from schemas.mobile_auth import (
    MobileAuthLoginResponse,
    MobileAuthUserResponse,
    MobileOtpRequestResponse,
    MobileOtpVerifyResponse,
)
from services.auth_service import AuthService, InvalidTokenError, TokenExpiredError

logger = logging.getLogger(__name__)

OTP_SESSION_TOKEN_TYPE = "otp_session"
PURPOSES = {"activate", "reset_pin"}


class MobileAuthError(Exception):
    """Base mobile auth error with HTTP-friendly message."""


class MobileAuthNotFoundError(MobileAuthError):
    pass


class MobileAuthConflictError(MobileAuthError):
    pass


class MobileAuthValidationError(MobileAuthError):
    pass


class MobileAuthForbiddenError(MobileAuthError):
    pass


@dataclass
class ResolvedSubject:
    role: UserRole
    subject_type: str  # member | trainer
    subject_id: int
    mobile_number: str
    display_name: str
    user: User | None
    member: Member | None


class MobileAuthService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def normalize_mobile(raw: str) -> str:
        digits = "".join(ch for ch in (raw or "") if ch.isdigit())
        if len(digits) > 10 and digits.startswith("91"):
            digits = digits[-10:]
        if len(digits) < 8:
            raise MobileAuthValidationError("Enter a valid mobile number")
        return digits

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _find_member(self, mobile: str) -> Member | None:
        return self.db.execute(
            select(Member).where(
                Member.deleted_at.is_(None),
                or_(
                    Member.mobile_number == mobile,
                    Member.phone == mobile,
                ),
            )
        ).scalar_one_or_none()

    def _find_trainer(self, mobile: str) -> User | None:
        return self.db.execute(
            select(User).where(
                User.role == UserRole.TRAINER,
                User.phone_number == mobile,
            )
        ).scalar_one_or_none()

    def resolve_subject(self, mobile: str, role: str | None) -> ResolvedSubject:
        member = self._find_member(mobile)
        trainer = self._find_trainer(mobile)

        if role == UserRole.MEMBER:
            if not member:
                raise MobileAuthNotFoundError("No member found for this mobile number")
            user = member.user
            return ResolvedSubject(
                role=UserRole.MEMBER,
                subject_type="member",
                subject_id=member.id,
                mobile_number=mobile,
                display_name=member.full_name,
                user=user,
                member=member,
            )

        if role == UserRole.TRAINER:
            if not trainer:
                raise MobileAuthNotFoundError("No trainer found for this mobile number")
            return ResolvedSubject(
                role=UserRole.TRAINER,
                subject_type="trainer",
                subject_id=trainer.id,
                mobile_number=mobile,
                display_name=trainer.full_name,
                user=trainer,
                member=None,
            )

        if member and trainer:
            raise MobileAuthConflictError(
                "This mobile number matches both a member and a trainer. Pass role=MEMBER or role=TRAINER."
            )
        if member:
            return self.resolve_subject(mobile, UserRole.MEMBER)
        if trainer:
            return self.resolve_subject(mobile, UserRole.TRAINER)
        raise MobileAuthNotFoundError("No member or trainer found for this mobile number")

    def _has_pin(self, user: User | None) -> bool:
        return bool(user and user.pin_hash)

    def request_otp(self, *, mobile_number: str, purpose: str, role: str | None) -> MobileOtpRequestResponse:
        if purpose not in PURPOSES:
            raise MobileAuthValidationError("Invalid OTP purpose")

        mobile = self.normalize_mobile(mobile_number)
        subject = self.resolve_subject(mobile, role)

        if subject.role == UserRole.MEMBER:
            if subject.member and subject.member.status and subject.member.status.lower() == "inactive":
                raise MobileAuthForbiddenError("This membership is inactive. Contact the gym.")
        if subject.role == UserRole.TRAINER and subject.user and not subject.user.is_active:
            raise MobileAuthForbiddenError("This trainer account is inactive.")

        has_pin = self._has_pin(subject.user)
        if purpose == "activate" and has_pin:
            raise MobileAuthValidationError("PIN already set. Use reset_pin or sign in with PIN.")
        if purpose == "reset_pin" and not has_pin:
            raise MobileAuthValidationError("No PIN is set yet. Use activate instead.")

        otp = f"{secrets.randbelow(1_000_000):06d}"
        challenge = OtpChallenge(
            mobile_number=mobile,
            purpose=purpose,
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
            role=subject.role.value,
            code_hash=hash_password(otp),
            expires_at=self._now() + timedelta(seconds=settings.mobile_otp_ttl_seconds),
            attempt_count=0,
        )
        self.db.add(challenge)
        self.db.commit()

        # SMS provider not wired yet — log OTP only in local environments.
        if settings.is_local_environment:
            logger.info(
                "Mobile OTP issued (local debug)",
                extra={"mobile": mobile, "purpose": purpose, "role": subject.role.value, "otp": otp},
            )

        return MobileOtpRequestResponse(
            success=True,
            message="OTP sent" if not settings.is_local_environment else "OTP generated (debug)",
            expires_in_seconds=settings.mobile_otp_ttl_seconds,
            role=subject.role.value,  # type: ignore[arg-type]
            debug_otp=otp if settings.is_local_environment else None,
        )

    def _latest_open_challenge(self, mobile: str, purpose: str, role: str | None) -> OtpChallenge:
        statement = (
            select(OtpChallenge)
            .where(
                OtpChallenge.mobile_number == mobile,
                OtpChallenge.purpose == purpose,
                OtpChallenge.consumed_at.is_(None),
            )
            .order_by(OtpChallenge.id.desc())
        )
        if role:
            statement = statement.where(OtpChallenge.role == role)
        challenge = self.db.execute(statement).scalars().first()
        if not challenge:
            raise MobileAuthValidationError("No active OTP. Request a new code.")
        if self._as_utc(challenge.expires_at) < self._now():
            raise MobileAuthValidationError("OTP expired. Request a new code.")
        return challenge

    def verify_otp(
        self,
        *,
        mobile_number: str,
        purpose: str,
        otp: str,
        role: str | None,
    ) -> MobileOtpVerifyResponse:
        if purpose not in PURPOSES:
            raise MobileAuthValidationError("Invalid OTP purpose")

        mobile = self.normalize_mobile(mobile_number)
        challenge = self._latest_open_challenge(mobile, purpose, role)

        if challenge.attempt_count >= settings.mobile_otp_max_verify_attempts:
            raise MobileAuthForbiddenError("Too many invalid OTP attempts. Request a new code.")

        if not verify_password(otp.strip(), challenge.code_hash):
            challenge.attempt_count += 1
            self.db.commit()
            raise MobileAuthValidationError("Invalid OTP")

        challenge.consumed_at = self._now()
        self.db.commit()

        expires_minutes = settings.mobile_otp_session_ttl_minutes
        expires_at = self._now() + timedelta(minutes=expires_minutes)
        payload = {
            "token_type": OTP_SESSION_TOKEN_TYPE,
            "purpose": purpose,
            "subject_type": challenge.subject_type,
            "subject_id": challenge.subject_id,
            "role": challenge.role,
            "mobile_number": mobile,
            "iat": self._now(),
            "exp": expires_at,
        }
        token = jwt.encode(payload, settings.effective_jwt_secret_key, algorithm=settings.jwt_algorithm)
        return MobileOtpVerifyResponse(
            success=True,
            otp_session_token=token,
            role=challenge.role,  # type: ignore[arg-type]
            expires_in_seconds=expires_minutes * 60,
        )

    def _decode_otp_session(self, token: str) -> dict:
        try:
            payload = jwt.decode(
                token,
                settings.effective_jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
        except ExpiredSignatureError as exc:
            raise TokenExpiredError("OTP session expired. Verify OTP again.") from exc
        except JWTError as exc:
            raise InvalidTokenError("Invalid OTP session") from exc

        if payload.get("token_type") != OTP_SESSION_TOKEN_TYPE:
            raise InvalidTokenError("Invalid OTP session type")
        required = ("purpose", "subject_type", "subject_id", "role", "mobile_number")
        if any(not payload.get(key) for key in required):
            raise InvalidTokenError("OTP session is missing claims")
        return payload

    def _ensure_member_user(self, member: Member, mobile: str) -> User:
        if member.user_id and member.user:
            user = member.user
            if not user.phone_number:
                user.phone_number = mobile
            return user

        email = (member.email or "").strip().lower()
        if email:
            existing = self.db.execute(select(User).where(User.email == email)).scalar_one_or_none()
            if existing:
                email = f"member-{member.id}@mobile.vyon.local"
        else:
            email = f"member-{member.id}@mobile.vyon.local"

        phone_conflict = self.db.execute(select(User).where(User.phone_number == mobile)).scalar_one_or_none()
        if phone_conflict and phone_conflict.role != UserRole.MEMBER:
            raise MobileAuthConflictError("This mobile number is already linked to another account")

        user = User(
            full_name=member.full_name,
            email=email,
            phone_number=mobile,
            role=UserRole.MEMBER,
            is_active=True,
            password_hash=hash_password(secrets.token_urlsafe(32)),
        )
        self.db.add(user)
        self.db.flush()
        member.user_id = user.id
        return user

    def set_pin(self, *, otp_session_token: str, pin: str) -> MobileAuthLoginResponse:
        if not pin.isdigit() or not (
            settings.mobile_pin_min_length <= len(pin) <= settings.mobile_pin_max_length
        ):
            raise MobileAuthValidationError(
                f"PIN must be {settings.mobile_pin_min_length}-{settings.mobile_pin_max_length} digits"
            )

        payload = self._decode_otp_session(otp_session_token)
        purpose = payload["purpose"]
        role = UserRole(payload["role"])
        mobile = payload["mobile_number"]

        if role == UserRole.MEMBER:
            member = self.db.get(Member, int(payload["subject_id"]))
            if not member or member.deleted_at is not None:
                raise MobileAuthNotFoundError("Member not found")
            user = self._ensure_member_user(member, mobile)
        elif role == UserRole.TRAINER:
            user = self.db.get(User, int(payload["subject_id"]))
            if not user or user.role != UserRole.TRAINER:
                raise MobileAuthNotFoundError("Trainer not found")
            if not user.phone_number:
                user.phone_number = mobile
        else:
            raise MobileAuthForbiddenError("Unsupported role for mobile PIN")

        if purpose == "activate" and user.pin_hash:
            raise MobileAuthValidationError("PIN already set")
        if purpose == "reset_pin" and not user.pin_hash:
            raise MobileAuthValidationError("No PIN to reset")

        user.pin_hash = hash_password(pin)
        user.pin_updated_at = self._now()
        user.pin_failed_attempts = 0
        user.pin_locked_until = None
        self.db.commit()
        self.db.refresh(user)

        return self._login_response(user)

    def login_with_pin(
        self,
        *,
        mobile_number: str,
        pin: str,
        role: str | None,
    ) -> MobileAuthLoginResponse:
        mobile = self.normalize_mobile(mobile_number)
        subject = self.resolve_subject(mobile, role)
        user = subject.user
        if not user or not user.pin_hash:
            raise MobileAuthValidationError("PIN is not set. Activate with OTP first.")
        if not user.is_active:
            raise MobileAuthForbiddenError("Account is inactive")

        if user.pin_locked_until and self._as_utc(user.pin_locked_until) > self._now():
            raise MobileAuthForbiddenError("PIN temporarily locked. Try again later or reset with OTP.")

        if not verify_password(pin, user.pin_hash):
            user.pin_failed_attempts = (user.pin_failed_attempts or 0) + 1
            if user.pin_failed_attempts >= settings.mobile_pin_max_failed_attempts:
                user.pin_locked_until = self._now() + timedelta(minutes=settings.mobile_pin_lockout_minutes)
                user.pin_failed_attempts = 0
            self.db.commit()
            raise MobileAuthValidationError("Invalid mobile number or PIN")

        user.pin_failed_attempts = 0
        user.pin_locked_until = None
        self.db.commit()
        self.db.refresh(user)
        return self._login_response(user)

    def _login_response(self, user: User) -> MobileAuthLoginResponse:
        member_id = None
        if user.role == UserRole.MEMBER:
            member = self.db.execute(
                select(Member).where(Member.user_id == user.id, Member.deleted_at.is_(None))
            ).scalar_one_or_none()
            if member:
                member_id = member.id

        user_info = UserInfo(
            id=str(user.id),
            name=user.full_name,
            email=user.email,
            role=UserRole(user.role),
        )
        token = AuthService.create_access_token(user_info)
        return MobileAuthLoginResponse(
            success=True,
            token=token,
            user=MobileAuthUserResponse(
                id=str(user.id),
                name=user.full_name,
                email=user.email,
                mobile_number=user.phone_number,
                role=user.role,  # type: ignore[arg-type]
                member_id=member_id,
            ),
        )
