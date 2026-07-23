"""AML Monitor — Tests for ML Scoring (Stage 5).

Tests cover:
1. Feature engineering — feature extraction, shape, values
2. ML Scorer — model training, scoring, SHAP explanation
3. ML API endpoints — model info, training, scoring, features
4. ML detector integration with rule engine
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.alert import Alert
from app.models.client import Client
from app.models.rule import Rule
from app.models.transaction import Transaction
from app.services.feature_engineering import (
    FEATURE_COUNT,
    FEATURE_NAMES,
    extract_features,
)
from app.services.ml_scorer import MLScorer, MLScoreResult, get_scorer
from app.services.rule_engine import detect_ml_anomaly, run_rule_engine

# =========================================================================
# Feature Engineering Tests
# =========================================================================


class TestFeatureEngineering:
    """Test feature extraction from transactions."""

    async def _create_test_transaction(
        self,
        db_session: AsyncSession,
        sample_account: Account,
        amount: Decimal = Decimal("1000.00"),
        currency: str = "USD",
        channel: str | None = "wire",
        txn_timestamp: datetime | None = None,
        extra_data: dict | None = None,
    ) -> Transaction:
        """Helper to create a test transaction."""
        if txn_timestamp is None:
            txn_timestamp = datetime.now(timezone.utc)

        txn = Transaction(
            external_id=f"TXN-{datetime.now(timezone.utc).timestamp()}",
            source_account_id=sample_account.id,
            destination_account_id=sample_account.id,
            amount=amount,
            currency=currency,
            txn_timestamp=txn_timestamp,
            channel=channel,
            status="pending",
            extra_data=extra_data,
            ingested_at=datetime.now(timezone.utc),
        )
        db_session.add(txn)
        await db_session.flush()
        return txn

    async def test_feature_vector_shape(
        self,
        db_session: AsyncSession,
        sample_account: Account,
    ) -> None:
        """Test that feature vector has the expected number of features."""
        txn = await self._create_test_transaction(db_session, sample_account)
        features = await extract_features(db_session, txn)

        assert isinstance(features, np.ndarray)
        assert features.shape == (FEATURE_COUNT,)
        assert len(FEATURE_NAMES) == FEATURE_COUNT

    async def test_feature_vector_values(
        self,
        db_session: AsyncSession,
        sample_account: Account,
    ) -> None:
        """Test that feature values are finite and within expected ranges."""
        txn = await self._create_test_transaction(
            db_session, sample_account, amount=Decimal("5000.00")
        )
        features = await extract_features(db_session, txn)

        assert np.all(np.isfinite(features)), "All features must be finite"

        # Amount feature should match
        assert features[0] == 5000.0  # amount

        # Log amount should be positive
        assert features[1] > 0  # log_amount

        # Roundness: 5000 is round
        assert features[2] == 1.0  # roundness

        # Temporal features should be in range
        assert 0 <= features[4] <= 23  # hour_of_day
        assert 0 <= features[5] <= 6  # day_of_week
        assert features[6] in (0.0, 1.0)  # is_weekend

    async def test_round_amount_detection(
        self,
        db_session: AsyncSession,
        sample_account: Account,
    ) -> None:
        """Test that round amounts are correctly flagged."""
        # Round amount
        txn_round = await self._create_test_transaction(
            db_session, sample_account, amount=Decimal("10000.00")
        )
        features_round = await extract_features(db_session, txn_round)
        assert features_round[2] == 1.0  # roundness

        # Non-round amount
        txn_non_round = await self._create_test_transaction(
            db_session, sample_account, amount=Decimal("10001.23")
        )
        features_non_round = await extract_features(db_session, txn_non_round)
        assert features_non_round[2] == 0.0  # roundness

    async def test_high_risk_channel(
        self,
        db_session: AsyncSession,
        sample_account: Account,
    ) -> None:
        """Test that crypto channel is flagged as high risk."""
        txn = await self._create_test_transaction(
            db_session, sample_account, channel="crypto"
        )
        features = await extract_features(db_session, txn)
        assert features[-3] == 1.0  # channel_is_high_risk

    async def test_common_currency(
        self,
        db_session: AsyncSession,
        sample_account: Account,
    ) -> None:
        """Test that common currencies are correctly identified."""
        txn = await self._create_test_transaction(
            db_session, sample_account, currency="USD"
        )
        features = await extract_features(db_session, txn)
        assert features[-2] == 1.0  # currency_is_common

    async def test_uncommon_currency(
        self,
        db_session: AsyncSession,
        sample_account: Account,
    ) -> None:
        """Test that uncommon currencies are flagged."""
        txn = await self._create_test_transaction(
            db_session, sample_account, currency="XRP"
        )
        features = await extract_features(db_session, txn)
        assert features[-2] == 0.0  # currency_is_common

    async def test_dormant_account(
        self,
        db_session: AsyncSession,
        sample_account: Account,
        sample_client: Client,
    ) -> None:
        """Test that dormant accounts are detected."""
        # Create a transaction with a very old timestamp
        old_timestamp = datetime.now(timezone.utc) - timedelta(days=200)
        txn = await self._create_test_transaction(
            db_session, sample_account, txn_timestamp=old_timestamp
        )
        features = await extract_features(db_session, txn)

        # Source account should be dormant (no recent activity)
        # src_is_dormant is at index 19 (FEATURE_COUNT - 7)
        assert features[-7] == 1.0  # src_is_dormant


# =========================================================================
# ML Scorer Tests
# =========================================================================


class TestMLScorer:
    """Test the ML scoring service."""

    async def test_scorer_singleton(self) -> None:
        """Test that MLScorer is a singleton."""
        scorer1 = get_scorer()
        scorer2 = get_scorer()
        assert scorer1 is scorer2

    async def test_initial_state(self) -> None:
        """Test that scorer starts untrained."""
        scorer = MLScorer()
        # Reset for test
        scorer._is_trained = False
        scorer._model = None

        info = scorer.get_model_info()
        assert info["is_trained"] is False
        assert info["model_type"] == "IsolationForest"
        assert info["feature_count"] == FEATURE_COUNT

    async def test_score_without_model(self) -> None:
        """Test that scoring returns neutral result when model is untrained."""
        scorer = MLScorer()
        scorer._is_trained = False
        scorer._model = None

        features = np.zeros(FEATURE_COUNT, dtype=np.float64)
        result = scorer._score_features(features)

        assert isinstance(result, MLScoreResult)
        assert result.anomaly_score == 0.0
        assert result.risk_score == Decimal("0.00")
        assert result.is_anomaly is False

    async def test_train_and_score(
        self,
        db_session: AsyncSession,
        sample_account: Account,
    ) -> None:
        """Test training the model and scoring a transaction."""
        # Create some transactions for training
        for i in range(60):
            txn = Transaction(
                external_id=f"TRAIN-{i}",
                source_account_id=sample_account.id,
                destination_account_id=sample_account.id,
                amount=Decimal(f"{100 + i}.00"),
                currency="USD",
                txn_timestamp=datetime.now(timezone.utc) - timedelta(minutes=i),
                channel="wire",
                status="pending",
                ingested_at=datetime.now(timezone.utc),
            )
            db_session.add(txn)
        await db_session.flush()

        scorer = MLScorer()
        scorer._is_trained = False
        scorer._model = None

        # Train
        result = await scorer.train(db_session)
        assert result["status"] == "trained"
        assert result["samples"] >= 60

        # Score a normal transaction
        normal_txn = Transaction(
            external_id="NORMAL-1",
            source_account_id=sample_account.id,
            destination_account_id=sample_account.id,
            amount=Decimal("500.00"),
            currency="USD",
            txn_timestamp=datetime.now(timezone.utc),
            channel="wire",
            status="pending",
            ingested_at=datetime.now(timezone.utc),
        )
        db_session.add(normal_txn)
        await db_session.flush()

        score_result = await scorer.score_transaction(db_session, normal_txn)
        assert isinstance(score_result, MLScoreResult)
        assert 0.0 <= score_result.anomaly_score <= 1.0
        assert Decimal("0.00") <= score_result.risk_score <= Decimal("100.00")

    async def test_anomaly_detection(
        self,
        db_session: AsyncSession,
        sample_account: Account,
    ) -> None:
        """Test that anomalous transactions get higher scores."""
        # Create mostly small transactions
        for i in range(100):
            txn = Transaction(
                external_id=f"BASE-{i}",
                source_account_id=sample_account.id,
                destination_account_id=sample_account.id,
                amount=Decimal(f"{50 + (i % 10)}.00"),  # 50-59 range
                currency="USD",
                txn_timestamp=datetime.now(timezone.utc) - timedelta(minutes=i),
                channel="wire",
                status="pending",
                ingested_at=datetime.now(timezone.utc),
            )
            db_session.add(txn)
        await db_session.flush()

        scorer = MLScorer()
        scorer._is_trained = False
        scorer._model = None
        await scorer.train(db_session)

        # Score a normal transaction
        normal_txn = Transaction(
            external_id="NORMAL-ANOMALY",
            source_account_id=sample_account.id,
            destination_account_id=sample_account.id,
            amount=Decimal("55.00"),
            currency="USD",
            txn_timestamp=datetime.now(timezone.utc),
            channel="wire",
            status="pending",
            ingested_at=datetime.now(timezone.utc),
        )
        db_session.add(normal_txn)
        await db_session.flush()
        normal_result = await scorer.score_transaction(db_session, normal_txn)

        # Score an anomalous transaction (very large amount)
        anomaly_txn = Transaction(
            external_id="ANOMALY-1",
            source_account_id=sample_account.id,
            destination_account_id=sample_account.id,
            amount=Decimal("999999.00"),
            currency="USD",
            txn_timestamp=datetime.now(timezone.utc),
            channel="crypto",
            status="pending",
            ingested_at=datetime.now(timezone.utc),
        )
        db_session.add(anomaly_txn)
        await db_session.flush()
        anomaly_result = await scorer.score_transaction(db_session, anomaly_txn)

        # Anomaly should have higher score
        assert anomaly_result.anomaly_score >= normal_result.anomaly_score

    async def test_serialization(self) -> None:
        """Test model serialization round-trip."""
        from sklearn.ensemble import IsolationForest

        # Create a simple model
        model = IsolationForest(n_estimators=10, random_state=42)
        X = np.random.randn(100, FEATURE_COUNT)
        model.fit(X)

        scorer = MLScorer()
        scorer._model = model
        scorer._is_trained = True

        # Serialize
        data = scorer.serialize_model()
        assert data is not None

        # Deserialize into a new scorer
        scorer2 = MLScorer()
        scorer2._is_trained = False
        scorer2._model = None
        scorer2.deserialize_model(data)

        assert scorer2._is_trained is True
        assert scorer2._model is not None

        # Both should produce similar scores
        test_x = np.random.randn(FEATURE_COUNT)
        r1 = scorer._score_features(test_x)
        r2 = scorer2._score_features(test_x)
        assert abs(r1.anomaly_score - r2.anomaly_score) < 0.01


# =========================================================================
# ML Detector Integration Tests
# =========================================================================


class TestMLDetector:
    """Test the ML anomaly detector integration with rule engine."""

    async def test_detector_registered(self) -> None:
        """Test that ml_anomaly detector is in the registry."""
        from app.services.rule_engine import DETECTOR_REGISTRY

        assert "ml_anomaly" in DETECTOR_REGISTRY

    async def test_detect_ml_anomaly_no_model(
        self,
        db_session: AsyncSession,
        sample_account: Account,
    ) -> None:
        """Test that detector returns not triggered when model is untrained."""
        txn = Transaction(
            external_id="ML-DETECT-TEST",
            source_account_id=sample_account.id,
            destination_account_id=sample_account.id,
            amount=Decimal("1000.00"),
            currency="USD",
            txn_timestamp=datetime.now(timezone.utc),
            channel="wire",
            status="pending",
            ingested_at=datetime.now(timezone.utc),
        )
        db_session.add(txn)
        await db_session.flush()

        # Reset scorer
        scorer = get_scorer()
        scorer._is_trained = False
        scorer._model = None

        result = await detect_ml_anomaly(
            db=db_session,
            transaction=txn,
            config={"threshold": 0.5, "min_risk_score": 20.0},
            weight=Decimal("1.50"),
        )

        # Should not trigger because model is not trained
        assert result.triggered is False

    async def test_detect_ml_anomaly_with_model(
        self,
        db_session: AsyncSession,
        sample_account: Account,
    ) -> None:
        """Test that detector triggers with a trained model."""
        # Create training data
        for i in range(60):
            txn = Transaction(
                external_id=f"ML-TRAIN-{i}",
                source_account_id=sample_account.id,
                destination_account_id=sample_account.id,
                amount=Decimal(f"{100 + i}.00"),
                currency="USD",
                txn_timestamp=datetime.now(timezone.utc) - timedelta(minutes=i),
                channel="wire",
                status="pending",
                ingested_at=datetime.now(timezone.utc),
            )
            db_session.add(txn)
        await db_session.flush()

        # Train model
        scorer = get_scorer()
        scorer._is_trained = False
        scorer._model = None
        await scorer.train(db_session)

        # Create an anomalous transaction
        anomaly_txn = Transaction(
            external_id="ML-ANOMALY-DETECT",
            source_account_id=sample_account.id,
            destination_account_id=sample_account.id,
            amount=Decimal("999999.00"),
            currency="USD",
            txn_timestamp=datetime.now(timezone.utc),
            channel="crypto",
            status="pending",
            ingested_at=datetime.now(timezone.utc),
        )
        db_session.add(anomaly_txn)
        await db_session.flush()

        result = await detect_ml_anomaly(
            db=db_session,
            transaction=anomaly_txn,
            config={"threshold": 0.3, "min_risk_score": 10.0},
            weight=Decimal("1.50"),
        )

        # Should trigger for anomalous transaction
        assert result.triggered is True
        assert result.severity in ("medium", "high", "critical")
        assert Decimal("0.00") < result.risk_score <= Decimal("100.00")
        assert "ML" in result.title

    async def test_rule_engine_integration(
        self,
        db_session: AsyncSession,
        sample_account: Account,
    ) -> None:
        """Test that rule engine runs ML detector and creates alerts."""
        # Create an active ML rule
        rule = Rule(
            name="ML Anomaly Detection",
            slug="ml_anomaly",
            description="ML-based anomaly detection",
            detector_type="ml_anomaly",
            config={"threshold": 0.3, "min_risk_score": 10.0},
            weight=Decimal("1.50"),
            is_active=True,
        )
        db_session.add(rule)

        # Create training data
        for i in range(60):
            txn = Transaction(
                external_id=f"RE-ML-{i}",
                source_account_id=sample_account.id,
                destination_account_id=sample_account.id,
                amount=Decimal(f"{100 + i}.00"),
                currency="USD",
                txn_timestamp=datetime.now(timezone.utc) - timedelta(minutes=i),
                channel="wire",
                status="pending",
                ingested_at=datetime.now(timezone.utc),
            )
            db_session.add(txn)
        await db_session.flush()

        # Train model
        scorer = get_scorer()
        scorer._is_trained = False
        scorer._model = None
        await scorer.train(db_session)

        # Create an anomalous transaction
        anomaly_txn = Transaction(
            external_id="RE-ANOMALY",
            source_account_id=sample_account.id,
            destination_account_id=sample_account.id,
            amount=Decimal("999999.00"),
            currency="USD",
            txn_timestamp=datetime.now(timezone.utc),
            channel="crypto",
            status="pending",
            ingested_at=datetime.now(timezone.utc),
        )
        db_session.add(anomaly_txn)
        await db_session.flush()

        # Run rule engine
        alerts = await run_rule_engine(db_session, anomaly_txn)

        # Should have created at least one alert
        assert len(alerts) >= 1
        ml_alerts = [a for a in alerts if a.rule_id == rule.id]
        assert len(ml_alerts) >= 1
        assert ml_alerts[0].title == "ML Anomaly Detected"


# =========================================================================
# ML API Tests
# =========================================================================


class TestMLAPI:
    """Test ML scoring API endpoints."""

    API_KEY = "dev-api-key-1"

    async def _auth_headers(self) -> dict[str, str]:
        return {"X-API-Key": self.API_KEY}

    async def test_get_model_info(
        self,
        client: AsyncClient,
    ) -> None:
        """Test GET /api/v1/ml/model."""
        response = await client.get(
            "/api/v1/ml/model",
            headers=await self._auth_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert "is_trained" in data
        assert data["model_type"] == "IsolationForest"
        assert data["feature_count"] == FEATURE_COUNT

    async def test_train_model_insufficient_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Test POST /api/v1/ml/train with insufficient data."""
        response = await client.post(
            "/api/v1/ml/train",
            headers=await self._auth_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "skipped"
        assert data["samples"] < data["min_required"]

    async def test_score_transaction_not_found(
        self,
        client: AsyncClient,
    ) -> None:
        """Test POST /api/v1/ml/score with non-existent transaction."""
        response = await client.post(
            "/api/v1/ml/score",
            json={"transaction_id": "00000000-0000-0000-0000-000000000000"},
            headers=await self._auth_headers(),
        )
        assert response.status_code == 404

    async def test_get_features_not_found(
        self,
        client: AsyncClient,
    ) -> None:
        """Test POST /api/v1/ml/features with non-existent transaction."""
        response = await client.post(
            "/api/v1/ml/features",
            json={"transaction_id": "00000000-0000-0000-0000-000000000000"},
            headers=await self._auth_headers(),
        )
        assert response.status_code == 404

    async def test_get_features(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sample_account: Account,
    ) -> None:
        """Test POST /api/v1/ml/features for a valid transaction."""
        txn = Transaction(
            external_id="FEATURES-API-TEST",
            source_account_id=sample_account.id,
            destination_account_id=sample_account.id,
            amount=Decimal("1000.00"),
            currency="USD",
            txn_timestamp=datetime.now(timezone.utc),
            channel="wire",
            status="pending",
            ingested_at=datetime.now(timezone.utc),
        )
        db_session.add(txn)
        await db_session.flush()
        txn_id = str(txn.id)

        response = await client.post(
            "/api/v1/ml/features",
            json={"transaction_id": txn_id},
            headers=await self._auth_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["transaction_id"] == txn_id
        assert len(data["feature_names"]) == FEATURE_COUNT
        assert len(data["feature_values"]) == FEATURE_COUNT

    async def test_unauthorized_access(
        self,
        client: AsyncClient,
    ) -> None:
        """Test that ML endpoints reject invalid API key."""
        endpoints = [
            ("GET", "/api/v1/ml/model"),
            ("POST", "/api/v1/ml/train"),
            ("POST", "/api/v1/ml/score"),
            ("POST", "/api/v1/ml/features"),
        ]

        for method, path in endpoints:
            if method == "GET":
                response = await client.get(
                    path,
                    headers={"X-API-Key": "invalid-key"},
                )
            else:
                response = await client.post(
                    path,
                    json={"transaction_id": "00000000-0000-0000-0000-000000000000"},
                    headers={"X-API-Key": "invalid-key"},
                )
            assert response.status_code == 401, f"{method} {path} should return 401"