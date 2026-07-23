"""AML Monitor — Sanctions List model.

Локальный кэш OFAC/EU/UN списков с датой последнего обновления.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, Enum, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SanctionsList(TimestampMixin, Base):
    """Cached sanctions entry from OFAC, EU, or UN lists."""

    __tablename__ = "sanctions_lists"

    list_source: Mapped[str] = mapped_column(
        Enum("ofac", "eu", "un", name="sanctions_source"),
        nullable=False,
        index=True,
    )

    full_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)

    name_variations: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    """Aliases and name variations."""

    entity_type: Mapped[str] = mapped_column(
        Enum("individual", "entity", name="sanctions_entity_type"),
        nullable=False,
    )

    country: Mapped[str | None] = mapped_column(String(128), nullable=True)

    program: Mapped[str | None] = mapped_column(String(256), nullable=True)
    """Sanctions program (e.g., 'UKRAINE-EO13662')."""

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    last_updated: Mapped[date | None] = mapped_column(Date, nullable=True)