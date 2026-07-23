"""Seed default rules for the rule engine.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-22 05:15:00.000000
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
# Default rules data
# ---------------------------------------------------------------------------

DEFAULT_RULES = [
    {
        "id": str(uuid4()),
        "name": "Structuring Detection",
        "slug": "structuring",
        "description": "Detects smurfing patterns — multiple transactions just below the reporting threshold within a 24-hour window.",
        "detector_type": "structuring",
        "config": {
            "threshold_amount": 9999.99,
            "time_window_minutes": 1440,
            "min_transactions": 3,
        },
        "weight": Decimal("1.00"),
        "is_active": True,
    },
    {
        "id": str(uuid4()),
        "name": "Rapid Movement Detection",
        "slug": "rapid_movement",
        "description": "Detects rapid movement of funds — destination account sends out >=90% of received amount within 60 minutes.",
        "detector_type": "rapid_movement",
        "config": {
            "threshold_pct": 90.00,
            "time_window_minutes": 60,
        },
        "weight": Decimal("1.00"),
        "is_active": True,
    },
    {
        "id": str(uuid4()),
        "name": "Round Amount Detection",
        "slug": "round_amount",
        "description": "Flags unusually round transaction amounts (e.g., 5000, 10000) or amounts just below round thresholds (e.g., 9999.99).",
        "detector_type": "round_amount",
        "config": {
            "threshold_amount": 5000,
            "check_below_threshold": True,
        },
        "weight": Decimal("0.50"),
        "is_active": True,
    },
    {
        "id": str(uuid4()),
        "name": "High Velocity Detection",
        "slug": "velocity",
        "description": "Flags accounts with unusually high transaction frequency — more than 10 transactions per hour.",
        "detector_type": "velocity",
        "config": {
            "max_transactions": 10,
            "time_window_minutes": 60,
        },
        "weight": Decimal("1.00"),
        "is_active": True,
    },
    {
        "id": str(uuid4()),
        "name": "Geographic Risk Detection",
        "slug": "geographic",
        "description": "Flags transactions involving high-risk jurisdictions or channels (e.g., crypto).",
        "detector_type": "geographic",
        "config": {
            "high_risk_countries": [
                "IR", "KP", "SY", "CU", "VE",
                "MM", "IQ", "LY", "SO", "SD",
                "YE", "AF", "BY", "CD", "CF",
            ],
            "high_risk_channels": ["crypto"],
        },
        "weight": Decimal("1.50"),
        "is_active": True,
    },
    {
        "id": str(uuid4()),
        "name": "Dormant Account Detection",
        "slug": "dormant",
        "description": "Flags transactions involving accounts that have been inactive for 90+ days.",
        "detector_type": "dormant",
        "config": {
            "dormant_days": 90,
        },
        "weight": Decimal("1.00"),
        "is_active": True,
    },
]


def upgrade() -> None:
    """Insert default rules into the rules table."""
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

    for rule in DEFAULT_RULES:
        op.bulk_insert(
            rules_table,
            [
                {
                    "id": rule["id"],
                    "name": rule["name"],
                    "slug": rule["slug"],
                    "description": rule["description"],
                    "detector_type": rule["detector_type"],
                    "config": rule["config"],
                    "weight": rule["weight"],
                    "is_active": rule["is_active"],
                    "created_at": now,
                    "updated_at": now,
                }
            ],
        )


def downgrade() -> None:
    """Remove default rules by slug."""
    slugs = [rule["slug"] for rule in DEFAULT_RULES]
    op.execute(
        sa.text("DELETE FROM rules WHERE slug = ANY(:slugs)").bindparams(
            slugs=slugs
        )
    )
