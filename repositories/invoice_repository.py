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

    def list_invoices_for_subscription_ids(self, subscription_ids: list[int]) -> list[Invoice]:
        if not subscription_ids:
            return []

        statement = (
            select(Invoice)
            .where(Invoice.subscription_id.in_(subscription_ids))
            .order_by(Invoice.created_at.desc(), Invoice.id.desc())
        )
        return list(self.db.execute(statement).scalars().all())

    def delete_invoices_for_member(self, member_id: int) -> int:
        """Permanently delete all invoices for a member. Returns deleted count."""
        statement = select(Invoice).where(Invoice.member_id == member_id)
        rows = self.db.execute(statement).scalars().all()
        count = len(rows)
        for row in rows:
            self.db.delete(row)
        self.db.flush()
        return count

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

    def get_report_metrics(self) -> dict[str, int | float]:
        total_invoices = self.db.execute(select(func.count(Invoice.id))).scalar_one()
        paid_invoices = self.db.execute(
            select(func.count(Invoice.id)).where(Invoice.status == "paid")
        ).scalar_one()
        partial_invoices = self.db.execute(
            select(func.count(Invoice.id)).where(Invoice.status == "partial")
        ).scalar_one()
        pending_invoices = self.db.execute(
            select(func.count(Invoice.id)).where(Invoice.status == "pending")
        ).scalar_one()

        collected_revenue = self.db.execute(
            select(func.coalesce(func.sum(Invoice.amount), 0)).where(Invoice.status == "paid")
        ).scalar_one()
        outstanding_expr = func.coalesce(Invoice.outstanding_balance, Invoice.amount)
        outstanding_revenue = self.db.execute(
            select(func.coalesce(func.sum(outstanding_expr), 0)).where(
                Invoice.status.in_(("pending", "partial"))
            )
        ).scalar_one()
        average_invoice_value = self.db.execute(
            select(func.coalesce(func.avg(Invoice.amount), 0))
        ).scalar_one()

        return {
            "total_invoices": int(total_invoices or 0),
            "paid_invoices": int(paid_invoices or 0),
            "pending_invoices": int((pending_invoices or 0) + (partial_invoices or 0)),
            "collected_revenue": float(collected_revenue or 0),
            "outstanding_revenue": float(outstanding_revenue or 0),
            "average_invoice_value": float(average_invoice_value or 0),
        }

    def update_status(self, invoice: Invoice, status: str) -> Invoice:
        invoice.status = status
        if status == "paid":
            if invoice.final_amount_received is not None:
                invoice.total_paid = invoice.final_amount_received
                invoice.amount_paid_today = invoice.final_amount_received
                invoice.outstanding_balance = 0
            invoice.amount = float(invoice.final_amount_received or invoice.amount)
            invoice.paid_at = datetime.now(timezone.utc)
            if invoice.subscription:
                invoice.subscription.payment_status = "paid"
        else:
            invoice.paid_at = None
            if invoice.subscription:
                if status == "partial":
                    invoice.subscription.payment_status = "partial"
                elif invoice.subscription.payment_status == "paid":
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
        amount_paid_today: float,
        outstanding_balance: float,
        total_paid: float,
        payment_mode: str,
        transaction_reference: str | None,
        payment_date,
        counsellor: str | None,
        notes: str | None,
        invoice_pdf_path: str | None,
        status: str,
    ) -> Invoice:
        invoice.invoice_number = invoice_number
        invoice.original_price = original_price
        invoice.final_amount_received = final_amount_received
        invoice.discount_amount = discount_amount
        invoice.discount_percentage = discount_percentage
        invoice.gst_amount = gst_amount
        invoice.amount_paid_today = amount_paid_today
        invoice.outstanding_balance = outstanding_balance
        invoice.total_paid = total_paid
        invoice.payment_mode = payment_mode
        invoice.transaction_reference = transaction_reference
        invoice.payment_date = payment_date
        invoice.counsellor = counsellor
        invoice.notes = notes
        invoice.invoice_pdf_path = invoice_pdf_path
        invoice.amount = final_amount_received
        invoice.status = status
        invoice.paid_at = datetime.now(timezone.utc) if status == "paid" else None

        if invoice.subscription:
            if status == "paid":
                invoice.subscription.payment_status = "paid"
            elif status == "partial":
                invoice.subscription.payment_status = "partial"
            else:
                invoice.subscription.payment_status = "pending"

        self.db.flush()
        self.db.refresh(invoice)
        return invoice
