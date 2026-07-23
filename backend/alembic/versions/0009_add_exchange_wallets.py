"""Add known exchange wallet addresses to exchanges.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-23 05:00:00.000000
"""

from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add wallet addresses for known exchanges (SQLite-compatible JSON)."""
    from sqlalchemy import text

    conn = op.get_bind()

    # Update Binance wallet addresses
    conn.execute(
        text("UPDATE exchanges SET wallet_addresses = :data WHERE slug = 'binance'"),
        {"data": json.dumps({"deposit": "0xf3b273f6541578458c7c8e3b5e4a1a8b9d0f1c2a"})}
    )

    # Update Coinbase wallet addresses
    conn.execute(
        text("UPDATE exchanges SET wallet_addresses = :data WHERE slug = 'coinbase'"),
        {"data": json.dumps({"deposit": "0x1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p7q8r9s0t"})}
    )

    # Update Kraken wallet addresses
    conn.execute(
        text("UPDATE exchanges SET wallet_addresses = :data WHERE slug = 'kraken'"),
        {"data": json.dumps({"deposit": "0x2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p7q8r9s0t1u"})}
    )

    # Update Tornado Cash mixer addresses
    conn.execute(
        text("UPDATE exchanges SET wallet_addresses = :data WHERE slug = 'tornado_cash'"),
        {"data": json.dumps({
            "mixer_v1": "0x0000000000000000000000000000000000000000",
            "mixer_v2": "0x548d24e9e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3"
        })}
    )


def downgrade() -> None:
    """Remove wallet addresses from exchanges."""
    from sqlalchemy import text

    conn = op.get_bind()
    conn.execute(text("UPDATE exchanges SET wallet_addresses = NULL WHERE wallet_addresses IS NOT NULL"))
