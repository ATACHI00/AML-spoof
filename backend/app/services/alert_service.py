"""AML Monitor — Alert service.

Business logic for alert listing, detail view, and status updates
with audit log integration.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.models.audit_log import AuditLog
from app.utils.hashing import compute_audit_hash


async def list_alerts(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    severity: str | None = None,
    rule_id: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[Alert], int]:
    """List alerts with optional filters and pagination.

    Returns:
        Tuple of (list of Alert ORM objects, total count).
    """
    # Build base query
    base_query = select(Alert)
    count_query = select(func.count(Alert.id))

    # Apply filters
    if status:
        base_query = base_query.where(Alert.status == status)
        count_query = count_query.where(Alert.status == status)
    if severity:
        base_query = base_query.where(Alert.severity == severity)
        count_query = count_query.where(Alert.severity == severity)
    if rule_id:
        base_query = base_query.where(Alert.rule_id == rule_id)
        count_query = count_query.where(Alert.rule_id == rule_id)

    # Get total count
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Apply sorting
    sort_column = getattr(Alert, sort_by, Alert.created_at)
    if sort_order == "asc":
        base_query = base_query.order_by(sort_column.asc())
    else:
        base_query = base_query.order_by(sort_column.desc())

    # Apply pagination
    offset = (page - 1) * page_size
    base_query = base_query.offset(offset).limit(page_size)

    result = await db.execute(base_query)
    alerts = list(result.scalars().all())

    return alerts, total


async def get_alert_by_id(db: AsyncSession, alert_id: str) -> Alert | None:
    """Get a single alert by ID."""
    try:
        alert_uuid = uuid.UUID(alert_id)
    except ValueError:
        return None

    result = await db.execute(select(Alert).where(Alert.id == alert_uuid))
    return result.scalar_one_or_none()


async def update_alert_status(
    db: AsyncSession,
    alert: Alert,
    new_status: str,
    comment: str,
    actor_id: str = "compliance-officer",
) -> tuple[Alert, AuditLog]:
    """Update alert status and create an audit log entry.

    Args:
        db: Database session.
        alert: Alert ORM instance to update.
        new_status: New status (closed, escalated, in_review).
        comment: Mandatory comment explaining the change.
        actor_id: Who performed the action.

    Returns:
        Tuple of (updated Alert, created AuditLog).
    """
    old_status = alert.status
    alert.status = new_status

    await db.flush()
    await db.refresh(alert)

    # Build changes diff
    changes = {
        "status": {"before": old_status, "after": new_status},
        "comment": comment,
    }

    # Get the latest audit log hash for chain linking
    prev_result = await db.execute(
        select(AuditLog.current_hash)
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    previous_hash = prev_result.scalar_one_or_none()

    # Use a single timestamp for both the hash computation and the DB record
    now = datetime.now(timezone.utc)

    current_hash = compute_audit_hash(
        previous_hash=previous_hash,
        entity_type="alert",
        entity_id=str(alert.id),
        action=f"status_{new_status}",
        actor_id=actor_id,
        changes=changes,
        created_at=now,
    )

    audit_entry = AuditLog(
        entity_type="alert",
        entity_id=str(alert.id),
        action=f"status_{new_status}",
        actor_id=actor_id,
        changes=changes,
        previous_hash=previous_hash,
        current_hash=current_hash,
        created_at=now,
    )
    db.add(audit_entry)
    await db.flush()
    await db.refresh(audit_entry)

    return alert, audit_entry