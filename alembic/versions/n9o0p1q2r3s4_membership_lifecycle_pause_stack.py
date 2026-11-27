"""Membership lifecycle columns: pause, scheduled renewal, resume chain.

Revision ID: n9o0p1q2r3s4 (Phase 1.3.7 n9a)
Revises: m8n9o0p1q2r3
Create Date: 2026-11-27

Adds nullable lifecycle columns and ``resume_after_subscription_id`` FK/index only.

The partial unique index ``uq_membership_subscriptions_one_effective_active`` is
applied in the follow-up revision ``o0p1q2r3s4t5`` (n9b) so reconciliation can
run between n9a and n9b.

Revision ID policy: ``n9o0p1q2r3s4`` is retained (not applied on rehearsal per
Phase 1.3.5/1.3.7 audit). If any environment already stamped this revision with
the old combined upgrade (columns + index), manual DBA review is required before
re-running Alembic.

Before rollout, verify each target environment::
    SELECT version_num FROM alembic_version;

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "n9o0p1q2r3s4"
down_revision: Union[str, Sequence[str], None] = "m8n9o0p1q2r3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "membership_subscriptions",
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "membership_subscriptions",
        sa.Column("resumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "membership_subscriptions",
        sa.Column("remaining_days", sa.Integer(), nullable=True),
    )
    op.add_column(
        "membership_subscriptions",
        sa.Column(
            "resume_after_subscription_id",
            sa.Integer(),
            sa.ForeignKey("membership_subscriptions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "membership_subscriptions",
        sa.Column("assignment_intent", sa.String(length=20), nullable=True),
    )
    op.create_index(
        "ix_membership_subscriptions_resume_after",
        "membership_subscriptions",
        ["resume_after_subscription_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_membership_subscriptions_resume_after", "membership_subscriptions")
    op.drop_column("membership_subscriptions", "assignment_intent")
    op.drop_column("membership_subscriptions", "resume_after_subscription_id")
    op.drop_column("membership_subscriptions", "remaining_days")
    op.drop_column("membership_subscriptions", "resumed_at")
    op.drop_column("membership_subscriptions", "paused_at")