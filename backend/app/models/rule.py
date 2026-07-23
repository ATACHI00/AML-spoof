"""AML Monitor — Rule model.

Конфигурируемые правила детекции (не хардкодить в коде).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, Enum, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Rule(TimestampMixin, Base):
    """A configurable detection rule."""

    __tablename__ = "rules"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    """Human-readable rule name."""

    slug: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    """Machine-readable identifier (e.g., 'structuring', 'velocity')."""

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    detector_type: Mapped[str] = mapped_column(
        Enum(
            "structuring",
            "rapid_movement",
            "round_amount",
            "velocity",
            "geographic",
            "dormant",
            "ml_anomaly",
            "sanctions_match",
            "graph_anomaly",
            name="detector_type",
        ),
        nullable=False,
    )

    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    """Thresholds and parameters as JSON.
    
    Example for structuring:
    {
        "threshold_amount": 9999.99,
        "time_window_minutes": 1440,
        "min_transactions": 3
    }
    """

    weight: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("1.00")
    )
    """Weight for risk score calculation."""

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)