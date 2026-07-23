"""Initial exchange schema data.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-23 04:30:00.000000
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create exchanges table and seed known exchanges."""
    # Create exchanges table
    op.create_table(
        "exchanges",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(128), unique=True, nullable=False, index=True),
        sa.Column("kyc_level", sa.String(16), nullable=False, default="none"),
        sa.Column("exchange_type", sa.String(16), nullable=False, default="cex"),
        sa.Column("countries", sa.Text(), nullable=True),  # Store as JSON string for SQLite
        sa.Column("risk_score", sa.Numeric(5, 2), default=0.00),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("website", sa.String(512), nullable=True),
        sa.Column("api_docs", sa.String(512), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_kyc_required", sa.Boolean(), default=True),
        sa.Column("is_license_held", sa.Boolean(), default=False),
        sa.Column("is_sanctioned", sa.Boolean(), default=False),
    )

    # Seed known exchanges data
    now = datetime.now(timezone.utc)

    exchanges = [
        # KYC exchanges (lower risk)
        {"id": "a0000000-0000-0000-0000-000000000001", "name": "Binance", "slug": "binance", "kyc_level": "full", "exchange_type": "cex", "countries": json.dumps(["BV", "CY", "AE"]), "risk_score": "15.00", "is_active": True, "is_kyc_required": True, "is_license_held": False, "is_sanctioned": False},
        {"id": "a0000000-0000-0000-0000-000000000002", "name": "Coinbase", "slug": "coinbase", "kyc_level": "full", "exchange_type": "cex", "countries": json.dumps(["US"]), "risk_score": "10.00", "is_active": True, "is_kyc_required": True, "is_license_held": True, "is_sanctioned": False},
        {"id": "a0000000-0000-0000-0000-000000000003", "name": "Kraken", "slug": "kraken", "kyc_level": "full", "exchange_type": "cex", "countries": json.dumps(["US", "EU"]), "risk_score": "12.00", "is_active": True, "is_kyc_required": True, "is_license_held": True, "is_sanctioned": False},
        {"id": "a0000000-0000-0000-0000-000000000004", "name": "KuCoin", "slug": "kucoin", "kyc_level": "basic", "exchange_type": "cex", "countries": json.dumps(["SV", "AE"]), "risk_score": "35.00", "is_active": True, "is_kyc_required": False, "is_license_held": False, "is_sanctioned": False},
        {"id": "a0000000-0000-0000-0000-000000000005", "name": "OKX", "slug": "okx", "kyc_level": "basic", "exchange_type": "cex", "countries": json.dumps(["AE", "VG"]), "risk_score": "30.00", "is_active": True, "is_kyc_required": False, "is_license_held": False, "is_sanctioned": False},
        # No-KYC / Low-KYC exchanges (higher risk)
        {"id": "a0000000-0000-0000-0000-000000000010", "name": "Bisq", "slug": "bisq", "kyc_level": "none", "exchange_type": "p2p", "countries": json.dumps(["Global"]), "risk_score": "65.00", "is_active": True, "is_kyc_required": False, "is_license_held": False, "is_sanctioned": False},
        {"id": "a0000000-0000-0000-0000-000000000011", "name": "LocalBitcoins", "slug": "localbitcoins", "kyc_level": "none", "exchange_type": "p2p", "countries": json.dumps(["Global"]), "risk_score": "70.00", "is_active": False, "is_kyc_required": False, "is_license_held": False, "is_sanctioned": False},
        {"id": "a0000000-0000-0000-0000-000000000012", "name": "P2B", "slug": "p2b", "kyc_level": "none", "exchange_type": "cex", "countries": json.dumps(["EE"]), "risk_score": "55.00", "is_active": True, "is_kyc_required": False, "is_license_held": False, "is_sanctioned": False},
        # Mixers / Tumblers (very high risk)
        {"id": "a0000000-0000-0000-0000-000000000020", "name": "Tornado Cash", "slug": "tornado_cash", "kyc_level": "none", "exchange_type": "mixer", "countries": json.dumps(["DE"]), "risk_score": "95.00", "is_active": True, "is_kyc_required": False, "is_license_held": False, "is_sanctioned": True},
        {"id": "a0000000-0000-0000-0000-000000000021", "name": "Tornado Cash (new)", "slug": "tornado_cash_new", "kyc_level": "none", "exchange_type": "mixer", "countries": json.dumps(["DE"]), "risk_score": "95.00", "is_active": True, "is_kyc_required": False, "is_license_held": False, "is_sanctioned": True},
        {"id": "a0000000-0000-0000-0000-000000000022", "name": "Elliptic", "slug": "elliptic", "kyc_level": "none", "exchange_type": "mixer", "countries": json.dumps(["UK"]), "risk_score": "90.00", "is_active": True, "is_kyc_required": False, "is_license_held": False, "is_sanctioned": False},
        # Gambling / Casino (high risk)
        {"id": "a0000000-0000-0000-0000-000000000030", "name": "Stake", "slug": "stake", "kyc_level": "basic", "exchange_type": "casino", "countries": json.dumps(["CW"]), "risk_score": "75.00", "is_active": True, "is_kyc_required": False, "is_license_held": False, "is_sanctioned": False},
        {"id": "a0000000-0000-0000-0000-000000000031", "name": "Roobet", "slug": "roobet", "kyc_level": "none", "exchange_type": "casino", "countries": json.dumps(["CW"]), "risk_score": "80.00", "is_active": True, "is_kyc_required": False, "is_license_held": False, "is_sanctioned": False},
    ]

    op.bulk_insert(sa.table("exchanges", *[sa.column(c) for c in exchanges[0].keys()]), exchanges)


def downgrade() -> None:
    """Remove exchanges table."""
    op.drop_table("exchanges")
