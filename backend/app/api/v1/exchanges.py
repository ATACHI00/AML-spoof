"""AML Monitor — Exchange classification API endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import verify_api_key
from app.database import get_db
from app.models.exchange import Exchange
from app.schemas.exchange import (
    ExchangeCreate,
    ExchangeListResponse,
    ExchangeResponse,
    ExchangeStatsResponse,
)

router = APIRouter(prefix="/exchanges", tags=["exchanges"])


def _build_response(exchange: Exchange) -> ExchangeResponse:
    """Convert an Exchange ORM instance to ExchangeResponse."""
    import json

    # Parse countries from JSON string if needed
    countries = exchange.countries
    if isinstance(countries, str):
        try:
            countries = json.loads(countries)
        except json.JSONDecodeError:
            countries = []

    return ExchangeResponse(
        id=str(exchange.id),
        name=exchange.name,
        slug=exchange.slug,
        kyc_level=exchange.kyc_level,
        type=exchange.exchange_type,
        countries=countries,
        risk_score=float(exchange.risk_score) if exchange.risk_score else 0.0,
        is_active=exchange.is_active,
        created_at=exchange.created_at,
        updated_at=exchange.updated_at,
    )


@router.get("/stats", response_model=ExchangeStatsResponse)
async def get_exchange_stats(
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> ExchangeStatsResponse:
    """Get exchange statistics."""
    result = await db.execute(select(Exchange))
    exchanges = list(result.scalars().all())

    by_kyc_level: dict[str, int] = {}
    by_type: dict[str, int] = {}
    high_risk_count = 0

    for exchange in exchanges:
        kyc = exchange.kyc_level
        by_kyc_level[kyc] = by_kyc_level.get(kyc, 0) + 1

        ex_type = exchange.exchange_type
        by_type[ex_type] = by_type.get(ex_type, 0) + 1

        if float(exchange.risk_score) >= 50:
            high_risk_count += 1

    return ExchangeStatsResponse(
        total=len(exchanges),
        by_kyc_level=by_kyc_level,
        by_type=by_type,
        high_risk_count=high_risk_count,
    )


@router.get("/", response_model=ExchangeListResponse)
async def list_exchanges(
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
    kyc_level: str | None = None,
    exchange_type: str | None = None,
    is_active: bool | None = None,
) -> ExchangeListResponse:
    """List exchanges with optional filters."""
    query = select(Exchange)

    if kyc_level:
        query = query.where(Exchange.kyc_level == kyc_level)
    if exchange_type:
        query = query.where(Exchange.exchange_type == exchange_type)
    if is_active is not None:
        query = query.where(Exchange.is_active == is_active)

    query = query.order_by(Exchange.risk_score.desc())

    result = await db.execute(query)
    exchanges = list(result.scalars().all())

    return ExchangeListResponse(
        exchanges=[_build_response(e) for e in exchanges],
        total=len(exchanges),
    )


@router.get("/{exchange_id}", response_model=ExchangeResponse)
async def get_exchange(
    exchange_id: UUID,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> ExchangeResponse:
    """Get a single exchange by ID."""
    result = await db.execute(select(Exchange).where(Exchange.id == exchange_id))
    exchange = result.scalar_one_or_none()
    if exchange is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exchange not found: {exchange_id}",
        )
    return _build_response(exchange)


@router.post("/", response_model=ExchangeResponse, status_code=status.HTTP_201_CREATED)
async def create_exchange(
    payload: ExchangeCreate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> ExchangeResponse:
    """Create a new exchange."""
    # Check slug uniqueness
    result = await db.execute(select(Exchange).where(Exchange.slug == payload.slug))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Exchange with slug '{payload.slug}' already exists",
        )

    exchange = Exchange(
        name=payload.name,
        slug=payload.slug,
        kyc_level=payload.kyc_level,
        exchange_type=payload.type,
        countries=payload.countries,
        risk_score=payload.risk_score,
        is_active=payload.is_active,
    )
    db.add(exchange)
    await db.flush()
    await db.refresh(exchange)
    return _build_response(exchange)


@router.put("/{exchange_id}", response_model=ExchangeResponse)
async def update_exchange(
    exchange_id: UUID,
    payload: ExchangeCreate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> ExchangeResponse:
    """Update an existing exchange."""
    result = await db.execute(select(Exchange).where(Exchange.id == exchange_id))
    exchange = result.scalar_one_or_none()
    if exchange is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exchange not found: {exchange_id}",
        )

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(exchange, field, value)

    await db.flush()
    await db.refresh(exchange)
    return _build_response(exchange)


@router.delete("/{exchange_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exchange(
    exchange_id: UUID,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """Delete an exchange."""
    result = await db.execute(select(Exchange).where(Exchange.id == exchange_id))
    exchange = result.scalar_one_or_none()
    if exchange is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exchange not found: {exchange_id}",
        )
    await db.delete(exchange)
    await db.commit()
    return None


@router.get("/stats", response_model=ExchangeStatsResponse)
async def get_exchange_stats(
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> ExchangeStatsResponse:
    """Get exchange statistics."""
    result = await db.execute(select(Exchange))
    exchanges = list(result.scalars().all())

    by_kyc_level: dict[str, int] = {}
    by_type: dict[str, int] = {}
    high_risk_count = 0

    for exchange in exchanges:
        kyc = exchange.kyc_level
        by_kyc_level[kyc] = by_kyc_level.get(kyc, 0) + 1

        ex_type = exchange.exchange_type
        by_type[ex_type] = by_type.get(ex_type, 0) + 1

        if float(exchange.risk_score) >= 50:
            high_risk_count += 1

    return ExchangeStatsResponse(
        total=len(exchanges),
        by_kyc_level=by_kyc_level,
        by_type=by_type,
        high_risk_count=high_risk_count,
    )
