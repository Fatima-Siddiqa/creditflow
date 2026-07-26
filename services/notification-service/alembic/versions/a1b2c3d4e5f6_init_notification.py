"""init notification

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-07-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS notification')
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    notification_status = postgresql.ENUM('sent', 'failed', name='notification_status', schema='notification')
    notification_status.create(bind, checkfirst=True)

    if not inspector.has_table('notification_log', schema='notification'):
        op.create_table('notification_log',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('type', sa.String(), nullable=False),
    sa.Column('recipient', sa.String(), nullable=False),
    sa.Column('status', postgresql.ENUM('sent', 'failed', name='notification_status', schema='notification', create_type=False), nullable=False),
    sa.Column('error', sa.String(), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='notification',
    )

    if not inspector.has_table('processed_events', schema='notification'):
        op.create_table('processed_events',
    sa.Column('event_id', sa.String(), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('event_id'),
    schema='notification',
    )
        op.create_index(op.f('ix_notification_processed_events_event_id'), 'processed_events', ['event_id'], unique=False, schema='notification')


def downgrade() -> None:
    op.drop_index(op.f('ix_notification_processed_events_event_id'), table_name='processed_events', schema='notification')
    op.drop_table('processed_events', schema='notification')
    op.drop_table('notification_log', schema='notification')
    postgresql.ENUM(name='notification_status', schema='notification').drop(op.get_bind(), checkfirst=True)