"""create instrument leverage brackets table

Revision ID: 2f8a19bc3d45
Revises: '1e44724e9b78'
Create Date: 2026-08-17 21:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2f8a19bc3d45'
down_revision: Union[str, None] = '1e44724e9b78'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'instrument_leverage_brackets',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('instrument_id', sa.Integer(), nullable=False),
        sa.Column('bracket', sa.Integer(), nullable=False),
        sa.Column('initial_leverage', sa.Integer(), nullable=False),
        sa.Column('notional_cap', sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column('notional_floor', sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column('maint_margin_ratio', sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column('cum', sa.Numeric(precision=18, scale=8), server_default='0', nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['instrument_id'], ['instruments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('instrument_id', 'bracket', name='uk_instrument_brackets_bracket')
    )
    op.create_index('idx_instrument_brackets_instrument_id', 'instrument_leverage_brackets', ['instrument_id'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_instrument_brackets_instrument_id', table_name='instrument_leverage_brackets')
    op.drop_table('instrument_leverage_brackets')
