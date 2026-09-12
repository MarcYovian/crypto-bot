"""Add daily_risk_amount column to daily_risk_config table.

Revision ID: 4b5c6d7e8f9a
Revises: 3a4b5c6d7e8f
Create Date: 2026-08-31 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4b5c6d7e8f9a"
down_revision: Union[str, None] = "3a4b5c6d7e8f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add daily_risk_amount column with default '0'
    op.add_column(
        "daily_risk_config",
        sa.Column("daily_risk_amount", sa.Numeric(precision=18, scale=8), server_default="0", nullable=False),
    )
    # 2. Backfill existing records: set daily_risk_amount to risk_amount or balance * 0.05
    op.execute(
        "UPDATE daily_risk_config SET daily_risk_amount = CASE WHEN risk_amount > 0 THEN risk_amount ELSE balance * 0.05 END WHERE daily_risk_amount = 0"
    )


def downgrade() -> None:
    op.drop_column("daily_risk_config", "daily_risk_amount")
