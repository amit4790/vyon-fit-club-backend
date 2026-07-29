"""add partial payment and counsellor to invoices

Revision ID: 9e4c21fd7a11
Revises: b73e9cd129af
Create Date: 2026-07-29 00:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9e4c21fd7a11"
down_revision: Union[str, Sequence[str], None] = "b73e9cd129af"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("amount_paid_today", sa.Numeric(10, 2), nullable=True))
    op.add_column("invoices", sa.Column("outstanding_balance", sa.Numeric(10, 2), nullable=True))
    op.add_column("invoices", sa.Column("counsellor", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("invoices", "counsellor")
    op.drop_column("invoices", "outstanding_balance")
    op.drop_column("invoices", "amount_paid_today")