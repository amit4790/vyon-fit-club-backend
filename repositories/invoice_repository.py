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
        else:
            invoice.paid_at = None

        self.db.flush()
        self.db.refresh(invoice)
        return invoice
