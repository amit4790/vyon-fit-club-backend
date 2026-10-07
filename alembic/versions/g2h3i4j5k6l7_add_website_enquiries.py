"""add website_enquiries

Revision ID: g2h3i4j5k6l7
Revises: f1a2b3c4d5e6
Create Date: 2026-10-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g2h3i4j5k6l7"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "website_enquiries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("phone_number", sa.String(length=20), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("intent", sa.String(length=40), nullable=False),
        sa.Column("plan_interest", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_website_enquiries_id"), "website_enquiries", ["id"], unique=False)
    op.create_index(
        op.f("ix_website_enquiries_intent"), "website_enquiries", ["intent"], unique=False
    )
    op.create_index(
        op.f("ix_website_enquiries_created_at"),
        "website_enquiries",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_website_enquiries_created_at"), table_name="website_enquiries")
    op.drop_index(op.f("ix_website_enquiries_intent"), table_name="website_enquiries")
    op.drop_index(op.f("ix_website_enquiries_id"), table_name="website_enquiries")
    op.drop_table("website_enquiries")
