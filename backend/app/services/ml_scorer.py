"""AML Monitor — ML Scoring Service.

Isolation Forest-based anomaly detection with SHAP explainability.

Architecture:
- ``MLScorer`` is a singleton that lazily trains an Isolation Forest model
  on historical transaction features.
- ``score_transaction()`` extracts features for a single transaction and
  returns an anomaly score + SHAP explanation.
- The model is retrained periodically (triggered by Celery beat or API call).

Usage:
    scorer = MLScorer()
    result = await scorer.score_transaction(db, transaction)
    # result.anomaly_score  → float (0.0 = normal, 1.0 = highly anomalous)
    # result.risk_score     → Decimal (0.00–100.00, mapped from anomaly_score)
    # result.explanation    → dict of feature → SHAP value
"""

from __future__ import annotations

import logging
import pickle
from decimal import Decimal
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction
from app.services.feature_engineering import FEATURE_NAMES, extract_features

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_CONTAMINATION = 0.05  # expected proportion of anomalies
DEFAULT_N_ESTIMATORS = 200
DEFAULT_MAX_SAMPLES = 10000
MIN_TRAINING_SAMPLES = 50  # minimum samples before model can be trained

# Risk score mapping: anomaly_score (0..1) → risk_score (0..100)
# anomaly_score > ANOMALY_THRESHOLD → scaled to 50..100
# anomaly_score <= ANOMALY_THRESHOLD → scaled to 0..50
ANOMALY_THRESHOLD = 0.5

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


class MLScoreResult:
    """Result of ML-based anomaly scoring for a single transaction."""

    def __init__(
        self,
        anomaly_score: float,
        risk_score: Decimal,
        is_anomaly: bool,
        explanation: dict[str, float] | None = None,
    ) -> None:
        self.anomaly_score = anomaly_score
        self.risk_score = risk_score
        self.is_anomaly = is_anomaly
        self.explanation = explanation or {}


# ---------------------------------------------------------------------------
# ML Scorer (singleton)
# ---------------------------------------------------------------------------


class MLScorer:
    """Singleton ML scorer with lazy model training and SHAP explainability.

    Thread-safe for Celery workers: the model is loaded once per process.
    """

    _instance: MLScorer | None = None
    _model: Any = None  # IsolationForest
    _explainer: Any = None  # SHAP TreeExplainer
    _is_trained: bool = False
    _feature_names: list[str] = FEATURE_NAMES

    def __new__(cls) -> MLScorer:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def score_transaction(
        self,
        db: AsyncSession,
        transaction: Transaction,
    ) -> MLScoreResult:
        """Score a single transaction for anomaly.

        If the model is not yet trained, attempts a lazy training using
        historical transactions from the database.

        Args:
            db: Database session.
            transaction: The transaction to score.

        Returns:
            An ``MLScoreResult`` with anomaly score, risk score, and SHAP explanation.
        """
        if not self._is_trained:
            await self._lazy_train(db)

        features = await extract_features(db, transaction)
        return self._score_features(features)

    async def train(
        self,
        db: AsyncSession,
        force: bool = False,
    ) -> dict[str, Any]:
        """Train (or retrain) the Isolation Forest model on historical data.

        Args:
            db: Database session.
            force: If True, retrain even if already trained.

        Returns:
            A dict with training stats.
        """
        from sklearn.ensemble import IsolationForest

        # Load historical transactions
        result = await db.execute(
            select(Transaction).order_by(Transaction.txn_timestamp.desc())
        )
        transactions: list[Transaction] = list(result.scalars().all())

        if len(transactions) < MIN_TRAINING_SAMPLES:
            logger.warning(
                "Not enough transactions to train ML model: %d < %d",
                len(transactions),
                MIN_TRAINING_SAMPLES,
            )
            return {
                "status": "skipped",
                "samples": len(transactions),
                "min_required": MIN_TRAINING_SAMPLES,
            }

        # Extract features for all transactions
        feature_matrix: list[np.ndarray] = []
        for txn in transactions:
            try:
                feats = await extract_features(db, txn)
                feature_matrix.append(feats)
            except Exception:
                logger.exception("Feature extraction failed for txn %s", txn.id)
                continue

        if len(feature_matrix) < MIN_TRAINING_SAMPLES:
            return {
                "status": "skipped",
                "samples": len(feature_matrix),
                "min_required": MIN_TRAINING_SAMPLES,
            }

        X = np.array(feature_matrix)

        # Train Isolation Forest
        model = IsolationForest(
            n_estimators=DEFAULT_N_ESTIMATORS,
            max_samples=min(DEFAULT_MAX_SAMPLES, len(X)),
            contamination=DEFAULT_CONTAMINATION,
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X)

        self._model = model
        self._is_trained = True

        # Build SHAP explainer
        try:
            import shap

            self._explainer = shap.TreeExplainer(model)
        except Exception:
            logger.warning("SHAP explainer could not be created — skipping")
            self._explainer = None

        logger.info(
            "ML model trained on %d samples (contamination=%.2f)",
            len(X),
            DEFAULT_CONTAMINATION,
        )

        return {
            "status": "trained",
            "samples": len(X),
            "contamination": DEFAULT_CONTAMINATION,
            "n_estimators": DEFAULT_N_ESTIMATORS,
        }

    def get_model_info(self) -> dict[str, Any]:
        """Get information about the current model state."""
        return {
            "is_trained": self._is_trained,
            "model_type": "IsolationForest",
            "feature_count": len(self._feature_names),
            "feature_names": self._feature_names,
        }

    def serialize_model(self) -> bytes | None:
        """Serialize the trained model to bytes for caching."""
        if self._model is None:
            return None
        return pickle.dumps({"model": self._model, "feature_names": self._feature_names})

    def deserialize_model(self, data: bytes) -> None:
        """Load a previously serialized model."""
        obj = pickle.loads(data)
        self._model = obj["model"]
        self._feature_names = obj.get("feature_names", FEATURE_NAMES)
        self._is_trained = True
        try:
            import shap

            self._explainer = shap.TreeExplainer(self._model)
        except Exception:
            self._explainer = None

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    async def _lazy_train(self, db: AsyncSession) -> None:
        """Lazy training on first use."""
        try:
            await self.train(db)
        except Exception:
            logger.exception("Lazy training failed — ML scoring unavailable")

    def _score_features(self, features: np.ndarray) -> MLScoreResult:
        """Score a feature vector using the trained model."""
        if self._model is None:
            # Model not available — return neutral score
            return MLScoreResult(
                anomaly_score=0.0,
                risk_score=Decimal("0.00"),
                is_anomaly=False,
            )

        X = features.reshape(1, -1)

        # Isolation Forest decision_function: lower = more anomalous
        # We normalise to 0..1 where 1 = most anomalous
        raw_score = self._model.decision_function(X)[0]
        # Typical range: -0.5 (anomaly) to 0.5 (normal)
        # Map: anomaly_score = 1 - (raw_score + 0.5) / 1.0  → clamped to [0, 1]
        anomaly_score = 1.0 - (raw_score + 0.5)
        anomaly_score = max(0.0, min(1.0, anomaly_score))

        # Map to risk score 0..100
        if anomaly_score > ANOMALY_THRESHOLD:
            # 50..100 range
            risk_val = 50.0 + (anomaly_score - ANOMALY_THRESHOLD) * 100.0
        else:
            # 0..50 range
            risk_val = anomaly_score * 100.0

        risk_score = Decimal(str(min(100.0, max(0.0, risk_val))))

        is_anomaly = anomaly_score > ANOMALY_THRESHOLD

        # SHAP explanation
        explanation: dict[str, float] | None = None
        if self._explainer is not None and is_anomaly:
            try:
                shap_values = self._explainer.shap_values(X, check_additivity=False)
                if isinstance(shap_values, list):
                    shap_values = shap_values[0]
                # shap_values shape: (1, n_features)
                explanation = {
                    self._feature_names[i]: float(shap_values[0, i])
                    for i in range(len(self._feature_names))
                    if abs(float(shap_values[0, i])) > 0.01
                }
                # Sort by absolute value, take top 10
                explanation = dict(
                    sorted(
                        explanation.items(),
                        key=lambda x: abs(x[1]),
                        reverse=True,
                    )[:10]
                )
            except Exception:
                logger.exception("SHAP explanation failed")

        return MLScoreResult(
            anomaly_score=anomaly_score,
            risk_score=risk_score,
            is_anomaly=is_anomaly,
            explanation=explanation,
        )


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

_scorer: MLScorer | None = None


def get_scorer() -> MLScorer:
    """Get the singleton MLScorer instance."""
    global _scorer
    if _scorer is None:
        _scorer = MLScorer()
    return _scorer


async def score_transaction(
    db: AsyncSession,
    transaction: Transaction,
) -> MLScoreResult:
    """Convenience: score a transaction using the singleton scorer."""
    return await get_scorer().score_transaction(db, transaction)


async def train_model(
    db: AsyncSession,
    force: bool = False,
) -> dict[str, Any]:
    """Convenience: train/retrain the singleton scorer."""
    return await get_scorer().train(db, force=force)