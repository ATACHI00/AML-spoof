"""Allow null accounts in transactions

Revision ID: 86b8744fc557
Revises: 0009
Create Date: 2026-07-24 01:10:44.636342
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '86b8744fc557'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Make source_account_id and destination_account_id nullable in transactions table.

    SQLite does not support ALTER COLUMN, so we need to recreate the table.
    """
    # Create new table with nullable columns
    op.create_table(
        'transactions_new',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('external_id', sa.String(255), nullable=False),
        sa.Column('source_account_id', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('destination_account_id', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('amount', sa.Numeric(18, 2), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False),
        sa.Column('txn_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('channel', sa.String(64), nullable=True),
        sa.Column('status', sa.Enum('pending', 'cleared', 'failed', 'reversed', name='txn_status'), nullable=False),
        sa.Column('extra_data', sa.JSON, nullable=True),
        sa.Column('ingested_at', sa.DateTime(timezone=True), nullable=False),
    )

    # Copy data from old table
    op.execute("""
        INSERT INTO transactions_new
        SELECT id, created_at, updated_at, external_id, source_account_id, destination_account_id,
               amount, currency, txn_timestamp, channel, status, extra_data, ingested_at
        FROM transactions
    """)

    # Drop old table
    op.drop_table('transactions')

    # Rename new table
    op.rename_table('transactions_new', 'transactions')


def downgrade() -> None:
    """Revert to non-nullable accounts - not supported for SQLite."""
    pass
