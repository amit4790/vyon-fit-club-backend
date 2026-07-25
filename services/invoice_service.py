"""
Invoice service layer for payment and invoice workflows.
"""

from __future__ import annotations

from dataclasses import asdict

from sqlalchemy.orm import Session

from repositories.invoice_repository import InvoiceRepository
from schemas.invoice import InvoiceResponse
from services.notification_service import DeliveryResult, NotificationService


class InvoiceNotFoundError(Exception):
    """Raised when the invoice does not exist."""


class InvalidInvoiceStatusTransitionError(Exception):
    """Raised when a status transition is not allowed."""


class InvoiceService:
    """Business logic for invoice querying and payment status updates."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = InvoiceRepository(db)
        self.notifier = NotificationService()

    def list_invoices(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None,
        member_id: int | None,
    ) -> tuple[list[InvoiceResponse], int]:
        rows, total_items = self.repo.list_invoices(
            page=page,
            page_size=page_size,
            status=status,
            member_id=member_id,
        )
        return [self._to_invoice_response(row) for row in rows], total_items

    def get_invoice(self, invoice_id: int) -> InvoiceResponse:
        row = self.repo.get_invoice_by_id(invoice_id)
        if not row:
            raise InvoiceNotFoundError("Invoice not found")
        return self._to_invoice_response(row)

    def update_invoice_status(self, invoice_id: int, status: str) -> tuple[InvoiceResponse, list[DeliveryResult]]:
        row = self.repo.get_invoice_by_id(invoice_id)
        if not row:
            raise InvoiceNotFoundError("Invoice not found")

        if row.status == "paid" and status != "paid":
            raise InvalidInvoiceStatusTransitionError("Paid invoice status cannot be changed")

        notifications: list[DeliveryResult] = []
        try:
            updated = self.repo.update_status(row, status)
            self.db.commit()
            self.db.refresh(updated)
        except Exception:
            self.db.rollback()
            raise

        if updated.status == "paid":
            notifications = self.notifier.send_payment_received(
                member_name=updated.member.full_name,
                email=updated.member.email,
                phone=updated.member.phone,
                invoice_id=updated.id,
                amount=float(updated.amount),
            )

        return self._to_invoice_response(updated), notifications

    def resend_invoice(self, invoice_id: int) -> tuple[InvoiceResponse, list[DeliveryResult]]:
        row = self.repo.get_invoice_by_id(invoice_id)
        if not row:
            raise InvoiceNotFoundError("Invoice not found")

        notifications = self.notifier.send_invoice_issued(
            member_name=row.member.full_name,
            email=row.member.email,
            phone=row.member.phone,
            invoice_id=row.id,
            amount=float(row.amount),
        )
        return self._to_invoice_response(row), notifications

    @staticmethod
    def delivery_results_to_dict(results: list[DeliveryResult]) -> list[dict]:
        return [asdict(item) for item in results]

    @staticmethod
    def _to_invoice_response(row) -> InvoiceResponse:
        member = row.member
        subscription = row.subscription
        return InvoiceResponse(
            id=row.id,
            member_id=row.member_id,
            member_name=member.full_name,
            member_email=member.email,
            member_phone=member.phone,
            subscription_id=row.subscription_id,
            plan_label=subscription.plan.name,
            amount=float(row.amount),
            status=row.status,
            issued_at=row.issued_at,
            paid_at=row.paid_at,
        )
