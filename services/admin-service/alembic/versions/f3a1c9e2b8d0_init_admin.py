"""init admin

Revision ID: f3a1c9e2b8d0
Revises:
Create Date: 2026-07-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'f3a1c9e2b8d0'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS admin')
    op.create_table('audit_log',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('payload', postgresql.JSONB(), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        schema='admin',
    )
    op.create_index('ix_admin_audit_log_event_id', 'audit_log', ['event_id'], schema='admin')
    op.create_index('ix_admin_audit_log_event_type', 'audit_log', ['event_type'], schema='admin')
    op.create_index('ix_admin_audit_log_account_id', 'audit_log', ['account_id'], schema='admin')

    op.create_table('processed_events',
        sa.Column('event_id', sa.String(), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('event_id'),
        schema='admin',
    )


def downgrade() -> None:
    op.drop_table('processed_events', schema='admin')
    op.drop_table('audit_log', schema='admin')