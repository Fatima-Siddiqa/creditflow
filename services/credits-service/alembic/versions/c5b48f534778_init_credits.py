"""init credits

Revision ID: c5b48f534778
Revises: 
Create Date: 2026-07-20 01:41:44.096277

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5b48f534778'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('credits_ledger',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('account_id', sa.String(), nullable=False),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('transaction_type', sa.Enum('PURCHASE', 'CONSUMPTION', 'MARKETPLACE_BUY', 'MARKETPLACE_SELL', 'REFUND_CLAWBACK', name='transactiontype', schema='credits'), nullable=False),
    sa.Column('reference_id', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='credits',
    )
    op.create_index(op.f('ix_credits_credits_ledger_account_id'), 'credits_ledger', ['account_id'], unique=False, schema='credits')
    op.create_index(op.f('ix_credits_credits_ledger_id'), 'credits_ledger', ['id'], unique=False, schema='credits')
    op.create_table('marketplace_listings',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('seller_account_id', sa.String(), nullable=False),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('price_cents', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='credits',
    )
    op.create_index(op.f('ix_credits_marketplace_listings_id'), 'marketplace_listings', ['id'], unique=False, schema='credits')
    op.create_index(op.f('ix_credits_marketplace_listings_seller_account_id'), 'marketplace_listings', ['seller_account_id'], unique=False, schema='credits')
    op.create_table('processed_events',
    sa.Column('event_id', sa.String(), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('event_id'),
    schema='credits',
    )
    op.create_index(op.f('ix_credits_processed_events_event_id'), 'processed_events', ['event_id'], unique=False, schema='credits')
    # ### end Alembic commands ###


def downgrade() -> None:
    op.drop_index(op.f('ix_credits_processed_events_event_id'), table_name='processed_events', schema='credits')
    op.drop_table('processed_events', schema='credits')
    op.drop_index(op.f('ix_credits_marketplace_listings_seller_account_id'), table_name='marketplace_listings', schema='credits')
    op.drop_index(op.f('ix_credits_marketplace_listings_id'), table_name='marketplace_listings', schema='credits')
    op.drop_table('marketplace_listings', schema='credits')
    op.drop_index(op.f('ix_credits_credits_ledger_id'), table_name='credits_ledger', schema='credits')
    op.drop_index(op.f('ix_credits_credits_ledger_account_id'), table_name='credits_ledger', schema='credits')
    op.drop_table('credits_ledger', schema='credits')
    sa.Enum(name='transactiontype', schema='credits').drop(op.get_bind(), checkfirst=True)