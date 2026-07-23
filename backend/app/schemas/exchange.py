"""Exchange classification schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ExchangeCreate(BaseModel):
    """Schema for creating an exchange."""
    name: str = Field(..., description="Exchange name")
    slug: str = Field(..., description="URL-friendly slug")
    kyc_level: str = Field(..., description="KYC level: none, basic, full, enterprise")
    type: str = Field(..., description="Exchange type: cex, dex, p2p, mixer, casino")
    countries: list[str] = Field(default_factory=list, description="Countries of operation")
    risk_score: Decimal = Field(default=Decimal("0.00"), ge=0, le=100, description="Risk score 0-100")
    is_active: bool = Field(default=True)


class ExchangeResponse(BaseModel):
    """Schema for exchange response."""
    id: str
    name: str
    slug: str
    kyc_level: str
    type: str
    countries: list[str]
    risk_score: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ExchangeListResponse(BaseModel):
    """Schema for exchange list response."""
    exchanges: list[ExchangeResponse]
    total: int


class ExchangeStatsResponse(BaseModel):
    """Schema for exchange statistics."""
    total: int
    by_kyc_level: dict[str, int] = Field(default_factory=dict)
    by_type: dict[str, int] = Field(default_factory=dict)
    high_risk_count: int = Field(default=0)
