"""AML Monitor — Client model.

Юридические и физические лица, чьи транзакции мониторятся.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, Enum, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Client(TimestampMixin, Base):
    """A client (legal entity or individual) being monitored."""

    __tablename__ = "clients"

    external_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    """Client's internal ID from their system."""

    name: Mapped[str] = mapped_column(String(512), nullable=False)
    """Legal name of the client."""

    client_type: Mapped[str] = mapped_column(
        Enum("individual", "legal_entity", name="client_type"),
        nullable=False,
    )

    risk_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00")
    )
    """Overall risk score 0.00–100.00."""

    is_sanctioned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    accounts = relationship("Account", back_populates="client", lazy="selectin")