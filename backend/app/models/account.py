"""AML Monitor — Account model.

Счета, привязанные к клиентам.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Account(TimestampMixin, Base):
    """A financial account belonging to a client."""

    __tablename__ = "accounts"

    client_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False, index=True
    )
    """UUID of the client who owns this account."""

    account_number: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    """IBAN or account number."""

    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    """ISO 4217 currency code."""

    balance: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    client = relationship("Client", back_populates="accounts")
    outgoing_transactions = relationship(
        "Transaction",
        back_populates="source_account",
        foreign_keys="Transaction.source_account_id",
        lazy="dynamic",
    )
    incoming_transactions = relationship(
        "Transaction",
        back_populates="destination_account",
        foreign_keys="Transaction.destination_account_id",
        lazy="dynamic",
    )