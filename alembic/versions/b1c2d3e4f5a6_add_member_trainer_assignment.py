"""Add trainer assignment columns to members

Revision ID: b1c2d3e4f5a6
Revises: a9b8c7d6e5f4
Create Date: 2026-08-16 12:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a9b8c7d6e5f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("members", sa.Column("trainer_id", sa.Integer(), nullable=True))
    op.add_column("members", sa.Column("trainer_assignment_source", sa.String(length=20), nullable=True))
    op.add_column("members", sa.Column("trainer_assigned_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_members_trainer_id"), "members", ["trainer_id"], unique=False)
    op.create_foreign_key(
        "fk_members_trainer_id_users",
        "members",
        "users",
        ["trainer_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_members_trainer_id_users", "members", type_="foreignkey")
    op.drop_index(op.f("ix_members_trainer_id"), table_name="members")
    op.drop_column("members", "trainer_assigned_at")
    op.drop_column("members", "trainer_assignment_source")
    op.drop_column("members", "trainer_id")
