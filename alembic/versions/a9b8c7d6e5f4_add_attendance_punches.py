"""Add attendance_punches table

Revision ID: a9b8c7d6e5f4
Revises: f8a1b2c3d4e5
Create Date: 2026-08-16 10:40:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a9b8c7d6e5f4"
down_revision: Union[str, Sequence[str], None] = "f8a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attendance_punches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_serial", sa.String(length=100), nullable=False),
        sa.Column("pin", sa.Integer(), nullable=False),
        sa.Column("person_type", sa.String(length=20), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("punched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_line", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "device_serial",
            "pin",
            "punched_at",
            name="uq_attendance_punches_device_pin_time",
        ),
    )
    op.create_index(op.f("ix_attendance_punches_id"), "attendance_punches", ["id"], unique=False)
    op.create_index(op.f("ix_attendance_punches_device_serial"), "attendance_punches", ["device_serial"], unique=False)
    op.create_index(op.f("ix_attendance_punches_pin"), "attendance_punches", ["pin"], unique=False)
    op.create_index(op.f("ix_attendance_punches_person_type"), "attendance_punches", ["person_type"], unique=False)
    op.create_index(op.f("ix_attendance_punches_person_id"), "attendance_punches", ["person_id"], unique=False)
    op.create_index(op.f("ix_attendance_punches_punched_at"), "attendance_punches", ["punched_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_attendance_punches_punched_at"), table_name="attendance_punches")
    op.drop_index(op.f("ix_attendance_punches_person_id"), table_name="attendance_punches")
    op.drop_index(op.f("ix_attendance_punches_person_type"), table_name="attendance_punches")
    op.drop_index(op.f("ix_attendance_punches_pin"), table_name="attendance_punches")
    op.drop_index(op.f("ix_attendance_punches_device_serial"), table_name="attendance_punches")
    op.drop_index(op.f("ix_attendance_punches_id"), table_name="attendance_punches")
    op.drop_table("attendance_punches")
