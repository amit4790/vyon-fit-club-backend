"""add body assessments

Revision ID: i4j5k6l7m8n9
Revises: h3i4j5k6l7m8
Create Date: 2026-10-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "i4j5k6l7m8n9"
down_revision: Union[str, Sequence[str], None] = "h3i4j5k6l7m8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "body_assessments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("conducted_by_trainer_id", sa.Integer(), nullable=False),
        sa.Column("assessed_on", sa.Date(), nullable=False),
        sa.Column("assessment_type", sa.String(length=40), server_default="monthly_review", nullable=False),
        sa.Column("measurement_method", sa.String(length=80), nullable=True),
        sa.Column("device_name", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="completed", nullable=False),
        sa.Column("primary_goal", sa.String(length=200), nullable=True),
        sa.Column("trainer_observations", sa.Text(), nullable=True),
        sa.Column("focus_next_month", sa.Text(), nullable=True),
        sa.Column("next_assessment_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"]),
        sa.ForeignKeyConstraint(["conducted_by_trainer_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_body_assessments_id"), "body_assessments", ["id"], unique=False)
    op.create_index(op.f("ix_body_assessments_member_id"), "body_assessments", ["member_id"], unique=False)
    op.create_index(
        op.f("ix_body_assessments_conducted_by_trainer_id"),
        "body_assessments",
        ["conducted_by_trainer_id"],
        unique=False,
    )
    op.create_index(op.f("ix_body_assessments_assessed_on"), "body_assessments", ["assessed_on"], unique=False)
    op.create_index(op.f("ix_body_assessments_status"), "body_assessments", ["status"], unique=False)

    op.create_table(
        "body_assessment_metrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("assessment_id", sa.Integer(), nullable=False),
        sa.Column("metric_key", sa.String(length=60), nullable=False),
        sa.Column("value_numeric", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), server_default="machine", nullable=False),
        sa.Column("body_region", sa.String(length=40), nullable=True),
        sa.Column("side", sa.String(length=10), nullable=True),
        sa.ForeignKeyConstraint(["assessment_id"], ["body_assessments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_body_assessment_metrics_id"), "body_assessment_metrics", ["id"], unique=False)
    op.create_index(
        op.f("ix_body_assessment_metrics_assessment_id"),
        "body_assessment_metrics",
        ["assessment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_body_assessment_metrics_metric_key"),
        "body_assessment_metrics",
        ["metric_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("body_assessment_metrics")
    op.drop_table("body_assessments")
