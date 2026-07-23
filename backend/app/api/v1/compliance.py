"""AML Monitor — Compliance & Reporting API endpoints.

SAR export (CSV), audit log viewer, compliance dashboard stats.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import verify_api_key
from app.database import get_db
from app.services.sar_export import (
    export_alert_report_text,
    export_alerts_csv,
    get_compliance_stats,
)

router = APIRouter(prefix="/compliance", tags=["compliance"])


@router.get("/stats")
async def compliance_stats(
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> dict:
    """Get compliance dashboard statistics."""
    return await get_compliance_stats(db)


@router.get("/export/alerts.csv")
async def export_alerts(
    status: str | None = Query(None, description="Filter by status"),
    severity: str | None = Query(None, description="Filter by severity"),
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> StreamingResponse:
    """Export alerts as CSV for SAR reporting."""
    csv_content = await export_alerts_csv(
        db=db,
        status=status,
        severity=severity,
    )
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=alerts_export.csv",
        },
    )


@router.get("/export/alert/{alert_id}/report")
async def export_alert_report(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> PlainTextResponse:
    """Generate a SAR-style text report for a single alert."""
    report = await export_alert_report_text(db=db, alert_id=alert_id)
    return PlainTextResponse(
        content=report,
        headers={
            "Content-Disposition": f"attachment; filename=sar_report_{alert_id}.txt",
        },
    )