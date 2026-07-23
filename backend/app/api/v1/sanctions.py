"""AML Monitor — Sanctions screening API endpoints.

Provides endpoints for:
- Screening names against sanctions lists
- Managing the local sanctions list (list, search, import)
- Viewing sanctions list statistics
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import verify_api_key
from app.database import get_db
from app.schemas.sanctions import (
    SanctionsEntryResponse,
    SanctionsImportResponse,
    SanctionsListResponse,
    SanctionsScreenRequest,
    SanctionsScreenResult,
    SanctionsStatsResponse,
)
from app.services.sanctions_service import (
    SanctionsMatchResult,
    get_sanctions_stats,
    screen_name_against_sanctions,
    search_sanctions,
)
from app.services.sanctions_provider import import_ofac_sdn

router = APIRouter(prefix="/sanctions", tags=["sanctions"])


def _build_entry_response(entry) -> SanctionsEntryResponse:
    """Convert a SanctionsList ORM instance to a SanctionsEntryResponse."""
    return SanctionsEntryResponse(
        id=str(entry.id),
        list_source=entry.list_source,
        full_name=entry.full_name,
        name_variations=entry.name_variations,
        entity_type=entry.entity_type,
        country=entry.country,
        program=entry.program,
        is_active=entry.is_active,
        last_updated=entry.last_updated,
        created_at=entry.created_at,
    )


def _build_screen_result(result: SanctionsMatchResult) -> SanctionsScreenResult:
    """Convert a SanctionsMatchResult to a SanctionsScreenResult schema."""
    from app.schemas.sanctions import SanctionsMatchDetail

    return SanctionsScreenResult(
        triggered=result.triggered,
        severity=result.severity,
        risk_score=result.risk_score,
        title=result.title,
        description=result.description,
        matches=[
            SanctionsMatchDetail(**m) for m in (result.matches or [])
        ],
    )


# ---------------------------------------------------------------------------
# Screening
# ---------------------------------------------------------------------------


@router.post("/screen", response_model=SanctionsScreenResult)
async def screen_name(
    payload: SanctionsScreenRequest,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> SanctionsScreenResult:
    """Screen a name against the local sanctions list.

    Uses fuzzy matching (Jaro-Winkler or Levenshtein) to find potential
    matches. Returns match details including similarity scores.
    """
    result = await screen_name_against_sanctions(
        db=db,
        name=payload.name,
        threshold=payload.threshold,
        method=payload.method,
    )
    return _build_screen_result(result)


# ---------------------------------------------------------------------------
# Sanctions list management
# ---------------------------------------------------------------------------


@router.get("/entries", response_model=SanctionsListResponse)
async def list_sanctions_entries(
    query: str | None = Query(None, description="Search by name"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> SanctionsListResponse:
    """List or search sanctions list entries."""
    if query:
        entries, total = await search_sanctions(
            db=db,
            query=query,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
    else:
        from sqlalchemy import func, select

        from app.models.sanctions_list import SanctionsList

        # Get total count
        count_result = await db.execute(select(func.count(SanctionsList.id)))
        total = count_result.scalar() or 0

        result = await db.execute(
            select(SanctionsList)
            .order_by(SanctionsList.full_name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        entries = list(result.scalars().all())

    return SanctionsListResponse(
        entries=[_build_entry_response(e) for e in entries],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=SanctionsStatsResponse)
async def sanctions_stats(
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> SanctionsStatsResponse:
    """Get sanctions list statistics."""
    stats = await get_sanctions_stats(db=db)
    return SanctionsStatsResponse(**stats)


@router.post("/import", response_model=SanctionsImportResponse)
async def import_sanctions(
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> SanctionsImportResponse:
    """Import the latest OFAC SDN list from the US Treasury website.

    Downloads, parses, and stores new entries in the local database.
    Existing entries are skipped (idempotent).
    """
    try:
        from app.database import _get_session_factory

        factory = _get_session_factory()
        imported = await import_ofac_sdn(factory)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to import OFAC SDN list: {exc}",
        )

    return SanctionsImportResponse(
        imported=imported,
        source="ofac",
        message=f"Successfully imported {imported} new sanctions entries",
    )