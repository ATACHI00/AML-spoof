"""AML Monitor — Sanctions screening service.

Provides functions to screen transaction parties (source/destination account
holders) and client names against the local sanctions list using fuzzy matching.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sanctions_list import SanctionsList
from app.utils.fuzzy import name_matches

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Screening result
# ---------------------------------------------------------------------------


class SanctionsMatchResult:
    """Result of screening a name against the sanctions list."""

    def __init__(
        self,
        triggered: bool = False,
        severity: str = "high",
        risk_score: Decimal = Decimal("0.00"),
        title: str = "",
        description: str = "",
        matches: list[dict[str, Any]] | None = None,
    ) -> None:
        self.triggered = triggered
        self.severity = severity
        self.risk_score = risk_score
        self.title = title
        self.description = description
        self.matches = matches or []


# ---------------------------------------------------------------------------
# Screening logic
# ---------------------------------------------------------------------------


async def screen_name_against_sanctions(
    db: AsyncSession,
    name: str,
    *,
    threshold: float = 0.88,
    method: str = "jaro_winkler",
    max_results: int = 5,
) -> SanctionsMatchResult:
    """Screen a single name against the local sanctions list.

    Args:
        db: Database session.
        name: The name to screen (e.g. account holder name).
        threshold: Similarity threshold (0.0–1.0).
        method: ``"jaro_winkler"`` or ``"levenshtein"``.
        max_results: Maximum number of top matches to return.

    Returns:
        A ``SanctionsMatchResult`` with match details.
    """
    # Load all active sanctions entries
    result = await db.execute(
        select(SanctionsList).where(SanctionsList.is_active == True)  # noqa: E712
    )
    entries: list[SanctionsList] = list(result.scalars().all())

    if not entries:
        return SanctionsMatchResult(triggered=False)

    scored_matches: list[tuple[float, SanctionsList, str]] = []

    for entry in entries:
        is_match, score, matched_name = name_matches(
            query_name=name,
            candidate_name=entry.full_name,
            method=method,
            threshold=threshold,
            candidate_variations=entry.name_variations,
        )
        if is_match:
            scored_matches.append((score, entry, matched_name))

    if not scored_matches:
        return SanctionsMatchResult(triggered=False)

    # Sort by score descending, take top N
    scored_matches.sort(key=lambda x: x[0], reverse=True)
    top_matches = scored_matches[:max_results]

    match_details: list[dict[str, Any]] = []
    for score, entry, matched_name in top_matches:
        match_details.append(
            {
                "sanctions_id": str(entry.id),
                "full_name": entry.full_name,
                "matched_name": matched_name,
                "score": score,
                "list_source": entry.list_source,
                "entity_type": entry.entity_type,
                "country": entry.country,
                "program": entry.program,
            }
        )

    # Calculate risk score based on best match
    best_score = top_matches[0][0]
    risk_score = min(Decimal(str(round(best_score * 100, 2))), Decimal("100"))

    # Determine severity
    if best_score >= 0.95:
        severity = "critical"
    elif best_score >= 0.90:
        severity = "high"
    else:
        severity = "medium"

    description_parts: list[str] = []
    for md in match_details:
        description_parts.append(
            f"'{md['full_name']}' ({md['list_source']}, score: {md['score']:.2f})"
        )

    return SanctionsMatchResult(
        triggered=True,
        severity=severity,
        risk_score=risk_score,
        title="Sanctions Match Detected",
        description="; ".join(description_parts),
        matches=match_details,
    )


async def screen_transaction_parties(
    db: AsyncSession,
    source_name: str | None,
    destination_name: str | None,
    *,
    threshold: float = 0.88,
    method: str = "jaro_winkler",
) -> SanctionsMatchResult:
    """Screen both parties of a transaction against the sanctions list.

    Args:
        db: Database session.
        source_name: Name of the source account holder (if available).
        destination_name: Name of the destination account holder (if available).
        threshold: Similarity threshold.
        method: Matching method.

    Returns:
        A ``SanctionsMatchResult``. If either party matches, the result
        is triggered with details of the best match.
    """
    names_to_check: list[tuple[str, str]] = []
    if source_name:
        names_to_check.append(("source", source_name))
    if destination_name:
        names_to_check.append(("destination", destination_name))

    if not names_to_check:
        return SanctionsMatchResult(triggered=False)

    all_matches: list[dict[str, Any]] = []
    best_risk = Decimal("0.00")
    best_severity = "medium"
    best_title = ""
    best_description = ""

    for role, party_name in names_to_check:
        result = await screen_name_against_sanctions(
            db=db,
            name=party_name,
            threshold=threshold,
            method=method,
        )
        if result.triggered:
            for m in result.matches:
                m["role"] = role
                m["screened_name"] = party_name
            all_matches.extend(result.matches)

            if result.risk_score > best_risk:
                best_risk = result.risk_score
                best_severity = result.severity
                best_title = result.title
                best_description = result.description

    if not all_matches:
        return SanctionsMatchResult(triggered=False)

    return SanctionsMatchResult(
        triggered=True,
        severity=best_severity,
        risk_score=best_risk,
        title=best_title,
        description=best_description,
        matches=all_matches,
    )


# ---------------------------------------------------------------------------
# Sanctions list management helpers
# ---------------------------------------------------------------------------


async def get_sanctions_stats(db: AsyncSession) -> dict[str, Any]:
    """Get summary statistics about the local sanctions list."""
    from sqlalchemy import func

    # Total count
    result = await db.execute(select(func.count(SanctionsList.id)))
    total = result.scalar() or 0

    # Count by source
    result = await db.execute(
        select(SanctionsList.list_source, func.count(SanctionsList.id))
        .group_by(SanctionsList.list_source)
    )
    by_source = {row[0]: row[1] for row in result.fetchall()}

    # Count by entity type
    result = await db.execute(
        select(SanctionsList.entity_type, func.count(SanctionsList.id))
        .group_by(SanctionsList.entity_type)
    )
    by_type = {row[0]: row[1] for row in result.fetchall()}

    return {
        "total": total,
        "by_source": by_source,
        "by_type": by_type,
    }


async def search_sanctions(
    db: AsyncSession,
    query: str,
    *,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[SanctionsList], int]:
    """Search sanctions list by name (exact/prefix match on full_name)."""
    from sqlalchemy import func

    like_pattern = f"%{query}%"

    count_result = await db.execute(
        select(func.count(SanctionsList.id)).where(
            SanctionsList.full_name.ilike(like_pattern)
        )
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(SanctionsList)
        .where(SanctionsList.full_name.ilike(like_pattern))
        .order_by(SanctionsList.full_name)
        .offset(offset)
        .limit(limit)
    )
    entries = list(result.scalars().all())

    return entries, total