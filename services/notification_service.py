"""
Dummy notification service for email and SMS integration points.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone


@dataclass
class DeliveryResult:
    channel: str
    target: str | None
    status: str
    message: str
    mock_message_id: str | None


class NotificationService:
    """Notification abstraction with dummy providers for demo environments."""

    @staticmethod
    def _mock_id(channel: str) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        return f"{channel.upper()}-{ts}"

    def _send_email(self, target: str | None, subject: str, body: str) -> DeliveryResult:
        if not target:
            return DeliveryResult(
                channel="email",
                target=None,
                status="skipped",
                message="Email not available for member",
                mock_message_id=None,
            )

        message_id = self._mock_id("email")
        print(f"[DUMMY EMAIL] to={target} subject={subject} message_id={message_id} body={body}")
        return DeliveryResult(
            channel="email",
            target=target,
            status="sent",
            message="Dummy email sent",
            mock_message_id=message_id,
        )

    def _send_sms(self, target: str | None, body: str) -> DeliveryResult:
        if not target:
            return DeliveryResult(
                channel="sms",
                target=None,
                status="skipped",
                message="Phone not available for member",
                mock_message_id=None,
            )

        message_id = self._mock_id("sms")
        print(f"[DUMMY SMS] to={target} message_id={message_id} body={body}")
        return DeliveryResult(
            channel="sms",
            target=target,
            status="sent",
            message="Dummy SMS sent",
            mock_message_id=message_id,
        )

    def send_welcome(
        self,
        *,
        member_name: str,
        email: str | None,
        phone: str | None,
        plan_label: str,
        start_date: date,
        end_date: date,
    ) -> list[DeliveryResult]:
        subject = "Welcome to VYON Fit Club"
        body = (
            f"Hi {member_name}, your {plan_label} membership is active from "
            f"{start_date.isoformat()} to {end_date.isoformat()}."
        )
        return [self._send_email(email, subject, body), self._send_sms(phone, body)]

    def send_invoice_issued(
        self,
        *,
        member_name: str,
        email: str | None,
        phone: str | None,
        invoice_id: int,
        amount: float,
    ) -> list[DeliveryResult]:
        subject = f"Invoice #{invoice_id} generated"
        body = f"Hi {member_name}, invoice #{invoice_id} of INR {amount:.2f} has been generated."
        return [self._send_email(email, subject, body), self._send_sms(phone, body)]

    def send_payment_received(
        self,
        *,
        member_name: str,
        email: str | None,
        phone: str | None,
        invoice_id: int,
        amount: float,
    ) -> list[DeliveryResult]:
        subject = f"Payment received for Invoice #{invoice_id}"
        body = f"Hi {member_name}, payment of INR {amount:.2f} for invoice #{invoice_id} is confirmed."
        return [self._send_email(email, subject, body), self._send_sms(phone, body)]
