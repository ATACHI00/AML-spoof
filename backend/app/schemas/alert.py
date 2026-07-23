"""AML Monitor — Alert schemas.

Pydantic models for alert listing, detail view, and status updates.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class AlertResponse(BaseModel):
    """Schema for alert response (list and detail)."""

    id: str
    transaction_id: str | None
    rule_id: str | None
    case_id: str | None
    severity: str
    risk_score: Decimal | None
    title: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AlertListResponse(BaseModel):
    """Schema for paginated alert list."""

    alerts: list[AlertResponse]
    total: int
    page: int
    page_size: int


class AlertStatusUpdate(BaseModel):
    """Schema for updating alert status (close/escalate)."""

    status: str = Field(
        ...,
        pattern=r"^(closed|escalated|in_review)$",
        description="New status: closed, escalated, or in_review",
    )
    comment: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Mandatory comment explaining the status change",
    )
    actor_id: str = Field(
        default="compliance-officer",
        description="Who performed the action",
    )


class AlertStatusUpdateResponse(BaseModel):
    """Schema for alert status update response."""

    alert: AlertResponse
    audit_entry_id: str
    message: str