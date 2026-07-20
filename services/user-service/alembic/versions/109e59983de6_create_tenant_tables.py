"""create tenant tables

Revision ID: 109e59983de6
Revises:
Create Date: 2026-07-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '109e59983de6'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'accounts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('type', sa.Enum('individual', 'team', name='account_type', schema='tenant'), nullable=False),
        sa.Column('plan_tier', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        schema='tenant',
    )
    op.create_table(
        'account_members',
        sa.Column('account_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('role', sa.Enum('owner', 'admin', 'member', name='account_member_role', schema='tenant'), nullable=False),
        sa.Column('joined_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['tenant.accounts.id'], ),
        sa.PrimaryKeyConstraint('account_id', 'user_id'),
        schema='tenant',
    )
    op.create_index(op.f('ix_tenant_account_members_user_id'), 'account_members', ['user_id'], unique=False, schema='tenant')
    op.create_table(
        'invites',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('account_id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('role', sa.Enum('owner', 'admin', 'member', name='invite_role', schema='tenant'), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('accepted', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['tenant.accounts.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
        schema='tenant',
    )
    op.create_index(op.f('ix_tenant_invites_account_id'), 'invites', ['account_id'], unique=False, schema='tenant')
    op.create_table(
        'processed_events',
        sa.Column('event_id', sa.UUID(), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('event_id'),
        schema='tenant',
    )


def downgrade() -> None:
    op.drop_table('processed_events', schema='tenant')
    op.drop_index(op.f('ix_tenant_invites_account_id'), table_name='invites', schema='tenant')
    op.drop_table('invites', schema='tenant')
    op.drop_index(op.f('ix_tenant_account_members_user_id'), table_name='account_members', schema='tenant')
    op.drop_table('account_members', schema='tenant')
    op.drop_table('accounts', schema='tenant')
    # Postgres ENUM types aren't dropped automatically when their last
    # column goes away — drop them explicitly, or `downgrade` leaves
    # orphaned types behind that block a future `upgrade` reusing the name.
    sa.Enum(name='invite_role', schema='tenant').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='account_member_role', schema='tenant').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='account_type', schema='tenant').drop(op.get_bind(), checkfirst=True)