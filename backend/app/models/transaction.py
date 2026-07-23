"""AML Monitor — Transaction model.

Транзакции: сумма, валюта, отправитель, получатель, timestamp, канал, статус.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Transaction(TimestampMixin, Base):
    """A financial transaction being monitored."""

    __tablename__ = "transactions"

    external_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    """Client's internal transaction ID — used for idempotency."""

    source_account_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True
    )

    destination_account_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    """ISO 4217 currency code."""

    txn_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    """When the transaction occurred (client-reported)."""

    channel: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    """Transaction channel: wire, ach, card, internal, crypto, etc."""

    status: Mapped[str] = mapped_column(
        Enum("pending", "cleared", "failed", "reversed", name="txn_status"),
        nullable=False,
        default="pending",
    )

    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    """Arbitrary extra data from the client."""

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    """When we received/ingested the transaction."""

    # Relationships
    source_account = relationship(
        "Account", back_populates="outgoing_transactions",
        foreign_keys=[source_account_id],
    )
    destination_account = relationship(
        "Account", back_populates="incoming_transactions",
        foreign_keys=[destination_account_id],
    )