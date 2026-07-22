"""init social

Revision ID: ec27a0ad12c6
Revises:
Create Date: 2026-07-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ec27a0ad12c6'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS social')
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table('social_connections', schema='social'):
        op.create_table('social_connections',
    sa.Column('account_id', sa.String(), nullable=False),
    sa.Column('linkedin_member_urn', sa.String(), nullable=False),
    sa.Column('access_token_enc', sa.String(), nullable=False),
    sa.Column('refresh_token_enc', sa.String(), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('account_id'),
    schema='social',
    )

    if not inspector.has_table('publish_jobs', schema='social'):
        op.create_table('publish_jobs',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('scheduled_post_id', sa.String(), nullable=False),
    sa.Column('content_id', sa.String(), nullable=False),
    sa.Column('account_id', sa.String(), nullable=False),
    sa.Column('status', sa.Enum('pending', 'publishing', 'published', 'failed', name='publish_status', schema='social'), nullable=False),
    sa.Column('attempt_count', sa.Integer(), nullable=False),
    sa.Column('last_error', sa.String(), nullable=True),
    sa.Column('linkedin_post_urn', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='social',
    )
        op.create_index(op.f('ix_social_publish_jobs_scheduled_post_id'), 'publish_jobs', ['scheduled_post_id'], unique=False, schema='social')
        op.create_index(op.f('ix_social_publish_jobs_account_id'), 'publish_jobs', ['account_id'], unique=False, schema='social')
        op.create_index(op.f('ix_social_publish_jobs_id'), 'publish_jobs', ['id'], unique=False, schema='social')

    if not inspector.has_table('post_media', schema='social'):
        op.create_table('post_media',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('publish_job_id', sa.String(), nullable=False),
    sa.Column('linkedin_asset_urn', sa.String(), nullable=False),
    sa.Column('image_url', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['publish_job_id'], ['social.publish_jobs.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='social',
    )
        op.create_index(op.f('ix_social_post_media_id'), 'post_media', ['id'], unique=False, schema='social')

    if not inspector.has_table('processed_events', schema='social'):
        op.create_table('processed_events',
    sa.Column('event_id', sa.String(), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('event_id'),
    schema='social',
    )
        op.create_index(op.f('ix_social_processed_events_event_id'), 'processed_events', ['event_id'], unique=False, schema='social')


def downgrade() -> None:
    op.drop_index(op.f('ix_social_processed_events_event_id'), table_name='processed_events', schema='social')
    op.drop_table('processed_events', schema='social')
    op.drop_index(op.f('ix_social_post_media_id'), table_name='post_media', schema='social')
    op.drop_table('post_media', schema='social')
    op.drop_index(op.f('ix_social_publish_jobs_id'), table_name='publish_jobs', schema='social')
    op.drop_index(op.f('ix_social_publish_jobs_account_id'), table_name='publish_jobs', schema='social')
    op.drop_index(op.f('ix_social_publish_jobs_scheduled_post_id'), table_name='publish_jobs', schema='social')
    op.drop_table('publish_jobs', schema='social')
    op.drop_table('social_connections', schema='social')
    sa.Enum(name='publish_status', schema='social').drop(op.get_bind(), checkfirst=True)