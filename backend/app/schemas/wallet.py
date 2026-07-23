"""AML Monitor — Wallet schemas.

Pydantic models for wallet management and risk scoring.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class WalletCreate(BaseModel):
    """Schema for creating a new wallet."""

    address: str = Field(..., description="Cryptocurrency wallet address")
    currency: str = Field(..., description="Currency: BTC, ETH, USDT, XMR, etc.")
    label: str | None = Field(None, description="Human-readable label")
    exchange_id: str | None = Field(None, description="Associated exchange ID")
    is_sanctioned: bool = Field(default=False, description="Is wallet sanctioned")
    risk_score: Decimal = Field(default=Decimal("0.00"), ge=0, le=100)


class WalletResponse(BaseModel):
    """Schema for wallet response."""

    id: str
    address: str
    currency: str
    label: str | None
    exchange_id: str | None
    is_sanctioned: bool
    risk_score: Decimal
    first_seen: date | None
    last_seen: date | None
    total_received: Decimal
    total_sent: Decimal
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WalletListResponse(BaseModel):
    """Schema for wallet list response."""

    wallets: list[WalletResponse]
    total: int
    page: int = 1
    page_size: int = 20


class WalletRiskUpdate(BaseModel):
    """Schema for updating wallet risk score."""

    risk_score: Decimal = Field(..., ge=0, le=100, description="New risk score")
    reason: str = Field(..., description="Reason for risk score change")


class WalletTransactionRequest(BaseModel):
    """Schema for checking wallet transaction history."""

    address: str = Field(..., description="Wallet address to check")
    currency: str = Field(..., description="Currency: BTC, ETH, USDT, XMR")
    days_back: int = Field(default=30, ge=1, le=365, description="Days to look back")


class WalletRiskResponse(BaseModel):
    """Response with wallet risk analysis."""

    address: str
    currency: str
    risk_score: Decimal
    is_sanctioned: bool
    total_transactions: int
    total_volume: Decimal
    days_active: int
    risk_factors: list[str] = []
    recommendations: list[str] = []
