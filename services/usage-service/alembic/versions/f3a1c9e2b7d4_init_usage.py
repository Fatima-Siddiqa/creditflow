"""init usage

Revision ID: f3a1c9e2b7d4
Revises:
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a1c9e2b7d4'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute('CREATE SCHEMA IF NOT EXISTS usage')
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table('usage_ledger', schema='usage'):
        op.create_table('usage_ledger',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('account_id', sa.String(), nullable=False),
    sa.Column('model', sa.String(), nullable=False),
    sa.Column('tokens_used', sa.Integer(), nullable=False),
    sa.Column('cost_cents', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='usage',
    )
        op.create_index(op.f('ix_usage_usage_ledger_account_id'), 'usage_ledger', ['account_id'], unique=False, schema='usage')

    if not inspector.has_table('processed_events', schema='usage'):
        op.create_table('processed_events',
    sa.Column('event_id', sa.String(), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('event_id'),
    schema='usage',
    )
        op.create_index(op.f('ix_usage_processed_events_event_id'), 'processed_events', ['event_id'], unique=False, schema='usage')

    if not inspector.has_table('usage_threshold_notifications', schema='usage'):
        op.create_table('usage_threshold_notifications',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('account_id', sa.String(), nullable=False),
    sa.Column('period', sa.String(), nullable=False),
    sa.Column('threshold', sa.Integer(), nullable=False),
    sa.Column('notified_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('account_id', 'period', 'threshold', name='uq_usage_threshold_account_period_threshold'),
    schema='usage',
    )
        op.create_index(op.f('ix_usage_usage_threshold_notifications_account_id'), 'usage_threshold_notifications', ['account_id'], unique=False, schema='usage')
    # ### end Alembic commands ###


def downgrade() -> None:
    op.drop_index(op.f('ix_usage_usage_threshold_notifications_account_id'), table_name='usage_threshold_notifications', schema='usage')
    op.drop_table('usage_threshold_notifications', schema='usage')
    op.drop_index(op.f('ix_usage_processed_events_event_id'), table_name='processed_events', schema='usage')
    op.drop_table('processed_events', schema='usage')
    op.drop_index(op.f('ix_usage_usage_ledger_account_id'), table_name='usage_ledger', schema='usage')
    op.drop_table('usage_ledger', schema='usage')
