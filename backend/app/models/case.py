"""AML Monitor — Case model.

Объединение нескольких alerts в одно расследование.
"""

from __future__ import annotations

from sqlalchemy import Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Case(TimestampMixin, Base):
    """A case grouping multiple alerts for investigation."""

    __tablename__ = "cases"

    title: Mapped[str] = mapped_column(String(512), nullable=False)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        Enum("open", "in_review", "closed", "escalated", name="case_status"),
        nullable=False,
        default="open",
    )

    assigned_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    """Compliance officer assigned to this case."""

    # Relationships
    alerts = relationship("Alert", back_populates="case", lazy="selectin")