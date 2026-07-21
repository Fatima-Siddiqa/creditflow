"""add content_type to generation_jobs

Revision ID: c2b9e4480445
Revises: 40231e1a8453
Create Date: 2026-07-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c2b9e4480445'
down_revision: Union[str, Sequence[str], None] = 'dad112290312'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('generation_jobs', sa.Column('content_type', sa.String(), nullable=False, server_default='chat'), schema='ai')


def downgrade() -> None:
    op.drop_column('generation_jobs', 'content_type', schema='ai')