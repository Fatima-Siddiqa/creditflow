"""add platform_role to users

Revision ID: b7e2f1a9c3d4
Revises: 17c5303bd1f8
Create Date: 2026-07-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b7e2f1a9c3d4'
down_revision: Union[str, Sequence[str], None] = '17c5303bd1f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('platform_role', sa.String(), nullable=True), schema='auth')


def downgrade() -> None:
    op.drop_column('users', 'platform_role', schema='auth')