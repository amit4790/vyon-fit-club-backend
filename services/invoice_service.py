"""
Invoice service layer for payment and invoice workflows.
"""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
from calendar import monthrange
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

    @staticmethod
    def _add_months(start_date, months: int):
        month = start_date.month - 1 + months
        year = start_date.year + month // 12
        month = month % 12 + 1
        day = min(start_date.day, monthrange(year, month)[1])
        return start_date.replace(year=year, month=month, day=day)

    @staticmethod
    def _format_duration_label(duration_value: int, duration_unit: str) -> str:
        if duration_unit == "months":
            unit_label = "Month" if duration_value == 1 else "Months"
        else:
            unit_label = "Day" if duration_value == 1 else "Days"
        return f"{duration_value} {unit_label}"

    def _resolve_subscription_duration_label(self, subscription) -> str:
        plan = subscription.plan
        if not plan:
            total_days = max((subscription.end_date - subscription.start_date).days + 1, 1)
            return self._format_duration_label(total_days, "days")

        default_end_date = self._add_months(subscription.start_date, plan.duration_months)
        default_end_date = default_end_date - timedelta(days=1)
        if subscription.end_date == default_end_date:
            return plan.duration_label

        total_days = max((subscription.end_date - subscription.start_date).days + 1, 1)
        return self._format_duration_label(total_days, "days")

    @staticmethod
    def _resolve_subscription_name(subscription) -> str:
        plan = subscription.plan
        if not plan:
            return "-"

        name = (plan.name or "").strip()
        duration_label = (plan.duration_label or "").strip()

        if name and duration_label:
            suffix = f" - {duration_label}"
            if name.casefold().endswith(suffix.casefold()):
                trimmed = name[: -len(suffix)].strip()
                if trimmed:
                    return trimmed

        if name:
            return name

        family = (plan.family_name or "").strip().upper()
        variant = (plan.variant_name or "").strip()
        if family and variant:
            return f"{family} - {variant}"
        return family or "-"

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

        # Prefer staff-edited original price; fall back for older clients/records.
        if payload.original_price is not None:
            original_price = self._money(payload.original_price)
        elif invoice.original_price is not None:
            original_price = self._money(invoice.original_price)
        elif subscription.total_amount is not None:
            original_price = self._money(subscription.total_amount)
        else:
            original_price = self._money(subscription.base_price)

        if original_price < Decimal("0.00"):
            raise InvalidPaymentAmountError("Original Membership Price cannot be less than zero")

        final_amount = self._money(payload.final_amount_received)
        amount_paid_today = self._money(payload.amount_paid_today)

        if amount_paid_today > final_amount:
            raise InvalidPaymentAmountError("Amount Paid Today cannot exceed Final Amount Payable")

        # Discount can never be negative when final amount exceeds original price.
        discount_amount = self._money(max(original_price - final_amount, Decimal("0.00")))
        discount_percentage = self._money(
            (discount_amount / original_price) * Decimal("100") if original_price > 0 else Decimal("0")
        )

        GST_RATE = Decimal("0.05")

        # Final amount payable is GST inclusive.
        taxable_amount = self._money(final_amount / (Decimal("1.00") + GST_RATE))
        gst_amount = self._money(final_amount - taxable_amount)
        outstanding_balance = self._money(final_amount - amount_paid_today)
        total_paid = amount_paid_today
        invoice_status = "paid" if outstanding_balance == Decimal("0.00") else "partial"
        pdf_payment_status = "paid" if outstanding_balance == Decimal("0.00") else "partial"

        invoice_number = invoice.invoice_number or self._build_invoice_number(invoice.id)
        subscription_name = self._resolve_subscription_name(subscription)
        subscription_duration = self._resolve_subscription_duration_label(subscription)

        try:
            self.repo.save_payment_snapshot(
                invoice,
                invoice_number=invoice_number,
                original_price=float(original_price),
                final_amount_received=float(final_amount),
                discount_amount=float(discount_amount),
                discount_percentage=float(discount_percentage),
                gst_amount=float(gst_amount),
                amount_paid_today=float(amount_paid_today),
                outstanding_balance=float(outstanding_balance),
                total_paid=float(total_paid),
                payment_mode=payload.payment_mode,
                transaction_reference=payload.transaction_reference,
                payment_date=payload.payment_date,
                counsellor=payload.counsellor,
                notes=payload.notes,
                invoice_pdf_path=invoice.invoice_pdf_path,
                status=invoice_status,
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
                    plan_label=subscription_name,
                    duration_label=subscription_duration,
                    start_date=subscription.start_date,
                    end_date=subscription.end_date,
                    original_price=float(original_price),
                    discount_amount=float(discount_amount),
                    taxable_amount=float(taxable_amount),
                    gst_amount=float(gst_amount),
                    final_amount_payable=float(final_amount),
                    amount_paid=float(amount_paid_today),
                    outstanding_balance=float(outstanding_balance),
                    payment_mode=payload.payment_mode,
                    transaction_reference=payload.transaction_reference,
                    payment_status=pdf_payment_status,
                    remarks=payload.notes,
                    created_by="System",
                    counsellor=payload.counsellor,
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

        if row.invoice_pdf_path:
            path = Path(row.invoice_pdf_path)
            if path.exists():
                return path

        # Render/ephemeral disks wipe stored PDFs on deploy; rebuild from DB snapshot.
        return self._regenerate_invoice_pdf(row)

    def _regenerate_invoice_pdf(self, invoice) -> Path:
        subscription = invoice.subscription
        member = invoice.member
        if not subscription or not member:
            raise InvoiceNotFoundError("Invoice PDF cannot be regenerated")

        GST_RATE = Decimal("0.05")
        final_amount = self._money(
            invoice.final_amount_received if invoice.final_amount_received is not None else invoice.amount
        )
        original_price = self._money(
            invoice.original_price if invoice.original_price is not None else final_amount
        )
        discount_amount = self._money(
            invoice.discount_amount
            if invoice.discount_amount is not None
            else max(original_price - final_amount, Decimal("0.00"))
        )
        taxable_amount = self._money(final_amount / (Decimal("1.00") + GST_RATE))
        gst_amount = self._money(
            invoice.gst_amount if invoice.gst_amount is not None else (final_amount - taxable_amount)
        )
        amount_paid = self._money(
            invoice.amount_paid_today
            if invoice.amount_paid_today is not None
            else (invoice.total_paid if invoice.total_paid is not None else final_amount)
        )
        outstanding_balance = self._money(
            invoice.outstanding_balance
            if invoice.outstanding_balance is not None
            else max(final_amount - amount_paid, Decimal("0.00"))
        )

        payment_date = invoice.payment_date
        if payment_date is None:
            issued_at = invoice.issued_at or invoice.created_at
            payment_date = issued_at.date() if issued_at is not None else datetime.now().date()

        invoice_number = invoice.invoice_number or self._build_invoice_number(invoice.id)
        pdf_payment_status = (
            "paid"
            if outstanding_balance == Decimal("0.00")
            else ("partial" if amount_paid > Decimal("0.00") else (invoice.status or "pending"))
        )

        try:
            pdf_path = self.pdf_service.render_invoice_pdf(
                InvoicePdfPayload(
                    invoice_number=invoice_number,
                    invoice_date=payment_date,
                    invoice_time=datetime.now().strftime("%I:%M %p"),
                    member_id=str(member.id),
                    member_name=member.full_name,
                    member_phone=member.mobile_number,
                    member_email=member.email,
                    plan_label=self._resolve_subscription_name(subscription),
                    duration_label=self._resolve_subscription_duration_label(subscription),
                    start_date=subscription.start_date,
                    end_date=subscription.end_date,
                    original_price=float(original_price),
                    discount_amount=float(discount_amount),
                    taxable_amount=float(taxable_amount),
                    gst_amount=float(gst_amount),
                    final_amount_payable=float(final_amount),
                    amount_paid=float(amount_paid),
                    outstanding_balance=float(outstanding_balance),
                    payment_mode=invoice.payment_mode or "-",
                    transaction_reference=invoice.transaction_reference,
                    payment_status=pdf_payment_status,
                    remarks=invoice.notes,
                    created_by="System",
                    counsellor=invoice.counsellor,
                )
            )
            invoice.invoice_number = invoice_number
            invoice.invoice_pdf_path = pdf_path
            self.db.commit()
            self.db.refresh(invoice)
        except Exception:
            self.db.rollback()
            raise

        path = Path(pdf_path)
        if not path.exists():
            raise InvoiceNotFoundError("Invoice PDF file not found")
        return path

    @staticmethod
    def delivery_results_to_dict(results: list[DeliveryResult]) -> list[dict]:
        return [asdict(item) for item in results]

    def _to_invoice_response(self, row) -> InvoiceResponse:
        member = row.member
        subscription = row.subscription
        # Missing files are regenerated on download; expose URL when payment data exists.
        can_download = (
            bool(row.invoice_pdf_path)
            or row.final_amount_received is not None
            or row.payment_date is not None
        )
        return InvoiceResponse(
            id=row.id,
            invoice_number=row.invoice_number,
            member_id=row.member_id,
            member_name=member.full_name,
            member_email=member.email,
            member_phone=member.phone,
            subscription_id=row.subscription_id,
            plan_label=self._resolve_subscription_name(subscription),
            amount=float(row.amount),
            original_price=float(row.original_price) if row.original_price is not None else None,
            final_amount_received=float(row.final_amount_received) if row.final_amount_received is not None else None,
            discount_amount=float(row.discount_amount) if row.discount_amount is not None else None,
            discount_percentage=float(row.discount_percentage) if row.discount_percentage is not None else None,
            gst_amount=float(row.gst_amount) if row.gst_amount is not None else None,
            amount_paid_today=float(row.amount_paid_today) if row.amount_paid_today is not None else None,
            outstanding_balance=float(row.outstanding_balance) if row.outstanding_balance is not None else None,
            total_paid=float(row.total_paid) if row.total_paid is not None else None,
            payment_mode=row.payment_mode,
            transaction_reference=row.transaction_reference,
            payment_date=row.payment_date,
            counsellor=row.counsellor,
            notes=row.notes,
            invoice_download_url=f"/api/admin/invoices/{row.id}/download" if can_download else None,
            status=row.status,
            issued_at=row.issued_at,
            paid_at=row.paid_at,
        )
