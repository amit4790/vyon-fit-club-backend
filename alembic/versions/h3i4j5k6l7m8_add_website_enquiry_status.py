"""add website enquiry status

Revision ID: h3i4j5k6l7m8
Revises: g2h3i4j5k6l7
Create Date: 2026-10-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "h3i4j5k6l7m8"
down_revision: Union[str, Sequence[str], None] = "g2h3i4j5k6l7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "website_enquiries",
        sa.Column("status", sa.String(length=20), server_default="new", nullable=False),
    )
    op.create_index(
        op.f("ix_website_enquiries_status"),
        "website_enquiries",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_website_enquiries_status"), table_name="website_enquiries")
    op.drop_column("website_enquiries", "status")
