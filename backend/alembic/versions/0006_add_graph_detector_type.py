"""Add graph_anomaly and sanctions_match to detector_type ENUM.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-23 00:27:00.000000
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_ENUM = (
    "structuring",
    "rapid_movement",
    "round_amount",
    "velocity",
    "geographic",
    "dormant",
    "ml_anomaly",
)

NEW_ENUM = OLD_ENUM + ("sanctions_match", "graph_anomaly")


def upgrade() -> None:
    """Add sanctions_match and graph_anomaly to detector_type ENUM."""
    # SQLite doesn't support ALTER TYPE, so we need to recreate the table
    # For SQLite, we'll just add the new values as strings
    pass


def downgrade() -> None:
    """Remove sanctions_match and graph_anomaly from detector_type ENUM."""
    pass
