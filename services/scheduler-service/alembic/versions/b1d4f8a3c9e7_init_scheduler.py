"""init scheduler

Revision ID: b1d4f8a3c9e7
Revises:
Create Date: 2026-07-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'b1d4f8a3c9e7'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS scheduler')
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table('scheduled_posts', schema='scheduler'):
        op.create_table('scheduled_posts',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('account_id', sa.String(), nullable=False),
            sa.Column('content_id', sa.String(), nullable=False),
            sa.Column('has_image', sa.Boolean(), nullable=False),
            sa.Column('publish_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('status', sa.Enum('pending', 'fired', 'cancelled', name='schedule_status', schema='scheduler'), nullable=False),
            sa.Column('recurrence_rule', sa.JSON(), nullable=True),
            sa.Column('recurrence_parent_id', sa.String(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            schema='scheduler',
        )
        op.create_index(op.f('ix_scheduler_scheduled_posts_account_id'), 'scheduled_posts', ['account_id'], schema='scheduler')
        op.create_index(op.f('ix_scheduler_scheduled_posts_publish_at'), 'scheduled_posts', ['publish_at'], schema='scheduler')
        op.create_index(op.f('ix_scheduler_scheduled_posts_recurrence_parent_id'), 'scheduled_posts', ['recurrence_parent_id'], schema='scheduler')


def downgrade() -> None:
    op.drop_table('scheduled_posts', schema='scheduler')
    sa.Enum(name='schedule_status', schema='scheduler').drop(op.get_bind(), checkfirst=True)
