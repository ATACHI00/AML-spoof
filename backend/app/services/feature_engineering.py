"""AML Monitor — Feature Engineering for ML Scoring.

Extracts numerical features from transactions and account history for
anomaly detection models (Isolation Forest, etc.).

Features computed per transaction:
- amount_features: amount, log_amount, roundness, is_just_below_round
- temporal_features: hour_of_day, day_of_week, is_weekend, days_since_last_txn
- velocity_features: txn_count_1h, txn_count_24h, txn_sum_1h, txn_sum_24h
- account_features: account_age_days, balance_ratio, is_dormant
- client_features: client_risk_score, client_txn_count_30d
- channel_features: channel_is_high_risk (crypto, etc.)
- currency_features: currency_is_common, currency_pair_match
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.client import Client
from app.models.transaction import Transaction

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HIGH_RISK_CHANNELS: set[str] = {"crypto", "virtual_currency", "anonymous"}
COMMON_CURRENCIES: set[str] = {"USD", "EUR", "GBP", "CHF", "JPY", "CNY"}
ROUND_THRESHOLD = Decimal("5000")

# ---------------------------------------------------------------------------
# Feature vector schema
# ---------------------------------------------------------------------------

FEATURE_NAMES: list[str] = [
    # Amount features
    "amount",
    "log_amount",
    "roundness",  # 1 if amount is a round number, else 0
    "is_just_below_round",  # 1 if amount is just below a round threshold
    # Temporal features
    "hour_of_day",
    "day_of_week",
    "is_weekend",
    # Velocity features (source account)
    "src_txn_count_1h",
    "src_txn_count_24h",
    "src_txn_sum_1h",
    "src_txn_sum_24h",
    # Velocity features (destination account)
    "dst_txn_count_1h",
    "dst_txn_count_24h",
    "dst_txn_sum_1h",
    "dst_txn_sum_24h",
    # Account features
    "src_account_age_days",
    "dst_account_age_days",
    "src_balance_ratio",  # amount / balance (or 0 if balance is 0)
    "dst_balance_ratio",
    "src_is_dormant",  # 1 if no activity in 90 days
    "dst_is_dormant",
    # Client features
    "client_risk_score",
    "counterparty_risk_score",
    # Channel / currency features
    "channel_is_high_risk",
    "currency_is_common",
    "currency_pair_match",  # 1 if source and dest currency match
]

FEATURE_COUNT: int = len(FEATURE_NAMES)


# ---------------------------------------------------------------------------
# Feature extractor
# ---------------------------------------------------------------------------


async def extract_features(
    db: AsyncSession,
    transaction: Transaction,
) -> np.ndarray:
    """Extract a feature vector for a single transaction.

    Args:
        db: Database session.
        transaction: The transaction to extract features for.

    Returns:
        A 1-D numpy array of shape ``(FEATURE_COUNT,)``.
    """
    now = transaction.txn_timestamp
    features: list[float] = []

    # ------------------------------------------------------------------
    # 1. Amount features
    # ------------------------------------------------------------------
    amount = float(transaction.amount)
    features.append(amount)
    features.append(math.log1p(amount))  # log(1 + amount) for skew reduction

    # Roundness
    is_round = 1.0 if amount == round(amount) else 0.0
    features.append(is_round)

    # Just below round threshold
    if amount >= float(ROUND_THRESHOLD):
        rounded_up = math.ceil(amount)
        is_just_below = 1.0 if 0 < (rounded_up - amount) < 1.0 else 0.0
    else:
        is_just_below = 0.0
    features.append(is_just_below)

    # ------------------------------------------------------------------
    # 2. Temporal features
    # ------------------------------------------------------------------
    features.append(float(now.hour))
    features.append(float(now.weekday()))
    features.append(1.0 if now.weekday() >= 5 else 0.0)

    # ------------------------------------------------------------------
    # 3. Velocity features (source account)
    # ------------------------------------------------------------------
    src_1h_ago = now - timedelta(hours=1)
    src_24h_ago = now - timedelta(hours=24)

    src_count_1h = await _count_txns(
        db, Transaction.source_account_id, transaction.source_account_id,
        src_1h_ago, now,
    )
    src_count_24h = await _count_txns(
        db, Transaction.source_account_id, transaction.source_account_id,
        src_24h_ago, now,
    )
    src_sum_1h = await _sum_txns(
        db, Transaction.source_account_id, transaction.source_account_id,
        src_1h_ago, now,
    )
    src_sum_24h = await _sum_txns(
        db, Transaction.source_account_id, transaction.source_account_id,
        src_24h_ago, now,
    )

    features.append(float(src_count_1h))
    features.append(float(src_count_24h))
    features.append(float(src_sum_1h))
    features.append(float(src_sum_24h))

    # ------------------------------------------------------------------
    # 4. Velocity features (destination account)
    # ------------------------------------------------------------------
    dst_count_1h = await _count_txns(
        db, Transaction.destination_account_id, transaction.destination_account_id,
        src_1h_ago, now,
    )
    dst_count_24h = await _count_txns(
        db, Transaction.destination_account_id, transaction.destination_account_id,
        src_24h_ago, now,
    )
    dst_sum_1h = await _sum_txns(
        db, Transaction.destination_account_id, transaction.destination_account_id,
        src_1h_ago, now,
    )
    dst_sum_24h = await _sum_txns(
        db, Transaction.destination_account_id, transaction.destination_account_id,
        src_24h_ago, now,
    )

    features.append(float(dst_count_1h))
    features.append(float(dst_count_24h))
    features.append(float(dst_sum_1h))
    features.append(float(dst_sum_24h))

    # ------------------------------------------------------------------
    # 5. Account features
    # ------------------------------------------------------------------
    src_account = await _get_account(db, transaction.source_account_id)
    dst_account = await _get_account(db, transaction.destination_account_id)

    # Account age
    src_age = _account_age_days(src_account, now) if src_account else 0.0
    dst_age = _account_age_days(dst_account, now) if dst_account else 0.0
    features.append(src_age)
    features.append(dst_age)

    # Balance ratio (amount / balance)
    src_bal = float(src_account.balance) if src_account and src_account.balance else 0.0
    dst_bal = float(dst_account.balance) if dst_account and dst_account.balance else 0.0
    features.append(amount / src_bal if src_bal > 0 else 0.0)
    features.append(amount / dst_bal if dst_bal > 0 else 0.0)

    # Dormant flags
    src_dormant = await _is_dormant(db, transaction.source_account_id, now)
    dst_dormant = await _is_dormant(db, transaction.destination_account_id, now)
    features.append(1.0 if src_dormant else 0.0)
    features.append(1.0 if dst_dormant else 0.0)

    # ------------------------------------------------------------------
    # 6. Client features
    # ------------------------------------------------------------------
    src_client = await _get_client_for_account(db, src_account) if src_account else None
    dst_client = await _get_client_for_account(db, dst_account) if dst_account else None

    features.append(
        float(src_client.risk_score) if src_client and src_client.risk_score else 0.0
    )
    features.append(
        float(dst_client.risk_score) if dst_client and dst_client.risk_score else 0.0
    )

    # ------------------------------------------------------------------
    # 7. Channel / Currency features
    # ------------------------------------------------------------------
    channel = (transaction.channel or "").lower()
    features.append(1.0 if channel in HIGH_RISK_CHANNELS else 0.0)

    currency = transaction.currency.upper()
    features.append(1.0 if currency in COMMON_CURRENCIES else 0.0)

    # Currency pair match
    src_currency = src_account.currency.upper() if src_account else ""
    dst_currency = dst_account.currency.upper() if dst_account else ""
    features.append(1.0 if src_currency == dst_currency else 0.0)

    return np.array(features, dtype=np.float64)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _count_txns(
    db: AsyncSession,
    column: Any,
    account_id: Any,
    start: datetime,
    end: datetime,
) -> int:
    """Count transactions for an account in a time window."""
    result = await db.execute(
        select(func.count(Transaction.id)).where(
            column == account_id,
            Transaction.txn_timestamp >= start,
            Transaction.txn_timestamp <= end,
        )
    )
    return result.scalar() or 0


async def _sum_txns(
    db: AsyncSession,
    column: Any,
    account_id: Any,
    start: datetime,
    end: datetime,
) -> float:
    """Sum transaction amounts for an account in a time window."""
    result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            column == account_id,
            Transaction.txn_timestamp >= start,
            Transaction.txn_timestamp <= end,
        )
    )
    return float(result.scalar() or 0)


async def _get_account(db: AsyncSession, account_id: Any) -> Account | None:
    """Fetch an account by ID."""
    result = await db.execute(select(Account).where(Account.id == account_id))
    return result.scalar_one_or_none()


async def _get_client_for_account(db: AsyncSession, account: Account) -> Client | None:
    """Fetch the client that owns an account."""
    result = await db.execute(select(Client).where(Client.id == account.client_id))
    return result.scalar_one_or_none()


def _account_age_days(account: Account, now: datetime) -> float:
    """Calculate account age in days."""
    if account.created_at:
        # Make both datetimes offset-aware (assume UTC for naive ones)
        created = account.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        now_aware = now
        if now_aware.tzinfo is None:
            now_aware = now_aware.replace(tzinfo=timezone.utc)
        delta = now_aware - created
        return max(0.0, delta.total_seconds() / 86400.0)
    return 0.0


async def _is_dormant(
    db: AsyncSession,
    account_id: Any,
    now: datetime,
    dormant_days: int = 90,
) -> bool:
    """Check if an account has been inactive for ``dormant_days``."""
    cutoff = now - timedelta(days=dormant_days)
    result = await db.execute(
        select(func.count(Transaction.id)).where(
            (Transaction.source_account_id == account_id)
            | (Transaction.destination_account_id == account_id),
            Transaction.txn_timestamp >= cutoff,
            Transaction.txn_timestamp < now,
        )
    )
    count: int = result.scalar() or 0
    return count == 0