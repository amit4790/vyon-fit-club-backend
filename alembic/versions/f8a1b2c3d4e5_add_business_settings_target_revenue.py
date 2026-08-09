"""Add business_settings table for target revenue

Revision ID: f8a1b2c3d4e5
Revises: e7f8c9d0a123
Create Date: 2026-08-09 20:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f8a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "e7f8c9d0a123"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "business_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("target_revenue", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        sa.text(
            "INSERT INTO business_settings (id, target_revenue) "
            "SELECT 1, 0 WHERE NOT EXISTS (SELECT 1 FROM business_settings WHERE id = 1)"
        )
    )


def downgrade() -> None:
    op.drop_table("business_settings")
