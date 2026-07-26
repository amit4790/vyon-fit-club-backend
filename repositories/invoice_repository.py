"""
Invoice repository for payment persistence operations.
"""

from datetime import datetime, timezone

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload

from models import Invoice, MembershipSubscription


class InvoiceRepository:
    """Repository for invoice queries and mutations."""

    def __init__(self, db: Session):
        self.db = db

    def create_invoice(self, invoice: Invoice) -> Invoice:
        self.db.add(invoice)
        self.db.flush()
        self.db.refresh(invoice)
        return invoice

    def get_invoice_by_id(self, invoice_id: int) -> Invoice | None:
        statement = (
            select(Invoice)
            .options(
                joinedload(Invoice.member),
                joinedload(Invoice.subscription).joinedload(MembershipSubscription.plan),
            )
            .where(Invoice.id == invoice_id)
        )
        return self.db.execute(statement).scalar_one_or_none()

    def get_latest_invoice_by_subscription_id(self, subscription_id: int) -> Invoice | None:
        statement = (
            select(Invoice)
            .options(
                joinedload(Invoice.member),
                joinedload(Invoice.subscription).joinedload(MembershipSubscription.plan),
            )
            .where(Invoice.subscription_id == subscription_id)
            .order_by(Invoice.created_at.desc(), Invoice.id.desc())
            .limit(1)
        )
        return self.db.execute(statement).scalar_one_or_none()

    def list_invoices(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None,
        member_id: int | None,
    ) -> tuple[list[Invoice], int]:
        query: Select[tuple[Invoice]] = select(Invoice).options(
            joinedload(Invoice.member),
            joinedload(Invoice.subscription).joinedload(MembershipSubscription.plan),
        )
        count_query = select(func.count(Invoice.id))

        if status:
            query = query.where(Invoice.status == status)
            count_query = count_query.where(Invoice.status == status)

        if member_id is not None:
            query = query.where(Invoice.member_id == member_id)
            count_query = count_query.where(Invoice.member_id == member_id)

        total_items = self.db.execute(count_query).scalar_one()
        items = (
            self.db.execute(
                query.order_by(Invoice.issued_at.desc(), Invoice.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
        return items, total_items

    def update_status(self, invoice: Invoice, status: str) -> Invoice:
        invoice.status = status
        if status == "paid":
            invoice.paid_at = datetime.now(timezone.utc)
            if invoice.subscription:
                invoice.subscription.payment_status = "paid"
        else:
            invoice.paid_at = None
            if invoice.subscription and invoice.subscription.payment_status == "paid":
                invoice.subscription.payment_status = "pending"

        self.db.flush()
        self.db.refresh(invoice)
        return invoice

    def save_payment_snapshot(
        self,
        invoice: Invoice,
        *,
        invoice_number: str,
        original_price: float,
        final_amount_received: float,
        discount_amount: float,
        discount_percentage: float,
        gst_amount: float,
        total_paid: float,
        payment_mode: str,
        transaction_reference: str | None,
        payment_date,
        notes: str | None,
        invoice_pdf_path: str | None,
    ) -> Invoice:
        invoice.invoice_number = invoice_number
        invoice.original_price = original_price
        invoice.final_amount_received = final_amount_received
        invoice.discount_amount = discount_amount
        invoice.discount_percentage = discount_percentage
        invoice.gst_amount = gst_amount
        invoice.total_paid = total_paid
        invoice.payment_mode = payment_mode
        invoice.transaction_reference = transaction_reference
        invoice.payment_date = payment_date
        invoice.notes = notes
        invoice.invoice_pdf_path = invoice_pdf_path
        invoice.amount = total_paid
        invoice.status = "paid"
        invoice.paid_at = datetime.now(timezone.utc)

        if invoice.subscription:
            invoice.subscription.payment_status = "paid"

        self.db.flush()
        self.db.refresh(invoice)
        return invoice
