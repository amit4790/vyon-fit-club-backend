"""Add duration and bonus fields to membership_subscriptions

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
Create Date: 2026-08-30 14:40:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("membership_subscriptions", sa.Column("duration_value", sa.Integer(), nullable=True))
    op.add_column("membership_subscriptions", sa.Column("duration_unit", sa.String(length=20), nullable=True))
    op.add_column("membership_subscriptions", sa.Column("bonus_duration_value", sa.Integer(), nullable=True))
    op.add_column("membership_subscriptions", sa.Column("bonus_duration_unit", sa.String(length=20), nullable=True))
    op.add_column("membership_subscriptions", sa.Column("duration_label", sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column("membership_subscriptions", "duration_label")
    op.drop_column("membership_subscriptions", "bonus_duration_unit")
    op.drop_column("membership_subscriptions", "bonus_duration_value")
    op.drop_column("membership_subscriptions", "duration_unit")
    op.drop_column("membership_subscriptions", "duration_value")
