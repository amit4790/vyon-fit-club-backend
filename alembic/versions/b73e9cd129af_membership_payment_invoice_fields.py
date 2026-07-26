"""membership payment invoice fields

Revision ID: b73e9cd129af
Revises: f2a9b58d1c77
Create Date: 2026-07-25 00:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b73e9cd129af"
down_revision: Union[str, Sequence[str], None] = "f2a9b58d1c77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "membership_subscriptions",
        sa.Column("payment_status", sa.String(length=20), nullable=False, server_default="pending"),
    )

    op.add_column("invoices", sa.Column("invoice_number", sa.String(length=40), nullable=True))
    op.add_column("invoices", sa.Column("original_price", sa.Numeric(10, 2), nullable=True))
    op.add_column("invoices", sa.Column("final_amount_received", sa.Numeric(10, 2), nullable=True))
    op.add_column("invoices", sa.Column("discount_amount", sa.Numeric(10, 2), nullable=True))
    op.add_column("invoices", sa.Column("discount_percentage", sa.Numeric(5, 2), nullable=True))
    op.add_column("invoices", sa.Column("gst_amount", sa.Numeric(10, 2), nullable=True))
    op.add_column("invoices", sa.Column("total_paid", sa.Numeric(10, 2), nullable=True))
    op.add_column("invoices", sa.Column("payment_mode", sa.String(length=30), nullable=True))
    op.add_column("invoices", sa.Column("transaction_reference", sa.String(length=120), nullable=True))
    op.add_column("invoices", sa.Column("payment_date", sa.Date(), nullable=True))
    op.add_column("invoices", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("invoices", sa.Column("invoice_pdf_path", sa.String(length=500), nullable=True))

    op.create_index(op.f("ix_invoices_invoice_number"), "invoices", ["invoice_number"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_invoices_invoice_number"), table_name="invoices")

    op.drop_column("invoices", "invoice_pdf_path")
    op.drop_column("invoices", "notes")
    op.drop_column("invoices", "payment_date")
    op.drop_column("invoices", "transaction_reference")
    op.drop_column("invoices", "payment_mode")
    op.drop_column("invoices", "total_paid")
    op.drop_column("invoices", "gst_amount")
    op.drop_column("invoices", "discount_percentage")
    op.drop_column("invoices", "discount_amount")
    op.drop_column("invoices", "final_amount_received")
    op.drop_column("invoices", "original_price")
    op.drop_column("invoices", "invoice_number")

    op.drop_column("membership_subscriptions", "payment_status")
