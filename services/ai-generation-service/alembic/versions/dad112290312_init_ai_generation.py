"""init ai generation

Revision ID: dad112290312
Revises:
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dad112290312'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute('CREATE SCHEMA IF NOT EXISTS ai')
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table('generation_jobs', schema='ai'):
        op.create_table('generation_jobs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('account_id', sa.String(), nullable=False),
        sa.Column('created_by_user_id', sa.String(), nullable=False),
        sa.Column('model', sa.String(), nullable=False),
        # schema='ai' on the Enum itself, not just the table -- an
        # unqualified Enum lands wherever the connection's default
        # search_path resolves, independent of create_table's schema kwarg.
        # This is exactly what broke credits-service's first migration
        # (transactiontype ended up in public); pinning it explicitly here
        # so this service doesn't repeat that.
        sa.Column('status', sa.Enum('RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED', name='generationstatus', schema='ai'), nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), nullable=True),
        sa.Column('completion_tokens', sa.Integer(), nullable=True),
        sa.Column('total_tokens', sa.Integer(), nullable=True),
        sa.Column('cost_cents', sa.Integer(), nullable=True),
        sa.Column('error_reason', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        schema='ai',
        )
        op.create_index(op.f('ix_ai_generation_jobs_account_id'), 'generation_jobs', ['account_id'], unique=False, schema='ai')

    if not inspector.has_table('prompt_history', schema='ai'):
        op.create_table('prompt_history',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('job_id', sa.String(), nullable=False),
        sa.Column('account_id', sa.String(), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('response', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['ai.generation_jobs.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='ai',
        )
        op.create_index(op.f('ix_ai_prompt_history_account_id'), 'prompt_history', ['account_id'], unique=False, schema='ai')
        op.create_index(op.f('ix_ai_prompt_history_job_id'), 'prompt_history', ['job_id'], unique=False, schema='ai')
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_ai_prompt_history_job_id'), table_name='prompt_history', schema='ai')
    op.drop_index(op.f('ix_ai_prompt_history_account_id'), table_name='prompt_history', schema='ai')
    op.drop_table('prompt_history', schema='ai')
    op.drop_index(op.f('ix_ai_generation_jobs_account_id'), table_name='generation_jobs', schema='ai')
    op.drop_table('generation_jobs', schema='ai')
    sa.Enum(name='generationstatus', schema='ai').drop(op.get_bind(), checkfirst=True)