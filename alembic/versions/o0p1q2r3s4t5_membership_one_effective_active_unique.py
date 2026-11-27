"""Partial unique index: one active membership subscription per member.

Revision ID: o0p1q2r3s4t5
Revises: n9o0p1q2r3s4
Create Date: 2026-11-27

Apply only after historical reconciliation (Phase 1.3.7): duplicate ``status='active'``
rows per member must be resolved before this upgrade runs.

Before rollout, verify each target environment::
    SELECT version_num FROM alembic_version;

Environments may be at ``l7m8n9o0p1q2``, ``m8n9o0p1q2r3``, ``n9o0p1q2r3s4``, or already at head.
Do not assume all databases share the same revision.

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "o0p1q2r3s4t5"
down_revision: Union[str, Sequence[str], None] = "n9o0p1q2r3s4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_membership_subscriptions_one_effective_active",
        "membership_subscriptions",
        ["member_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_membership_subscriptions_one_effective_active", "membership_subscriptions")