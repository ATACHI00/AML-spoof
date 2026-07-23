"""AML Monitor — Rule schemas.

Pydantic models for rule CRUD operations.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class RuleCreate(BaseModel):
    """Schema for creating a new rule."""

    name: str = Field(..., min_length=1, max_length=255, description="Human-readable rule name")
    slug: str = Field(..., min_length=1, max_length=128, description="Machine-readable identifier")
    description: str | None = Field(None, description="Rule description")
    detector_type: str = Field(
        ...,
        description="Detector type: structuring, rapid_movement, round_amount, velocity, geographic, dormant",
    )
    config: dict[str, Any] = Field(default_factory=dict, description="Thresholds and parameters as JSON")
    weight: Decimal = Field(default=Decimal("1.00"), ge=0, le=100, description="Weight for risk score")
    is_active: bool = Field(default=True, description="Whether the rule is active")


class RuleUpdate(BaseModel):
    """Schema for updating an existing rule."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    config: dict[str, Any] | None = None
    weight: Decimal | None = Field(None, ge=0, le=100)
    is_active: bool | None = None


class RuleResponse(BaseModel):
    """Schema for rule response."""

    id: str
    name: str
    slug: str
    description: str | None
    detector_type: str
    config: dict[str, Any]
    weight: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RuleListResponse(BaseModel):
    """Schema for listing rules."""

    rules: list[RuleResponse]
    total: int