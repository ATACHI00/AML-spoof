"""AML Monitor — Audit Log API endpoints.

Просмотр audit log с верификацией hash chain (tamper-evidence).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import verify_api_key
from app.database import get_db
from app.models.audit_log import AuditLog
from app.schemas.audit import (
    AuditLogResponse,
    AuditLogListResponse,
    AuditLogVerifyResponse,
)
from app.utils.hashing import compute_audit_hash

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    entity_type: str | None = Query(None, description="Filter by entity type (alert, case, rule)"),
    entity_id: str | None = Query(None, description="Filter by entity ID"),
    action: str | None = Query(None, description="Filter by action"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> AuditLogListResponse:
    """List audit log entries with optional filters and pagination."""
    query = select(AuditLog)
    count_query = select(AuditLog.id)

    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id)
    if action:
        query = query.where(AuditLog.action == action)

    # Get total count
    count_result = await db.execute(count_query)
    total = len(count_result.all()) if not (entity_type or entity_id or action) else 0

    if total == 0 and (entity_type or entity_id or action):
        # Re-count with filters
        count_query = select(AuditLog.id)
        if entity_type:
            count_query = count_query.where(AuditLog.entity_type == entity_type)
        if entity_id:
            count_query = count_query.where(AuditLog.entity_id == entity_id)
        if action:
            count_query = count_query.where(AuditLog.action == action)
        count_result = await db.execute(count_query)
        total = len(count_result.all())

    # Apply ordering and pagination
    query = query.order_by(AuditLog.created_at.desc())
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    logs = result.scalars().all()

    return AuditLogListResponse(
        items=[_log_to_response(log) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/logs/{log_id}", response_model=AuditLogResponse)
async def get_audit_log(
    log_id: str,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> AuditLogResponse:
    """Get a single audit log entry by ID."""
    import uuid

    try:
        log_uuid = uuid.UUID(log_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid audit log ID")

    result = await db.execute(select(AuditLog).where(AuditLog.id == log_uuid))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Audit log entry not found")

    return _log_to_response(log)


@router.get("/verify", response_model=AuditLogVerifyResponse)
async def verify_audit_chain(
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> AuditLogVerifyResponse:
    """Verify the integrity of the entire audit log hash chain.

    Iterates through all audit log entries in chronological order and
    recomputes each entry's hash to verify tamper-evidence.
    """
    result = await db.execute(
        select(AuditLog).order_by(AuditLog.created_at.asc())
    )
    logs = result.scalars().all()

    if not logs:
        return AuditLogVerifyResponse(
            is_intact=True,
            total_entries=0,
            broken_links=[],
        )

    broken_links: list[dict] = []
    previous_hash: str | None = None

    for log in logs:
        expected_hash = compute_audit_hash(
            previous_hash=previous_hash,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            action=log.action,
            actor_id=log.actor_id,
            changes=log.changes,
            created_at=log.created_at,
        )

        if expected_hash != log.current_hash:
            broken_links.append({
                "id": str(log.id),
                "expected_hash": expected_hash,
                "actual_hash": log.current_hash,
                "created_at": log.created_at.isoformat(),
            })

        previous_hash = log.current_hash

    return AuditLogVerifyResponse(
        is_intact=len(broken_links) == 0,
        total_entries=len(logs),
        broken_links=broken_links,
    )


def _log_to_response(log: AuditLog) -> AuditLogResponse:
    """Convert AuditLog ORM to response schema."""
    return AuditLogResponse(
        id=str(log.id),
        entity_type=log.entity_type,
        entity_id=log.entity_id,
        action=log.action,
        actor_id=log.actor_id,
        changes=log.changes,
        previous_hash=log.previous_hash,
        current_hash=log.current_hash,
        created_at=log.created_at.isoformat(),
    )