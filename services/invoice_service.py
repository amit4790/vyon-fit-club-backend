"""
Invoice service layer for payment and invoice workflows.
"""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from repositories.subscription_repository import SubscriptionRepository
from repositories.invoice_repository import InvoiceRepository
from schemas.invoice import CapturePaymentRequest, InvoiceResponse
from services.invoice_pdf_service import InvoicePdfPayload, InvoicePdfService
from services.notification_service import DeliveryResult, NotificationService


class InvoiceNotFoundError(Exception):
    """Raised when the invoice does not exist."""


class InvalidInvoiceStatusTransitionError(Exception):
    """Raised when a status transition is not allowed."""


class SubscriptionNotFoundError(Exception):
    """Raised when the subscription does not exist."""


class InvalidPaymentAmountError(Exception):
    """Raised when payment amount violates business rules."""


class InvoiceService:
    """Business logic for invoice querying and payment status updates."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = InvoiceRepository(db)
        self.subscription_repo = SubscriptionRepository(db)
        self.notifier = NotificationService()
        self.pdf_service = InvoicePdfService()

    @staticmethod
    def _money(value: Decimal | float | int) -> Decimal:
        return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _build_invoice_number(invoice_id: int) -> str:
        return f"VYON-{invoice_id:06d}"

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

    def capture_payment_for_subscription(
        self,
        *,
        subscription_id: int,
        payload: CapturePaymentRequest,
    ) -> InvoiceResponse:
        subscription = self.subscription_repo.get_subscription_by_id(subscription_id)
        if not subscription:
            raise SubscriptionNotFoundError("Subscription not found")

        invoice = self.repo.get_latest_invoice_by_subscription_id(subscription_id)
        if not invoice:
            raise InvoiceNotFoundError("No invoice found for this subscription")

        original_price = self._money(subscription.base_price)
        final_amount = self._money(payload.final_amount_received)

        if final_amount > original_price:
            raise InvalidPaymentAmountError("Final Amount Received cannot exceed Original Membership Price")

        discount_amount = self._money(original_price - final_amount)
        discount_percentage = self._money(
            (discount_amount / original_price) * Decimal("100") if original_price > 0 else Decimal("0")
        )
        gst_amount = self._money(final_amount * Decimal("0.05"))
        total_paid = self._money(final_amount + gst_amount)

        invoice_number = invoice.invoice_number or self._build_invoice_number(invoice.id)

        try:
            self.repo.save_payment_snapshot(
                invoice,
                invoice_number=invoice_number,
                original_price=float(original_price),
                final_amount_received=float(final_amount),
                discount_amount=float(discount_amount),
                discount_percentage=float(discount_percentage),
                gst_amount=float(gst_amount),
                total_paid=float(total_paid),
                payment_mode=payload.payment_mode,
                transaction_reference=payload.transaction_reference,
                payment_date=payload.payment_date,
                notes=payload.notes,
                invoice_pdf_path=invoice.invoice_pdf_path,
            )

            pdf_path = self.pdf_service.render_invoice_pdf(
                InvoicePdfPayload(
                    invoice_number=invoice_number,
                    invoice_date=payload.payment_date,
                    invoice_time=datetime.now().strftime("%I:%M %p"),
                    member_id=str(subscription.member_id),
                    member_name=subscription.member.full_name,
                    member_phone=subscription.member.mobile_number,
                    member_email=subscription.member.email,
                    plan_label=subscription.plan.name,
                    duration_label=subscription.plan.duration_label,
                    start_date=subscription.start_date,
                    end_date=subscription.end_date,
                    original_price=float(original_price),
                    discount_amount=float(discount_amount),
                    taxable_amount=float(final_amount),
                    gst_amount=float(gst_amount),
                    total_paid=float(total_paid),
                    payment_mode=payload.payment_mode,
                    transaction_reference=payload.transaction_reference,
                    payment_status=invoice.status,
                    remarks=payload.notes,
                    created_by="System",
                    counsellor="System",
                )
            )

            invoice.invoice_pdf_path = pdf_path
            self.db.commit()
            self.db.refresh(invoice)
        except Exception:
            self.db.rollback()
            raise

        return self._to_invoice_response(invoice)

    def get_invoice_pdf_path(self, invoice_id: int) -> Path:
        row = self.repo.get_invoice_by_id(invoice_id)
        if not row:
            raise InvoiceNotFoundError("Invoice not found")

        if not row.invoice_pdf_path:
            raise InvoiceNotFoundError("Invoice PDF is not generated yet")

        path = Path(row.invoice_pdf_path)
        if not path.exists():
            raise InvoiceNotFoundError("Invoice PDF file not found")

        return path

    @staticmethod
    def delivery_results_to_dict(results: list[DeliveryResult]) -> list[dict]:
        return [asdict(item) for item in results]

    @staticmethod
    def _to_invoice_response(row) -> InvoiceResponse:
        member = row.member
        subscription = row.subscription
        return InvoiceResponse(
            id=row.id,
            invoice_number=row.invoice_number,
            member_id=row.member_id,
            member_name=member.full_name,
            member_email=member.email,
            member_phone=member.phone,
            subscription_id=row.subscription_id,
            plan_label=subscription.plan.name,
            amount=float(row.amount),
            original_price=float(row.original_price) if row.original_price is not None else None,
            final_amount_received=float(row.final_amount_received) if row.final_amount_received is not None else None,
            discount_amount=float(row.discount_amount) if row.discount_amount is not None else None,
            discount_percentage=float(row.discount_percentage) if row.discount_percentage is not None else None,
            gst_amount=float(row.gst_amount) if row.gst_amount is not None else None,
            total_paid=float(row.total_paid) if row.total_paid is not None else None,
            payment_mode=row.payment_mode,
            transaction_reference=row.transaction_reference,
            payment_date=row.payment_date,
            notes=row.notes,
            invoice_download_url=f"/api/admin/invoices/{row.id}/download" if row.invoice_pdf_path else None,
            status=row.status,
            issued_at=row.issued_at,
            paid_at=row.paid_at,
        )
