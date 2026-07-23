"""Exchange model — Crypto exchange classification."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, JSON, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class Exchange(TimestampMixin, Base):
    """A cryptocurrency exchange or service for AML monitoring."""

    __tablename__ = "exchanges"

    id: str = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True,
    )

    name: str = Column(String(255), nullable=False)
    slug: str = Column(String(128), unique=True, nullable=False, index=True)

    kyc_level: str = Column(
        String(16), nullable=False, default="none"
    )  # none, basic, full, enterprise

    exchange_type: str = Column(
        String(16), nullable=False, default="cex"
    )  # cex, dex, p2p, mixer, casino

    countries: str = Column(Text, nullable=True)  # JSON string for SQLite compatibility

    risk_score: Decimal = Column(Numeric(5, 2), default=Decimal("0.00"))

    is_active: bool = Column(Boolean, default=True, nullable=False)

    description: str | None = Column(Text, nullable=True)

    website: str | None = Column(String(512), nullable=True)

    api_docs: str | None = Column(String(512), nullable=True)

    notes: str | None = Column(Text, nullable=True)

    # Compliance flags
    is_kyc_required: bool = Column(Boolean, default=True)
    is_license_held: bool = Column(Boolean, default=False)

    # Sanctions
    is_sanctioned: bool = Column(Boolean, default=False)

    # Wallets associated with this exchange
    wallet_addresses: dict | None = Column("wallet_addresses", JSON, nullable=True)
    """Known wallet addresses for this exchange (for fast lookup)."""

    # Relationships
    wallets = relationship("Wallet", back_populates="exchange", lazy="selectin")
