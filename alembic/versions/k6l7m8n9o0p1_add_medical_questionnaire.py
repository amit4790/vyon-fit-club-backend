"""add medical_questionnaire json to body assessments

Revision ID: k6l7m8n9o0p1
Revises: j5k6l7m8n9o0
Create Date: 2026-10-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "k6l7m8n9o0p1"
down_revision: Union[str, Sequence[str], None] = "j5k6l7m8n9o0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "body_assessments",
        sa.Column("medical_questionnaire", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("body_assessments", "medical_questionnaire")
