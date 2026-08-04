"""Add ZKTeco PUSH protocol tables

Revision ID: e7f8c9d0a123
Revises: 1f2d3e4a5b66
Create Date: 2026-08-03 14:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e7f8c9d0a123"
down_revision: Union[str, Sequence[str], None] = "1f2d3e4a5b66"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create tables for ZKTeco PUSH (iClock/ADMS) protocol support.
    
    New tables:
    - push_devices: Track devices communicating via PUSH protocol
    - device_commands: Command queue for devices
    - device_attendance_logs: Raw attendance data uploads
    """
    
    # Create push_devices table
    op.create_table(
        "push_devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("serial_number", sa.String(length=100), nullable=False),
        sa.Column("device_name", sa.String(length=200), nullable=True),
        sa.Column("platform", sa.String(length=100), nullable=True),
        sa.Column("firmware_version", sa.String(length=100), nullable=True),
        sa.Column("device_type", sa.String(length=50), nullable=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("registration_payload", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id")
    )
    op.create_index(op.f("ix_push_devices_id"), "push_devices", ["id"], unique=False)
    op.create_index(op.f("ix_push_devices_serial_number"), "push_devices", ["serial_number"], unique=True)
    
    # Create device_commands table
    op.create_table(
        "device_commands",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("command_id", sa.String(length=100), nullable=False),
        sa.Column("device_serial", sa.String(length=100), nullable=False),
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "EXECUTING", "COMPLETED", "FAILED", name="commandstatus"),
            nullable=False,
            server_default="PENDING"
        ),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.PrimaryKeyConstraint("id")
    )
    op.create_index(op.f("ix_device_commands_id"), "device_commands", ["id"], unique=False)
    op.create_index(op.f("ix_device_commands_command_id"), "device_commands", ["command_id"], unique=True)
    op.create_index(op.f("ix_device_commands_device_serial"), "device_commands", ["device_serial"], unique=False)
    op.create_index(op.f("ix_device_commands_status"), "device_commands", ["status"], unique=False)
    
    # Create device_attendance_logs table
    op.create_table(
        "device_attendance_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_serial", sa.String(length=100), nullable=False),
        sa.Column("raw_payload", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("content_length", sa.Integer(), nullable=True),
        sa.Column("is_processed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("record_count", sa.Integer(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id")
    )
    op.create_index(op.f("ix_device_attendance_logs_id"), "device_attendance_logs", ["id"], unique=False)
    op.create_index(op.f("ix_device_attendance_logs_device_serial"), "device_attendance_logs", ["device_serial"], unique=False)
    op.create_index(op.f("ix_device_attendance_logs_is_processed"), "device_attendance_logs", ["is_processed"], unique=False)
    op.create_index(op.f("ix_device_attendance_logs_uploaded_at"), "device_attendance_logs", ["uploaded_at"], unique=False)


def downgrade() -> None:
    """Drop ZKTeco PUSH protocol tables."""
    
    # Drop device_attendance_logs table
    op.drop_index(op.f("ix_device_attendance_logs_uploaded_at"), table_name="device_attendance_logs")
    op.drop_index(op.f("ix_device_attendance_logs_is_processed"), table_name="device_attendance_logs")
    op.drop_index(op.f("ix_device_attendance_logs_device_serial"), table_name="device_attendance_logs")
    op.drop_index(op.f("ix_device_attendance_logs_id"), table_name="device_attendance_logs")
    op.drop_table("device_attendance_logs")
    
    # Drop device_commands table
    op.drop_index(op.f("ix_device_commands_status"), table_name="device_commands")
    op.drop_index(op.f("ix_device_commands_device_serial"), table_name="device_commands")
    op.drop_index(op.f("ix_device_commands_command_id"), table_name="device_commands")
    op.drop_index(op.f("ix_device_commands_id"), table_name="device_commands")
    op.drop_table("device_commands")
    op.execute("DROP TYPE commandstatus")
    
    # Drop push_devices table
    op.drop_index(op.f("ix_push_devices_serial_number"), table_name="push_devices")
    op.drop_index(op.f("ix_push_devices_id"), table_name="push_devices")
    op.drop_table("push_devices")
