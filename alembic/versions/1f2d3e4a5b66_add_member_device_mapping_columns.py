"""Add member device mapping columns

Revision ID: 1f2d3e4a5b66
Revises: 09c892bbcc7f
Create Date: 2026-08-01 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1f2d3e4a5b66"
down_revision: Union[str, Sequence[str], None] = "09c892bbcc7f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("members", sa.Column("device_user_id", sa.String(length=64), nullable=True))
    op.add_column("members", sa.Column("device_uid", sa.Integer(), nullable=True))
    op.add_column("members", sa.Column("device_card", sa.Integer(), nullable=True))
    op.add_column(
        "members",
        sa.Column("device_sync_status", sa.String(length=20), nullable=False, server_default="unlinked"),
    )
    op.add_column("members", sa.Column("last_device_sync_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index(op.f("ix_members_device_user_id"), "members", ["device_user_id"], unique=True)
    op.create_index(op.f("ix_members_device_uid"), "members", ["device_uid"], unique=True)

    op.alter_column("members", "device_sync_status", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_members_device_uid"), table_name="members")
    op.drop_index(op.f("ix_members_device_user_id"), table_name="members")

    op.drop_column("members", "last_device_sync_at")
    op.drop_column("members", "device_sync_status")
    op.drop_column("members", "device_card")
    op.drop_column("members", "device_uid")
    op.drop_column("members", "device_user_id")
