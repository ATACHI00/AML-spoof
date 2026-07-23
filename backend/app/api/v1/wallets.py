"""AML Monitor — Wallet API endpoints.

CRUD operations for cryptocurrency wallet management and risk analysis.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import verify_api_key
from app.database import get_db
from app.models.wallet import Wallet
from app.schemas.wallet import (
    WalletCreate,
    WalletListResponse,
    WalletResponse,
    WalletRiskUpdate,
    WalletRiskResponse,
    WalletTransactionRequest,
)

router = APIRouter(prefix="/wallets", tags=["wallets"])


def _build_response(wallet: Wallet) -> WalletResponse:
    """Convert a Wallet ORM instance to WalletResponse."""
    return WalletResponse(
        id=str(wallet.id),
        address=wallet.address,
        currency=wallet.currency,
        label=wallet.label,
        exchange_id=str(wallet.exchange_id) if wallet.exchange_id else None,
        is_sanctioned=wallet.is_sanctioned,
        risk_score=wallet.risk_score,
        first_seen=wallet.first_seen,
        last_seen=wallet.last_seen,
        total_received=wallet.total_received,
        total_sent=wallet.total_sent,
        created_at=wallet.created_at,
        updated_at=wallet.updated_at,
    )


@router.get("/", response_model=WalletListResponse)
async def list_wallets(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    currency: str | None = Query(None, description="Filter by currency"),
    is_sanctioned: bool | None = Query(None, description="Filter by sanctioned status"),
    min_risk_score: float | None = Query(None, description="Minimum risk score filter"),
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> WalletListResponse:
    """List wallets with optional filters."""
    query = select(Wallet)

    if currency:
        query = query.where(Wallet.currency == currency)
    if is_sanctioned is not None:
        query = query.where(Wallet.is_sanctioned == is_sanctioned)
    if min_risk_score is not None:
        query = query.where(Wallet.risk_score >= min_risk_score)

    query = query.order_by(Wallet.risk_score.desc())

    # Get total count
    count_query = select(Wallet)
    if currency:
        count_query = count_query.where(Wallet.currency == currency)
    if is_sanctioned is not None:
        count_query = count_query.where(Wallet.is_sanctioned == is_sanctioned)
    if min_risk_score is not None:
        count_query = count_query.where(Wallet.risk_score >= min_risk_score)

    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    wallets = list(result.scalars().all())

    return WalletListResponse(
        wallets=[_build_response(w) for w in wallets],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{wallet_id}", response_model=WalletResponse)
async def get_wallet(
    wallet_id: str,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> WalletResponse:
    """Get a single wallet by ID."""
    try:
        wallet_uuid = UUID(wallet_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid wallet ID format",
        )

    result = await db.execute(select(Wallet).where(Wallet.id == wallet_uuid))
    wallet = result.scalar_one_or_none()
    if wallet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Wallet not found: {wallet_id}",
        )
    return _build_response(wallet)


@router.post("/", response_model=WalletResponse, status_code=status.HTTP_201_CREATED)
async def create_wallet(
    payload: WalletCreate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> WalletResponse:
    """Create a new wallet."""
    # Check if wallet already exists
    result = await db.execute(select(Wallet).where(Wallet.address == payload.address))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Wallet already exists: {payload.address}",
        )

    wallet = Wallet(
        address=payload.address,
        currency=payload.currency,
        label=payload.label,
        exchange_id=payload.exchange_id,
        is_sanctioned=payload.is_sanctioned,
        risk_score=payload.risk_score,
    )
    db.add(wallet)
    await db.flush()
    await db.refresh(wallet)
    return _build_response(wallet)


@router.patch("/{wallet_id}/risk", response_model=WalletResponse)
async def update_wallet_risk(
    wallet_id: str,
    payload: WalletRiskUpdate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> WalletResponse:
    """Update wallet risk score."""
    try:
        wallet_uuid = UUID(wallet_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid wallet ID format",
        )

    result = await db.execute(select(Wallet).where(Wallet.id == wallet_uuid))
    wallet = result.scalar_one_or_none()
    if wallet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Wallet not found: {wallet_id}",
        )

    wallet.risk_score = payload.risk_score
    wallet.notes = f"Risk updated: {payload.reason}"
    await db.flush()
    await db.refresh(wallet)
    return _build_response(wallet)


@router.delete("/{wallet_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wallet(
    wallet_id: str,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """Delete a wallet."""
    try:
        wallet_uuid = UUID(wallet_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid wallet ID format",
        )

    result = await db.execute(select(Wallet).where(Wallet.id == wallet_uuid))
    wallet = result.scalar_one_or_none()
    if wallet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Wallet not found: {wallet_id}",
        )
    await db.delete(wallet)
    await db.commit()
    return None


@router.post("/analyze", response_model=WalletRiskResponse)
async def analyze_wallet_risk(
    payload: WalletTransactionRequest,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> WalletRiskResponse:
    """Analyze wallet risk based on transaction history."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func, select

    from app.models.transaction import Transaction

    # Find or create wallet record
    result = await db.execute(
        select(Wallet).where(
            Wallet.address == payload.address,
            Wallet.currency == payload.currency,
        )
    )
    wallet = result.scalar_one_or_none()

    cutoff = datetime.now(timezone.utc) - timedelta(days=payload.days_back)

    # Count transactions
    result = await db.execute(
        select(func.count(Transaction.id)).where(
            (Transaction.source_account_number == payload.address)
            | (Transaction.destination_account_number == payload.address),
            Transaction.currency == payload.currency,
            Transaction.txn_timestamp >= cutoff,
        )
    )
    total_transactions = result.scalar() or 0

    # Get total volume
    result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            (Transaction.source_account_number == payload.address)
            | (Transaction.destination_account_number == payload.address),
            Transaction.currency == payload.currency,
            Transaction.txn_timestamp >= cutoff,
        )
    )
    total_volume = result.scalar() or 0

    # Calculate risk factors
    risk_factors = []
    recommendations = []

    if wallet and wallet.is_sanctioned:
        risk_factors.append("Wallet is on sanctions list")
        recommendations.append("Immediately freeze transactions and file SAR")

    if wallet and wallet.risk_score >= 50:
        risk_factors.append(f"High risk score: {wallet.risk_score}")
        recommendations.append("Increase monitoring frequency")

    if total_transactions > 100:
        risk_factors.append("High transaction volume")
        recommendations.append("Review transaction patterns for structuring")

    if total_volume > 100000:
        risk_factors.append("Large transaction volumes")
        recommendations.append("Verify source of funds")

    # Determine overall risk score
    base_risk = float(wallet.risk_score) if wallet else 0.0
    risk_multiplier = 1.0
    if total_transactions > 50:
        risk_multiplier += 0.2
    if total_volume > 50000:
        risk_multiplier += 0.3

    final_risk = min(100.0, base_risk * risk_multiplier)

    return WalletRiskResponse(
        address=payload.address,
        currency=payload.currency,
        risk_score=round(final_risk, 2),
        is_sanctioned=wallet.is_sanctioned if wallet else False,
        total_transactions=total_transactions,
        total_volume=total_volume,
        days_active=payload.days_back,
        risk_factors=risk_factors,
        recommendations=recommendations,
    )
