"""member management

Revision ID: c3f4a1b29d0e
Revises: 0001_initial_schema
Create Date: 2026-07-24 12:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3f4a1b29d0e"
down_revision: Union[str, Sequence[str], None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("members", "user_id", existing_type=sa.Integer(), nullable=True)

    op.add_column("members", sa.Column("full_name", sa.String(length=120), nullable=True))
    op.add_column("members", sa.Column("mobile_number", sa.String(length=30), nullable=True))
    op.add_column("members", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column("members", sa.Column("gender", sa.String(length=20), nullable=True))
    op.add_column("members", sa.Column("address", sa.Text(), nullable=True))
    op.add_column("members", sa.Column("emergency_contact", sa.String(length=120), nullable=True))
    op.add_column("members", sa.Column("emergency_phone", sa.String(length=30), nullable=True))
    op.add_column("members", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("members", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    op.execute("UPDATE members SET full_name = COALESCE(full_name, 'Unknown Member') WHERE full_name IS NULL")
    op.execute(
        "UPDATE members "
        "SET mobile_number = COALESCE(mobile_number, phone, CONCAT('AUTO-', id::text)) "
        "WHERE mobile_number IS NULL"
    )
    op.execute("UPDATE members SET status = COALESCE(status, 'active') WHERE status IS NULL")

    op.alter_column("members", "full_name", existing_type=sa.String(length=120), nullable=False)
    op.alter_column("members", "mobile_number", existing_type=sa.String(length=30), nullable=False)

    op.create_index(op.f("ix_members_mobile_number"), "members", ["mobile_number"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_members_mobile_number"), table_name="members")

    op.drop_column("members", "deleted_at")
    op.drop_column("members", "notes")
    op.drop_column("members", "emergency_phone")
    op.drop_column("members", "emergency_contact")
    op.drop_column("members", "address")
    op.drop_column("members", "gender")
    op.drop_column("members", "email")
    op.drop_column("members", "mobile_number")
    op.drop_column("members", "full_name")

    op.alter_column("members", "user_id", existing_type=sa.Integer(), nullable=False)
