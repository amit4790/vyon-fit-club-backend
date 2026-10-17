"""rename focus_next_month to medical_history on body assessments

Revision ID: j5k6l7m8n9o0
Revises: i4j5k6l7m8n9
Create Date: 2026-10-17
"""

from typing import Sequence, Union

from alembic import op

revision: str = "j5k6l7m8n9o0"
down_revision: Union[str, Sequence[str], None] = "i4j5k6l7m8n9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("body_assessments", "focus_next_month", new_column_name="medical_history")


def downgrade() -> None:
    op.alter_column("body_assessments", "medical_history", new_column_name="focus_next_month")
