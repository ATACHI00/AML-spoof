"""AML Monitor — Alert management API endpoints.

Listing, filtering, detail view, and status updates (close/escalate)
with mandatory audit log integration.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import verify_api_key
from app.database import get_db
from app.schemas.alert import (
    AlertListResponse,
    AlertResponse,
    AlertStatusUpdate,
    AlertStatusUpdateResponse,
)
from app.services.alert_service import (
    get_alert_by_id,
    list_alerts,
    update_alert_status,
)

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _build_response(alert) -> AlertResponse:
    """Convert an Alert ORM instance to an AlertResponse."""
    return AlertResponse(
        id=str(alert.id),
        transaction_id=str(alert.transaction_id) if alert.transaction_id else None,
        rule_id=str(alert.rule_id) if alert.rule_id else None,
        case_id=str(alert.case_id) if alert.case_id else None,
        severity=alert.severity,
        risk_score=alert.risk_score,
        title=alert.title,
        description=alert.description,
        status=alert.status,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
    )


@router.get("/", response_model=AlertListResponse)
async def list_alerts_endpoint(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: str | None = Query(
        None, description="Filter by status: new, in_review, escalated, closed"
    ),
    severity: str | None = Query(
        None, description="Filter by severity: low, medium, high, critical"
    ),
    rule_id: str | None = Query(None, description="Filter by rule ID"),
    sort_by: str = Query(
        "created_at", description="Sort field: created_at, severity, risk_score, status"
    ),
    sort_order: str = Query(
        "desc", description="Sort order: asc or desc"
    ),
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> AlertListResponse:
    """List alerts with optional filters and pagination.

    Supports filtering by status, severity, and rule_id.
    Results are paginated and sortable.
    """
    alerts, total = await list_alerts(
        db=db,
        page=page,
        page_size=page_size,
        status=status,
        severity=severity,
        rule_id=rule_id,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    return AlertListResponse(
        alerts=[_build_response(a) for a in alerts],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> AlertResponse:
    """Get a single alert by ID with full details."""
    alert = await get_alert_by_id(db=db, alert_id=alert_id)
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert not found: {alert_id}",
        )
    return _build_response(alert)


@router.patch("/{alert_id}/status", response_model=AlertStatusUpdateResponse)
async def update_alert_status_endpoint(
    alert_id: str,
    payload: AlertStatusUpdate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> AlertStatusUpdateResponse:
    """Update alert status (close/escalate/in_review) with mandatory comment.

    Creates an immutable audit log entry recording the change.
    """
    alert = await get_alert_by_id(db=db, alert_id=alert_id)
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert not found: {alert_id}",
        )

    # Validate status transition
    if alert.status == "closed":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot update a closed alert",
        )

    updated_alert, audit_entry = await update_alert_status(
        db=db,
        alert=alert,
        new_status=payload.status,
        comment=payload.comment,
        actor_id=payload.actor_id,
    )

    return AlertStatusUpdateResponse(
        alert=_build_response(updated_alert),
        audit_entry_id=str(audit_entry.id),
        message=f"Alert status updated to '{payload.status}'",
    )