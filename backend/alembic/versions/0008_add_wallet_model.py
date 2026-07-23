"""Add wallet model and exchange-wallet relationships

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-23 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create wallet table (works for both PostgreSQL and SQLite)
    op.create_table(
        "wallets",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("address", sa.String(128), unique=True, nullable=False, index=True),
        sa.Column("currency", sa.String(16), nullable=False, index=True),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("is_sanctioned", sa.Boolean(), default=False, nullable=False),
        sa.Column("risk_score", sa.Numeric(5, 2), default=0.00),
        sa.Column("first_seen", sa.Date(), nullable=True),
        sa.Column("last_seen", sa.Date(), nullable=True),
        sa.Column("total_received", sa.Numeric(18, 8), default=0.00),
        sa.Column("total_sent", sa.Numeric(18, 8), default=0.00),
        sa.Column("exchange_id", sa.UUID(as_uuid=True), nullable=True, index=True),
    )

    # Add wallet_addresses column to exchanges table (JSON)
    op.add_column("exchanges", sa.Column("wallet_addresses", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("exchanges", "wallet_addresses")
    op.drop_table("wallets")
