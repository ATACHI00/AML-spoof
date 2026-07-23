"""AML Monitor — Wallet model.

Cryptocurrency wallet classification and tracking for AML monitoring.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Date, ForeignKey, JSON, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Wallet(TimestampMixin, Base):
    """A cryptocurrency wallet for AML monitoring."""

    __tablename__ = "wallets"

    id: str = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True,
    )

    address: str = Column(String(128), unique=True, nullable=False, index=True)
    """Cryptocurrency wallet address (BTC, ETH, USDT, XMR, etc.)."""

    currency: str = Column(String(16), nullable=False, index=True)
    """Currency type: BTC, ETH, USDT, XMR, etc."""

    label: str | None = Column(String(255), nullable=True)
    """Human-readable label for the wallet."""

    is_sanctioned: bool = Column(Boolean, default=False, nullable=False)
    """Whether this wallet is on a sanctions list."""

    risk_score: Decimal = Column(Numeric(5, 2), default=Decimal("0.00"))
    """Risk score 0.00-100.00 based on activity and associations."""

    first_seen: date | None = Column(Date, nullable=True)
    """First seen date for this wallet."""

    last_seen: date | None = Column(Date, nullable=True)
    """Last seen date for this wallet."""

    total_received: Decimal = Column(Numeric(18, 8), default=Decimal("0.00"))
    """Total amount received by this wallet."""

    total_sent: Decimal = Column(Numeric(18, 8), default=Decimal("0.00"))
    """Total amount sent from this wallet."""

    # Relationships
    exchange_id: str | None = Column(
        UUID(as_uuid=True), ForeignKey("exchanges.id"), nullable=True, index=True
    )
    """Exchange this wallet belongs to (if known)."""

    exchange = relationship("Exchange", back_populates="wallets", lazy="selectin")
