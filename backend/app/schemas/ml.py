"""AML Monitor — ML Scoring schemas.

Pydantic models for ML scoring request/response and model management.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class MLScoreRequest(BaseModel):
    """Schema for requesting ML scoring of a specific transaction."""

    transaction_id: str = Field(..., description="UUID of the transaction to score")


class MLScoreResponse(BaseModel):
    """Schema for ML scoring result."""

    transaction_id: str
    anomaly_score: float = Field(..., ge=0.0, le=1.0)
    risk_score: Decimal = Field(..., ge=0, le=100)
    is_anomaly: bool
    explanation: dict[str, float] | None = None
    model_trained: bool


class MLModelInfoResponse(BaseModel):
    """Schema for ML model information."""

    is_trained: bool
    model_type: str
    feature_count: int
    feature_names: list[str]


class MLTrainResponse(BaseModel):
    """Schema for model training result."""

    status: str
    samples: int
    min_required: int | None = None
    contamination: float | None = None
    n_estimators: int | None = None
    trained_at: datetime | None = None


class MLFeaturesResponse(BaseModel):
    """Schema for transaction features (debug/explainability)."""

    transaction_id: str
    feature_names: list[str]
    feature_values: list[float]