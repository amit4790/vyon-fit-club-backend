"""Add members.device_access_enabled for targeted expiry device sync.

Revision ID: m8n9o0p1q2r3
Revises: l7m8n9o0p1q2
Create Date: 2026-11-26

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "m8n9o0p1q2r3"
down_revision: Union[str, Sequence[str], None] = "l7m8n9o0p1q2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "members",
        sa.Column("device_access_enabled", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("members", "device_access_enabled")