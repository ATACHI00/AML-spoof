"""Seed default sanctions_match rule.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-22 23:20:00.000000
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ---------------------------------------------------------------------------
# New rule data
# ---------------------------------------------------------------------------

SANCTIONS_RULE = {
    "id": str(uuid4()),
    "name": "Sanctions Match Detection",
    "slug": "sanctions_match",
    "description": (
        "Screens transaction parties (source/destination account holders) "
        "against the local OFAC/EU/UN sanctions list using fuzzy name matching. "
        "Generates alerts when a name matches a sanctioned entity above the "
        "configured similarity threshold."
    ),
    "detector_type": "sanctions_match",
    "config": {
        "threshold": 0.88,
        "method": "jaro_winkler",
    },
    "weight": Decimal("2.00"),
    "is_active": True,
}


def upgrade() -> None:
    """Insert the sanctions_match rule."""
    now = datetime.now(timezone.utc)

    rules_table = sa.table(
        "rules",
        sa.column("id", sa.String(36)),
        sa.column("name", sa.String(255)),
        sa.column("slug", sa.String(128)),
        sa.column("description", sa.Text),
        sa.column("detector_type", sa.String(64)),
        sa.column("config", sa.JSON),
        sa.column("weight", sa.Numeric(5, 2)),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    op.bulk_insert(
        rules_table,
        [
            {
                "id": SANCTIONS_RULE["id"],
                "name": SANCTIONS_RULE["name"],
                "slug": SANCTIONS_RULE["slug"],
                "description": SANCTIONS_RULE["description"],
                "detector_type": SANCTIONS_RULE["detector_type"],
                "config": SANCTIONS_RULE["config"],
                "weight": SANCTIONS_RULE["weight"],
                "is_active": SANCTIONS_RULE["is_active"],
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def downgrade() -> None:
    """Remove the sanctions_match rule."""
    op.execute(
        sa.text("DELETE FROM rules WHERE slug = 'sanctions_match'")
    )
