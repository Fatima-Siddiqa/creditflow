"""add transaction_type to credits_ledger

Revision ID: b5f7a47db4d1
Revises: c5b48f534778
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5f7a47db4d1'
down_revision: Union[str, Sequence[str], None] = 'c5b48f534778'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS credits')
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns('credits_ledger', schema='credits')
    if any(column['name'] == 'transaction_type' for column in columns):
        return

    op.add_column(
        'credits_ledger',
        sa.Column('transaction_type', sa.String(), nullable=False, server_default='purchase'),
        schema='credits',
    )
    op.alter_column('credits_ledger', 'transaction_type', server_default=None, schema='credits')


def downgrade() -> None:
    op.drop_column('credits_ledger', 'transaction_type', schema='credits')
