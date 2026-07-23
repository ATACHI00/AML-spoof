"""AML Monitor — Pydantic schemas for sanctions screening."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Sanctions list entry
# ---------------------------------------------------------------------------


class SanctionsEntryResponse(BaseModel):
    """Schema for a single sanctions list entry."""

    id: str
    list_source: str
    full_name: str
    name_variations: list[str] | None = None
    entity_type: str
    country: str | None = None
    program: str | None = None
    is_active: bool = True
    last_updated: date | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class SanctionsListResponse(BaseModel):
    """Schema for paginated sanctions list response."""

    entries: list[SanctionsEntryResponse]
    total: int
    page: int = 1
    page_size: int = 20


# ---------------------------------------------------------------------------
# Screening
# ---------------------------------------------------------------------------


class SanctionsMatchDetail(BaseModel):
    """Details of a single sanctions match."""

    sanctions_id: str
    full_name: str
    matched_name: str
    score: float
    list_source: str
    entity_type: str
    country: str | None = None
    program: str | None = None
    role: str | None = None  # "source" or "destination"
    screened_name: str | None = None


class SanctionsScreenResult(BaseModel):
    """Result of screening a name/transaction against sanctions lists."""

    triggered: bool
    severity: str = "low"
    risk_score: Decimal = Decimal("0.00")
    title: str = ""
    description: str = ""
    matches: list[SanctionsMatchDetail] = []


class SanctionsScreenRequest(BaseModel):
    """Request body for screening a name."""

    name: str = Field(..., min_length=1, max_length=512, description="Name to screen")
    threshold: float = Field(
        0.88, ge=0.0, le=1.0, description="Similarity threshold (0.0–1.0)"
    )
    method: str = Field(
        "jaro_winkler",
        pattern=r"^(jaro_winkler|levenshtein)$",
        description="Matching method",
    )


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


class SanctionsImportResponse(BaseModel):
    """Response after importing sanctions data."""

    imported: int
    source: str = "ofac"
    message: str


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class SanctionsStatsResponse(BaseModel):
    """Sanctions list statistics."""

    total: int
    by_source: dict[str, int]
    by_type: dict[str, int]