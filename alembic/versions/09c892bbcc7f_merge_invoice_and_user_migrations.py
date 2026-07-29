"""merge invoice and user migrations

Revision ID: 09c892bbcc7f
Revises: e6d1aa2c9f14, 9e4c21fd7a11
Create Date: 2026-07-29 09:34:55.631414

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision: str = '09c892bbcc7f'
down_revision: Union[str, Sequence[str], None] = ('e6d1aa2c9f14', '9e4c21fd7a11')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
