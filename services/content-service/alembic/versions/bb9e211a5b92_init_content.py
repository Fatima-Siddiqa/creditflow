"""init content

Revision ID: bb9e211a5b92
Revises:
Create Date: 2026-07-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'bb9e211a5b92'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS content')
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table('content', schema='content'):
        op.create_table('content',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('account_id', sa.String(), nullable=False),
    sa.Column('created_by_user_id', sa.String(), nullable=False),
    sa.Column('status', sa.Enum('draft', 'approved', 'published', name='content_status', schema='content'), nullable=False),
    sa.Column('image_url', sa.String(), nullable=True),
    sa.Column('current_version_id', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='content',
    )
        op.create_index(op.f('ix_content_content_account_id'), 'content', ['account_id'], unique=False, schema='content')
        op.create_index(op.f('ix_content_content_id'), 'content', ['id'], unique=False, schema='content')

    if not inspector.has_table('content_versions', schema='content'):
        op.create_table('content_versions',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('content_id', sa.String(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('image_url', sa.String(), nullable=True),
    sa.Column('created_by_user_id', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['content_id'], ['content.content.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='content',
    )
        op.create_index(op.f('ix_content_content_versions_content_id'), 'content_versions', ['content_id'], unique=False, schema='content')
        op.create_index(op.f('ix_content_content_versions_id'), 'content_versions', ['id'], unique=False, schema='content')

    if not inspector.has_table('processed_events', schema='content'):
        op.create_table('processed_events',
    sa.Column('event_id', sa.String(), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('event_id'),
    schema='content',
    )
        op.create_index(op.f('ix_content_processed_events_event_id'), 'processed_events', ['event_id'], unique=False, schema='content')


def downgrade() -> None:
    op.drop_index(op.f('ix_content_processed_events_event_id'), table_name='processed_events', schema='content')
    op.drop_table('processed_events', schema='content')
    op.drop_index(op.f('ix_content_content_versions_id'), table_name='content_versions', schema='content')
    op.drop_index(op.f('ix_content_content_versions_content_id'), table_name='content_versions', schema='content')
    op.drop_table('content_versions', schema='content')
    op.drop_index(op.f('ix_content_content_id'), table_name='content', schema='content')
    op.drop_index(op.f('ix_content_content_account_id'), table_name='content', schema='content')
    op.drop_table('content', schema='content')
    sa.Enum(name='content_status', schema='content').drop(op.get_bind(), checkfirst=True)