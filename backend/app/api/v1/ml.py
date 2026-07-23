"""AML Monitor — ML Scoring API endpoints.

Endpoints for ML model management and transaction scoring.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import verify_api_key
from app.database import get_db
from app.models.transaction import Transaction
from app.schemas.ml import (
    MLFeaturesResponse,
    MLModelInfoResponse,
    MLScoreRequest,
    MLScoreResponse,
    MLTrainResponse,
)
from app.services.feature_engineering import FEATURE_NAMES, extract_features
from app.services.ml_scorer import get_scorer, train_model

router = APIRouter(prefix="/ml", tags=["ml"])


def _resolve_transaction(db: AsyncSession, txn_id: str) -> Transaction | None:
    """Resolve a transaction ID string to a Transaction ORM instance.

    Handles both UUID and string IDs for SQLite compatibility.
    """
    try:
        txn_uuid = uuid.UUID(txn_id)
    except ValueError:
        return None
    return None  # async — this is a placeholder, actual impl below


@router.get("/model", response_model=MLModelInfoResponse)
async def get_model_info(
    api_key: str = Depends(verify_api_key),
) -> MLModelInfoResponse:
    """Get information about the current ML model state."""
    scorer = get_scorer()
    info = scorer.get_model_info()
    return MLModelInfoResponse(
        is_trained=info["is_trained"],
        model_type=info["model_type"],
        feature_count=info["feature_count"],
        feature_names=info["feature_names"],
    )


@router.post("/train", response_model=MLTrainResponse)
async def train_ml_model(
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> MLTrainResponse:
    """Train (or retrain) the Isolation Forest model on historical data.

    Requires at least 50 transactions in the database to train.
    """
    result = await train_model(db)

    from datetime import datetime, timezone

    return MLTrainResponse(
        status=result["status"],
        samples=result["samples"],
        min_required=result.get("min_required"),
        contamination=result.get("contamination"),
        n_estimators=result.get("n_estimators"),
        trained_at=datetime.now(timezone.utc) if result["status"] == "trained" else None,
    )


async def _get_transaction_by_id(
    db: AsyncSession, txn_id: str
) -> Transaction | None:
    """Load a transaction by ID, handling UUID conversion."""
    try:
        txn_uuid = uuid.UUID(txn_id)
    except ValueError:
        return None
    result = await db.execute(
        select(Transaction).where(Transaction.id == txn_uuid)
    )
    return result.scalar_one_or_none()


@router.post("/score", response_model=MLScoreResponse)
async def score_transaction_ml(
    payload: MLScoreRequest,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> MLScoreResponse:
    """Score a single transaction using the ML model.

    Returns anomaly score, risk score, and SHAP explanation.
    """
    transaction = await _get_transaction_by_id(db, payload.transaction_id)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction not found: {payload.transaction_id}",
        )

    scorer = get_scorer()
    score_result = await scorer.score_transaction(db, transaction)

    return MLScoreResponse(
        transaction_id=str(transaction.id),
        anomaly_score=score_result.anomaly_score,
        risk_score=score_result.risk_score,
        is_anomaly=score_result.is_anomaly,
        explanation=score_result.explanation,
        model_trained=scorer.get_model_info()["is_trained"],
    )


@router.post("/features", response_model=MLFeaturesResponse)
async def get_transaction_features(
    payload: MLScoreRequest,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> MLFeaturesResponse:
    """Extract and return feature vector for a transaction (debug endpoint)."""
    transaction = await _get_transaction_by_id(db, payload.transaction_id)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction not found: {payload.transaction_id}",
        )

    features = await extract_features(db, transaction)

    return MLFeaturesResponse(
        transaction_id=str(transaction.id),
        feature_names=FEATURE_NAMES,
        feature_values=features.tolist(),
    )