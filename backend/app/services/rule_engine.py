"""AML Monitor — Rule Engine.

Six configurable rule-based detectors that evaluate transactions and generate alerts.

Detectors:
1. **structuring** — detects smurfing patterns (multiple txns below threshold)
2. **rapid_movement** — detects rapid movement of funds through an account
3. **round_amount** — detects unusually round transaction amounts
4. **velocity** — detects high frequency of transactions in a time window
5. **geographic** — detects transactions from high-risk jurisdictions
6. **dormant** — detects activity on accounts inactive for a period
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.alert import Alert
from app.models.client import Client
from app.models.rule import Rule
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Detection result
# ---------------------------------------------------------------------------


class DetectionResult:
    """Result of running a single detector against a transaction."""

    def __init__(
        self,
        triggered: bool,
        severity: str = "low",
        risk_score: Decimal = Decimal("0.00"),
        title: str = "",
        description: str = "",
    ) -> None:
        self.triggered = triggered
        self.severity = severity
        self.risk_score = risk_score
        self.title = title
        self.description = description


# ---------------------------------------------------------------------------
# Individual detectors
# ---------------------------------------------------------------------------


async def detect_structuring(
    db: AsyncSession,
    transaction: Transaction,
    config: dict[str, Any],
    weight: Decimal,
) -> DetectionResult:
    """Detect structuring / smurfing patterns.

    Looks for multiple transactions from the same source account that are
    just below the ``threshold_amount`` within a ``time_window_minutes``
    window.  If at least ``min_transactions`` such txns exist (including the
    current one), an alert is raised.
    """
    threshold = Decimal(str(config.get("threshold_amount", 9999.99)))
    window_minutes = int(config.get("time_window_minutes", 1440))  # 24h
    min_txns = int(config.get("min_transactions", 3))

    if transaction.amount >= threshold:
        return DetectionResult(triggered=False)

    window_start = transaction.txn_timestamp - timedelta(minutes=window_minutes)

    result = await db.execute(
        select(func.count(Transaction.id)).where(
            Transaction.source_account_id == transaction.source_account_id,
            Transaction.amount < threshold,
            Transaction.txn_timestamp >= window_start,
            Transaction.txn_timestamp <= transaction.txn_timestamp,
        )
    )
    count: int = result.scalar() or 0

    if count >= min_txns:
        risk = min(weight * Decimal(str(count)) * Decimal("10"), Decimal("100"))
        return DetectionResult(
            triggered=True,
            severity="high" if count >= 5 else "medium",
            risk_score=risk,
            title="Structuring / Smurfing Detected",
            description=(
                f"Source account {transaction.source_account_id} has {count} "
                f"transactions below {threshold} {transaction.currency} within "
                f"the last {window_minutes} minutes."
            ),
        )

    return DetectionResult(triggered=False)


async def detect_rapid_movement(
    db: AsyncSession,
    transaction: Transaction,
    config: dict[str, Any],
    weight: Decimal,
) -> DetectionResult:
    """Detect rapid movement of funds (in-and-out patterns).

    Flags transactions where the destination account sends out a significant
    portion of the received amount within a short time window.
    """
    threshold_pct = Decimal(str(config.get("threshold_pct", "90.00")))
    window_minutes = int(config.get("time_window_minutes", 60))

    window_start = transaction.txn_timestamp - timedelta(minutes=window_minutes)

    # Look for outgoing txns from the destination account shortly after
    # receiving this transaction
    result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.source_account_id == transaction.destination_account_id,
            Transaction.txn_timestamp >= transaction.txn_timestamp,
            Transaction.txn_timestamp <= transaction.txn_timestamp + timedelta(minutes=window_minutes),
        )
    )
    outgoing_sum: Decimal = result.scalar() or Decimal("0")

    if outgoing_sum > 0 and (outgoing_sum / transaction.amount * Decimal("100")) >= threshold_pct:
        risk = min(weight * Decimal("50"), Decimal("100"))
        return DetectionResult(
            triggered=True,
            severity="high",
            risk_score=risk,
            title="Rapid Movement of Funds",
            description=(
                f"Within {window_minutes} minutes of receiving "
                f"{transaction.amount} {transaction.currency}, the destination "
                f"account sent out {outgoing_sum} {transaction.currency} "
                f"({threshold_pct}%+ of received amount)."
            ),
        )

    return DetectionResult(triggered=False)


async def detect_round_amount(
    db: AsyncSession,
    transaction: Transaction,
    config: dict[str, Any],
    weight: Decimal,
) -> DetectionResult:
    """Detect unusually round transaction amounts.

    Flags amounts that are round numbers (e.g., 5000, 10000, 50000) or
    amounts just below round thresholds (e.g., 9999.99).
    """
    threshold = Decimal(str(config.get("threshold_amount", 5000)))
    check_below = config.get("check_below_threshold", True)

    if transaction.amount < threshold:
        return DetectionResult(triggered=False)

    amount = transaction.amount
    is_round = amount == amount.to_integral_value()
    is_just_below = False

    if check_below:
        # Check if amount is just below a round number (e.g., 9999.99)
        rounded = amount.to_integral_value(rounding="ROUND_UP")
        is_just_below = (rounded - amount) < Decimal("1") and (rounded - amount) > Decimal("0")

    if is_round or is_just_below:
        risk = min(weight * Decimal("30"), Decimal("100"))
        return DetectionResult(
            triggered=True,
            severity="low" if is_round else "medium",
            risk_score=risk,
            title="Suspicious Round Amount",
            description=(
                f"Transaction amount {amount} {transaction.currency} is "
                f"{'a round number' if is_round else 'just below a round threshold'}. "
                f"This may indicate automated or structured activity."
            ),
        )

    return DetectionResult(triggered=False)


async def detect_velocity(
    db: AsyncSession,
    transaction: Transaction,
    config: dict[str, Any],
    weight: Decimal,
) -> DetectionResult:
    """Detect high velocity of transactions.

    Flags accounts that have an unusually high number of transactions
    within a time window.
    """
    max_txns = int(config.get("max_transactions", 10))
    window_minutes = int(config.get("time_window_minutes", 60))

    window_start = transaction.txn_timestamp - timedelta(minutes=window_minutes)

    # Count transactions from the source account in the window
    result = await db.execute(
        select(func.count(Transaction.id)).where(
            Transaction.source_account_id == transaction.source_account_id,
            Transaction.txn_timestamp >= window_start,
            Transaction.txn_timestamp <= transaction.txn_timestamp,
        )
    )
    source_count: int = result.scalar() or 0

    # Also count transactions to the destination account
    result = await db.execute(
        select(func.count(Transaction.id)).where(
            Transaction.destination_account_id == transaction.destination_account_id,
            Transaction.txn_timestamp >= window_start,
            Transaction.txn_timestamp <= transaction.txn_timestamp,
        )
    )
    dest_count: int = result.scalar() or 0

    max_count = max(source_count, dest_count)

    if max_count > max_txns:
        excess = max_count - max_txns
        risk = min(weight * Decimal(str(excess)) * Decimal("15"), Decimal("100"))
        severity: str = "critical" if excess > 20 else ("high" if excess > 10 else "medium")
        return DetectionResult(
            triggered=True,
            severity=severity,
            risk_score=risk,
            title="High Transaction Velocity",
            description=(
                f"Account activity detected: {max_count} transactions in "
                f"{window_minutes} minutes (limit: {max_txns}). "
                f"This exceeds the velocity threshold by {excess} transactions."
            ),
        )

    return DetectionResult(triggered=False)


async def detect_geographic(
    db: AsyncSession,
    transaction: Transaction,
    config: dict[str, Any],
    weight: Decimal,
) -> DetectionResult:
    """Detect transactions involving high-risk jurisdictions.

    Uses the ``extra_data`` field to check for country/region indicators.
    High-risk countries are configured in the rule config.
    """
    high_risk_countries: list[str] = config.get("high_risk_countries", [])
    high_risk_channels: list[str] = config.get("high_risk_channels", ["crypto"])

    if not high_risk_countries and not high_risk_channels:
        return DetectionResult(triggered=False)

    reasons: list[str] = []

    # Check channel
    if transaction.channel and transaction.channel.lower() in [c.lower() for c in high_risk_channels]:
        reasons.append(f"High-risk channel: {transaction.channel}")

    # Check extra_data for country hints
    if transaction.extra_data:
        for field in ("country", "region", "jurisdiction", "origin_country"):
            value = transaction.extra_data.get(field, "")
            if value and value.upper() in [c.upper() for c in high_risk_countries]:
                reasons.append(f"High-risk jurisdiction: {value} ({field})")

    if reasons:
        risk = min(weight * Decimal("40"), Decimal("100"))
        return DetectionResult(
            triggered=True,
            severity="high",
            risk_score=risk,
            title="High-Risk Jurisdiction / Channel",
            description="; ".join(reasons),
        )

    return DetectionResult(triggered=False)


async def detect_dormant(
    db: AsyncSession,
    transaction: Transaction,
    config: dict[str, Any],
    weight: Decimal,
) -> DetectionResult:
    """Detect activity on dormant accounts.

    Flags transactions involving accounts that have been inactive for
    a specified period.
    """
    dormant_days = int(config.get("dormant_days", 90))

    cutoff = transaction.txn_timestamp - timedelta(days=dormant_days)

    # Check if source account has been inactive
    result = await db.execute(
        select(func.count(Transaction.id)).where(
            Transaction.source_account_id == transaction.source_account_id,
            Transaction.txn_timestamp < transaction.txn_timestamp,
            Transaction.txn_timestamp >= cutoff,
        )
    )
    source_recent: int = result.scalar() or 0

    # Check if destination account has been inactive
    result = await db.execute(
        select(func.count(Transaction.id)).where(
            Transaction.destination_account_id == transaction.destination_account_id,
            Transaction.txn_timestamp < transaction.txn_timestamp,
            Transaction.txn_timestamp >= cutoff,
        )
    )
    dest_recent: int = result.scalar() or 0

    dormant_accounts: list[str] = []
    if source_recent == 0:
        dormant_accounts.append(f"source ({transaction.source_account_id})")
    if dest_recent == 0:
        dormant_accounts.append(f"destination ({transaction.destination_account_id})")

    if dormant_accounts:
        risk = min(weight * Decimal("60"), Decimal("100"))
        return DetectionResult(
            triggered=True,
            severity="medium",
            risk_score=risk,
            title="Dormant Account Activity",
            description=(
                f"Transaction involves dormant account(s): "
                f"{', '.join(dormant_accounts)}. "
                f"No activity detected in the last {dormant_days} days."
            ),
        )

    return DetectionResult(triggered=False)


# ---------------------------------------------------------------------------
# Sanctions screening detector
# ---------------------------------------------------------------------------


async def detect_sanctions_match(
    db: AsyncSession,
    transaction: Transaction,
    config: dict[str, Any],
    weight: Decimal,
) -> DetectionResult:
    """Screen transaction parties against the local sanctions list.

    Uses the ``extra_data`` field to look up ``source_name`` and
    ``destination_name`` (account holder names).  If names are not
    available in ``extra_data``, the detector falls back to checking
    the client name associated with the source/destination account.

    Config keys:
    - ``threshold`` (float, default 0.88): similarity threshold.
    - ``method`` (str, default ``"jaro_winkler"``): matching method.
    """
    from app.services.sanctions_service import screen_transaction_parties

    threshold = float(config.get("threshold", 0.88))
    method = config.get("method", "jaro_winkler")

    # Try to get names from extra_data first
    source_name: str | None = None
    destination_name: str | None = None

    if transaction.extra_data:
        source_name = transaction.extra_data.get("source_name")
        destination_name = transaction.extra_data.get("destination_name")

    # Fall back to client names from the Account model
    if not source_name or not destination_name:
        from app.models.account import Account
        from app.models.client import Client

        account_ids = set()
        if not source_name and transaction.source_account_id:
            account_ids.add(transaction.source_account_id)
        if not destination_name and transaction.destination_account_id:
            account_ids.add(transaction.destination_account_id)

        if account_ids:
            result = await db.execute(
                select(Account).where(Account.id.in_(account_ids))
            )
            accounts = {str(a.id): a for a in result.scalars().all()}

            if not source_name and transaction.source_account_id:
                acc = accounts.get(str(transaction.source_account_id))
                if acc:
                    # Try to get client name
                    client_result = await db.execute(
                        select(Client).where(Client.id == acc.client_id)
                    )
                    client = client_result.scalar_one_or_none()
                    if client:
                        source_name = client.name

            if not destination_name and transaction.destination_account_id:
                acc = accounts.get(str(transaction.destination_account_id))
                if acc:
                    client_result = await db.execute(
                        select(Client).where(Client.id == acc.client_id)
                    )
                    client = client_result.scalar_one_or_none()
                    if client:
                        destination_name = client.name

    if not source_name and not destination_name:
        return DetectionResult(triggered=False)

    result = await screen_transaction_parties(
        db=db,
        source_name=source_name,
        destination_name=destination_name,
        threshold=threshold,
        method=method,
    )

    if result.triggered:
        risk = min(weight * result.risk_score, Decimal("100"))
        return DetectionResult(
            triggered=True,
            severity=result.severity,
            risk_score=risk,
            title=result.title,
            description=result.description,
        )

    return DetectionResult(triggered=False)


# ---------------------------------------------------------------------------
# ML Anomaly detector
# ---------------------------------------------------------------------------


async def detect_ml_anomaly(
    db: AsyncSession,
    transaction: Transaction,
    config: dict[str, Any],
    weight: Decimal,
) -> DetectionResult:
    """Detect anomalies using the Isolation Forest ML model.

    Uses the ``MLScorer`` singleton to score the transaction.  If the
    anomaly score exceeds the configured threshold, an alert is raised
    with a SHAP-based explanation.

    Config keys:
    - ``threshold`` (float, default 0.5): anomaly score threshold (0..1).
    - ``min_risk_score`` (float, default 20.0): minimum risk score to alert.
    """
    from app.services.ml_scorer import score_transaction as ml_score

    threshold = float(config.get("threshold", 0.5))
    min_risk = float(config.get("min_risk_score", 20.0))

    try:
        result = await ml_score(db, transaction)
    except Exception:
        logger.exception("ML scoring failed for transaction %s", transaction.id)
        return DetectionResult(triggered=False)

    if not result.is_anomaly and result.risk_score < Decimal(str(min_risk)):
        return DetectionResult(triggered=False)

    # Build explanation text from SHAP values
    explanation_parts: list[str] = []
    if result.explanation:
        for feat_name, shap_val in result.explanation.items():
            direction = "increased" if shap_val > 0 else "decreased"
            explanation_parts.append(
                f"'{feat_name}' {direction} risk by {abs(shap_val):.4f}"
            )

    description = (
        f"ML anomaly score: {result.anomaly_score:.4f} "
        f"(threshold: {threshold}). "
    )
    if explanation_parts:
        description += "Top SHAP contributors: " + "; ".join(explanation_parts)
    else:
        description += "No SHAP explanation available (model may not be trained)."

    risk = min(weight * result.risk_score, Decimal("100"))
    severity: str = "critical" if result.anomaly_score > 0.8 else (
        "high" if result.anomaly_score > 0.65 else "medium"
    )

    return DetectionResult(
        triggered=True,
        severity=severity,
        risk_score=risk,
        title="ML Anomaly Detected",
        description=description,
    )


# ---------------------------------------------------------------------------
# Graph anomaly detector
# ---------------------------------------------------------------------------


async def detect_graph_anomaly(
    db: AsyncSession,
    transaction: Transaction,
    config: dict[str, Any],
    weight: Decimal,
) -> DetectionResult:
    """Detect graph-based anomalies (cycles and suspicious clusters).

    Uses the ``check_graph_anomalies`` function from the graph analysis
    service to determine if the transaction's accounts are part of any
    suspicious graph patterns.

    Config keys:
    - ``hours_lookback`` (int, default 72): lookback window.
    - ``max_cycle_length`` (int, default 6): max cycle length.
    - ``min_cycle_volume`` (float, default 50000): min cycle volume.
    - ``min_cluster_size`` (int, default 3): min cluster size.
    - ``min_cluster_volume`` (float, default 50000): min cluster volume.
    """
    from app.services.graph_analysis import check_graph_anomalies

    try:
        result = await check_graph_anomalies(db, transaction, config)
    except Exception:
        logger.exception("Graph analysis failed for transaction %s", transaction.id)
        return DetectionResult(triggered=False)

    if not result["is_suspicious"]:
        return DetectionResult(triggered=False)

    risk = min(weight * result["risk_score"], Decimal("100"))
    severity = result["severity"]
    description = "; ".join(result["reasons"])

    return DetectionResult(
        triggered=True,
        severity=severity,
        risk_score=risk,
        title="Graph Anomaly Detected",
        description=description,
    )


# ---------------------------------------------------------------------------
# Detector registry — maps detector_type → async callable
# ---------------------------------------------------------------------------

DETECTOR_REGISTRY: dict[str, callable] = {
    "structuring": detect_structuring,
    "rapid_movement": detect_rapid_movement,
    "round_amount": detect_round_amount,
    "velocity": detect_velocity,
    "geographic": detect_geographic,
    "dormant": detect_dormant,
    "sanctions_match": detect_sanctions_match,
    "ml_anomaly": detect_ml_anomaly,
    "graph_anomaly": detect_graph_anomaly,
}

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def run_rule_engine(
    db: AsyncSession,
    transaction: Transaction,
) -> list[Alert]:
    """Run all active rules against a transaction and create alerts.

    Args:
        db: Database session.
        transaction: The transaction to evaluate.

    Returns:
        A list of newly created Alert instances (already flushed to DB).
    """
    # Load all active rules
    result = await db.execute(
        select(Rule).where(Rule.is_active == True)  # noqa: E712
    )
    rules: list[Rule] = list(result.scalars().all())

    if not rules:
        logger.info("No active rules configured — skipping rule engine")
        return []

    alerts: list[Alert] = []

    for rule in rules:
        detector = DETECTOR_REGISTRY.get(rule.detector_type)
        if detector is None:
            logger.warning("Unknown detector_type: %s (rule: %s)", rule.detector_type, rule.slug)
            continue

        try:
            detection: DetectionResult = await detector(
                db=db,
                transaction=transaction,
                config=rule.config,
                weight=rule.weight,
            )
        except Exception:
            logger.exception("Detector %s failed for transaction %s", rule.slug, transaction.id)
            continue

        if detection.triggered:
            alert = Alert(
                transaction_id=transaction.id,
                rule_id=rule.id,
                severity=detection.severity,
                risk_score=detection.risk_score,
                title=detection.title,
                description=detection.description,
                status="new",
            )
            db.add(alert)
            alerts.append(alert)
            logger.info(
                "Alert created: rule=%s txn=%s severity=%s score=%s",
                rule.slug,
                transaction.id,
                detection.severity,
                detection.risk_score,
            )

    if alerts:
        await db.flush()

    return alerts