"""AML Monitor — Audit Log model.

Неизменяемая (append-only) таблица: кто, что, когда сделал с alert/case.
Хэш-цепочка для tamper-evidence.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditLog(Base):
    """Append-only audit trail with hash chain for tamper evidence."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    entity_type: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    """Type of entity: alert, case, rule, transaction."""

    entity_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )

    action: Mapped[str] = mapped_column(String(64), nullable=False)
    """Action performed: created, updated, closed, escalated, etc."""

    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    """Who performed the action (user ID or system)."""

    changes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    """Before/after diff of the changes."""

    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """SHA-256 hash of the previous audit log row."""

    current_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    """SHA-256 hash of this row."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )