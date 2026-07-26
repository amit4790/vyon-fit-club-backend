"""add specialization to users

Revision ID: e6d1aa2c9f14
Revises: a1e4d5c0b912
Create Date: 2026-07-26 13:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e6d1aa2c9f14"
down_revision: Union[str, Sequence[str], None] = "a1e4d5c0b912"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("specialization", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "specialization")
