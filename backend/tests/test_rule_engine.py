"""AML Monitor — Rule engine tests.

Tests for all 6 detectors and the main rule engine orchestrator.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.alert import Alert
from app.models.client import Client
from app.models.rule import Rule
from app.models.transaction import Transaction
from app.services.rule_engine import (
    DETECTOR_REGISTRY,
    DetectionResult,
    detect_dormant,
    detect_geographic,
    detect_rapid_movement,
    detect_round_amount,
    detect_structuring,
    detect_velocity,
    run_rule_engine,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def sample_client_2(db_session: AsyncSession) -> Client:
    """Second client for multi-account tests."""
    client = Client(
        external_id="CLIENT-002",
        name="Second Client Ltd",
        client_type="legal_entity",
        risk_score=Decimal("10.00"),
    )
    db_session.add(client)
    await db_session.flush()
    return client


@pytest_asyncio.fixture
async def account_2(
    db_session: AsyncSession,
    sample_client_2: Client,
) -> Account:
    """Second account for testing."""
    account = Account(
        client_id=sample_client_2.id,
        account_number="GB30NWBK60161331926820",
        currency="GBP",
        balance=Decimal("50000.00"),
    )
    db_session.add(account)
    await db_session.flush()
    return account


@pytest_asyncio.fixture
async def active_rules(db_session: AsyncSession) -> list[Rule]:
    """Create all 6 default rules for testing."""
    rules_data = [
        Rule(
            name="Structuring Detection",
            slug="structuring",
            description="Detects smurfing patterns",
            detector_type="structuring",
            config={"threshold_amount": 9999.99, "time_window_minutes": 1440, "min_transactions": 3},
            weight=Decimal("1.00"),
            is_active=True,
        ),
        Rule(
            name="Rapid Movement Detection",
            slug="rapid_movement",
            description="Detects rapid movement of funds",
            detector_type="rapid_movement",
            config={"threshold_pct": 90.00, "time_window_minutes": 60},
            weight=Decimal("1.00"),
            is_active=True,
        ),
        Rule(
            name="Round Amount Detection",
            slug="round_amount",
            description="Flags round amounts",
            detector_type="round_amount",
            config={"threshold_amount": 5000, "check_below_threshold": True},
            weight=Decimal("0.50"),
            is_active=True,
        ),
        Rule(
            name="High Velocity Detection",
            slug="velocity",
            description="Flags high transaction frequency",
            detector_type="velocity",
            config={"max_transactions": 10, "time_window_minutes": 60},
            weight=Decimal("1.00"),
            is_active=True,
        ),
        Rule(
            name="Geographic Risk Detection",
            slug="geographic",
            description="Flags high-risk jurisdictions",
            detector_type="geographic",
            config={
                "high_risk_countries": ["IR", "KP", "SY"],
                "high_risk_channels": ["crypto"],
            },
            weight=Decimal("1.50"),
            is_active=True,
        ),
        Rule(
            name="Dormant Account Detection",
            slug="dormant",
            description="Flags dormant account activity",
            detector_type="dormant",
            config={"dormant_days": 90},
            weight=Decimal("1.00"),
            is_active=True,
        ),
    ]
    for rule in rules_data:
        db_session.add(rule)
    await db_session.flush()
    return rules_data


@pytest_asyncio.fixture
async def base_transaction(
    db_session: AsyncSession,
    sample_account: Account,
    account_2: Account,
) -> Transaction:
    """A base transaction for testing (amount=500, normal)."""
    txn = Transaction(
        external_id="TXN-BASE-001",
        source_account_id=sample_account.id,
        destination_account_id=account_2.id,
        amount=Decimal("500.00"),
        currency="GBP",
        txn_timestamp=datetime.now(timezone.utc),
        channel="wire",
        status="cleared",
        ingested_at=datetime.now(timezone.utc),
    )
    db_session.add(txn)
    await db_session.flush()
    return txn


# ---------------------------------------------------------------------------
# Detector: structuring
# ---------------------------------------------------------------------------


async def _create_txns(
    db_session: AsyncSession,
    source_id,
    dest_id,
    amounts: list[Decimal],
    base_time: datetime | None = None,
) -> list[Transaction]:
    """Helper to create multiple transactions."""
    if base_time is None:
        base_time = datetime.now(timezone.utc)
    txns = []
    for i, amount in enumerate(amounts):
        txn = Transaction(
            external_id=f"TXN-STRUCT-{i}",
            source_account_id=source_id,
            destination_account_id=dest_id,
            amount=amount,
            currency="GBP",
            txn_timestamp=base_time + timedelta(minutes=i * 10),
            channel="wire",
            status="cleared",
            ingested_at=datetime.now(timezone.utc),
        )
        db_session.add(txn)
        txns.append(txn)
    await db_session.flush()
    return txns


@pytest.mark.asyncio
async def test_structuring_triggers(
    db_session: AsyncSession,
    sample_account: Account,
    account_2: Account,
) -> None:
    """Structuring should trigger when 3+ txns below threshold exist."""
    txns = await _create_txns(
        db_session,
        sample_account.id,
        account_2.id,
        [Decimal("9000.00"), Decimal("9500.00"), Decimal("9800.00")],
    )
    config = {"threshold_amount": 9999.99, "time_window_minutes": 1440, "min_transactions": 3}
    result = await detect_structuring(db_session, txns[-1], config, Decimal("1.00"))
    assert result.triggered is True
    assert result.severity in ("medium", "high")
    assert result.risk_score > 0


@pytest.mark.asyncio
async def test_structuring_not_triggered(
    db_session: AsyncSession,
    sample_account: Account,
    account_2: Account,
) -> None:
    """Structuring should NOT trigger with only 1 txn below threshold."""
    txns = await _create_txns(
        db_session,
        sample_account.id,
        account_2.id,
        [Decimal("500.00")],
    )
    config = {"threshold_amount": 9999.99, "time_window_minutes": 1440, "min_transactions": 3}
    result = await detect_structuring(db_session, txns[-1], config, Decimal("1.00"))
    assert result.triggered is False


@pytest.mark.asyncio
async def test_structuring_above_threshold(
    db_session: AsyncSession,
    sample_account: Account,
    account_2: Account,
) -> None:
    """Structuring should NOT trigger for txns above threshold."""
    txns = await _create_txns(
        db_session,
        sample_account.id,
        account_2.id,
        [Decimal("15000.00")],
    )
    config = {"threshold_amount": 9999.99, "time_window_minutes": 1440, "min_transactions": 3}
    result = await detect_structuring(db_session, txns[-1], config, Decimal("1.00"))
    assert result.triggered is False


# ---------------------------------------------------------------------------
# Detector: rapid_movement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rapid_movement_triggers(
    db_session: AsyncSession,
    sample_account: Account,
    account_2: Account,
) -> None:
    """Rapid movement should trigger when destination sends out >=90% within 60min."""
    # Create incoming txn to account_2
    incoming = Transaction(
        external_id="TXN-RAPID-IN",
        source_account_id=sample_account.id,
        destination_account_id=account_2.id,
        amount=Decimal("10000.00"),
        currency="GBP",
        txn_timestamp=datetime.now(timezone.utc),
        channel="wire",
        status="cleared",
        ingested_at=datetime.now(timezone.utc),
    )
    db_session.add(incoming)
    await db_session.flush()

    # Create outgoing txn from account_2 shortly after
    outgoing = Transaction(
        external_id="TXN-RAPID-OUT",
        source_account_id=account_2.id,
        destination_account_id=sample_account.id,
        amount=Decimal("9500.00"),  # 95% of incoming
        currency="GBP",
        txn_timestamp=incoming.txn_timestamp + timedelta(minutes=30),
        channel="wire",
        status="cleared",
        ingested_at=datetime.now(timezone.utc),
    )
    db_session.add(outgoing)
    await db_session.flush()

    config = {"threshold_pct": 90.00, "time_window_minutes": 60}
    result = await detect_rapid_movement(db_session, incoming, config, Decimal("1.00"))
    assert result.triggered is True
    assert result.severity == "high"


@pytest.mark.asyncio
async def test_rapid_movement_not_triggered(
    db_session: AsyncSession,
    sample_account: Account,
    account_2: Account,
) -> None:
    """Rapid movement should NOT trigger when outgoing is below threshold."""
    incoming = Transaction(
        external_id="TXN-RAPID-NO",
        source_account_id=sample_account.id,
        destination_account_id=account_2.id,
        amount=Decimal("10000.00"),
        currency="GBP",
        txn_timestamp=datetime.now(timezone.utc),
        channel="wire",
        status="cleared",
        ingested_at=datetime.now(timezone.utc),
    )
    db_session.add(incoming)
    await db_session.flush()

    config = {"threshold_pct": 90.00, "time_window_minutes": 60}
    result = await detect_rapid_movement(db_session, incoming, config, Decimal("1.00"))
    assert result.triggered is False


# ---------------------------------------------------------------------------
# Detector: round_amount
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_round_amount_triggers(
    db_session: AsyncSession,
    base_transaction: Transaction,
) -> None:
    """Round amount should trigger for round numbers >= threshold."""
    base_transaction.amount = Decimal("10000.00")
    config = {"threshold_amount": 5000, "check_below_threshold": True}
    result = await detect_round_amount(db_session, base_transaction, config, Decimal("0.50"))
    assert result.triggered is True
    assert result.severity == "low"


@pytest.mark.asyncio
async def test_round_amount_just_below(
    db_session: AsyncSession,
    base_transaction: Transaction,
) -> None:
    """Round amount should trigger for amounts just below round numbers."""
    base_transaction.amount = Decimal("9999.99")
    config = {"threshold_amount": 5000, "check_below_threshold": True}
    result = await detect_round_amount(db_session, base_transaction, config, Decimal("0.50"))
    assert result.triggered is True
    assert result.severity == "medium"


@pytest.mark.asyncio
async def test_round_amount_not_triggered(
    db_session: AsyncSession,
    base_transaction: Transaction,
) -> None:
    """Round amount should NOT trigger for non-round amounts below threshold."""
    base_transaction.amount = Decimal("1234.56")
    config = {"threshold_amount": 5000, "check_below_threshold": True}
    result = await detect_round_amount(db_session, base_transaction, config, Decimal("0.50"))
    assert result.triggered is False


# ---------------------------------------------------------------------------
# Detector: velocity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_velocity_triggers(
    db_session: AsyncSession,
    sample_account: Account,
    account_2: Account,
) -> None:
    """Velocity should trigger when account exceeds max transactions."""
    now = datetime.now(timezone.utc)
    # Create 12 txns within a short window (1 min apart)
    txns = []
    for i in range(12):
        txn = Transaction(
            external_id=f"TXN-VEL-{i}",
            source_account_id=sample_account.id,
            destination_account_id=account_2.id,
            amount=Decimal("100.00"),
            currency="GBP",
            txn_timestamp=now + timedelta(minutes=i),
            channel="wire",
            status="cleared",
            ingested_at=now,
        )
        db_session.add(txn)
        txns.append(txn)
    await db_session.flush()

    # Evaluate the last transaction
    last_txn = txns[-1]
    config = {"max_transactions": 10, "time_window_minutes": 60}
    result = await detect_velocity(db_session, last_txn, config, Decimal("1.00"))
    assert result.triggered is True
    assert result.severity in ("medium", "high", "critical")


@pytest.mark.asyncio
async def test_velocity_not_triggered(
    db_session: AsyncSession,
    sample_account: Account,
    account_2: Account,
    base_transaction: Transaction,
) -> None:
    """Velocity should NOT trigger when under the limit."""
    config = {"max_transactions": 10, "time_window_minutes": 60}
    result = await detect_velocity(db_session, base_transaction, config, Decimal("1.00"))
    assert result.triggered is False


# ---------------------------------------------------------------------------
# Detector: geographic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_geographic_high_risk_channel(
    db_session: AsyncSession,
    base_transaction: Transaction,
) -> None:
    """Geographic should trigger for high-risk channels."""
    base_transaction.channel = "crypto"
    config = {
        "high_risk_countries": ["IR", "KP"],
        "high_risk_channels": ["crypto"],
    }
    result = await detect_geographic(db_session, base_transaction, config, Decimal("1.50"))
    assert result.triggered is True
    assert "crypto" in result.description


@pytest.mark.asyncio
async def test_geographic_high_risk_country(
    db_session: AsyncSession,
    base_transaction: Transaction,
) -> None:
    """Geographic should trigger for high-risk countries in extra_data."""
    base_transaction.extra_data = {"country": "IR"}
    config = {
        "high_risk_countries": ["IR", "KP"],
        "high_risk_channels": ["crypto"],
    }
    result = await detect_geographic(db_session, base_transaction, config, Decimal("1.50"))
    assert result.triggered is True
    assert "IR" in result.description


@pytest.mark.asyncio
async def test_geographic_not_triggered(
    db_session: AsyncSession,
    base_transaction: Transaction,
) -> None:
    """Geographic should NOT trigger for normal channels/countries."""
    base_transaction.channel = "wire"
    config = {
        "high_risk_countries": ["IR", "KP"],
        "high_risk_channels": ["crypto"],
    }
    result = await detect_geographic(db_session, base_transaction, config, Decimal("1.50"))
    assert result.triggered is False


# ---------------------------------------------------------------------------
# Detector: dormant
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def dormant_account(
    db_session: AsyncSession,
    sample_client_2: Client,
) -> Account:
    """An account with no transaction history (dormant)."""
    account = Account(
        client_id=sample_client_2.id,
        account_number="GB40NWBK60161331926830",
        currency="GBP",
        balance=Decimal("0.00"),
    )
    db_session.add(account)
    await db_session.flush()
    return account


@pytest.mark.asyncio
async def test_dormant_triggers(
    db_session: AsyncSession,
    sample_account: Account,
    dormant_account: Account,
) -> None:
    """Dormant should trigger when destination account has no prior activity."""
    new_txn = Transaction(
        external_id="TXN-DORMANT-TEST",
        source_account_id=sample_account.id,
        destination_account_id=dormant_account.id,
        amount=Decimal("1000.00"),
        currency="GBP",
        txn_timestamp=datetime.now(timezone.utc),
        channel="wire",
        status="cleared",
        ingested_at=datetime.now(timezone.utc),
    )
    db_session.add(new_txn)
    await db_session.flush()

    config = {"dormant_days": 90}
    result = await detect_dormant(db_session, new_txn, config, Decimal("1.00"))
    # dormant_account has no prior transactions — should be flagged
    assert result.triggered is True
    assert "destination" in result.description


@pytest.mark.asyncio
async def test_dormant_destination(
    db_session: AsyncSession,
    sample_account: Account,
    account_2: Account,
) -> None:
    """Dormant should trigger when destination account has no activity."""
    # Create a txn to a fresh account (no prior activity)
    new_txn = Transaction(
        external_id="TXN-DORMANT-FRESH",
        source_account_id=sample_account.id,
        destination_account_id=account_2.id,
        amount=Decimal("1000.00"),
        currency="GBP",
        txn_timestamp=datetime.now(timezone.utc),
        channel="wire",
        status="cleared",
        ingested_at=datetime.now(timezone.utc),
    )
    db_session.add(new_txn)
    await db_session.flush()

    config = {"dormant_days": 90}
    result = await detect_dormant(db_session, new_txn, config, Decimal("1.00"))
    # account_2 has no prior transactions, so it should be flagged as dormant
    assert result.triggered is True
    assert "destination" in result.description


# ---------------------------------------------------------------------------
# Detector registry
# ---------------------------------------------------------------------------


def test_detector_registry_has_all_types() -> None:
    """All 6 detector types should be registered."""
    expected_types = {
        "structuring",
        "rapid_movement",
        "round_amount",
        "velocity",
        "geographic",
        "dormant",
    }
    assert expected_types.issubset(DETECTOR_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Integration: run_rule_engine
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_rule_engine_no_rules(
    db_session: AsyncSession,
    base_transaction: Transaction,
) -> None:
    """Rule engine should return empty list when no active rules exist."""
    alerts = await run_rule_engine(db_session, base_transaction)
    assert alerts == []


@pytest.mark.asyncio
async def test_run_rule_engine_with_rules(
    db_session: AsyncSession,
    active_rules: list[Rule],
    sample_account: Account,
    account_2: Account,
) -> None:
    """Rule engine should create alerts for triggered rules."""
    # Create a transaction that should trigger multiple rules:
    # - round_amount (10000 is round)
    # - structuring (if we create prior txns)
    # - dormant (account_2 has no prior activity)
    txn = Transaction(
        external_id="TXN-ENGINE-001",
        source_account_id=sample_account.id,
        destination_account_id=account_2.id,
        amount=Decimal("10000.00"),
        currency="GBP",
        txn_timestamp=datetime.now(timezone.utc),
        channel="wire",
        status="cleared",
        ingested_at=datetime.now(timezone.utc),
    )
    db_session.add(txn)
    await db_session.flush()

    alerts = await run_rule_engine(db_session, txn)

    # Should have at least round_amount + dormant alerts
    assert len(alerts) >= 2

    # Verify alert structure
    for alert in alerts:
        assert alert.transaction_id == txn.id
        assert alert.status == "new"
        assert alert.severity in ("low", "medium", "high", "critical")
        assert alert.risk_score > 0
        assert alert.title
        assert alert.description


@pytest.mark.asyncio
async def test_run_rule_engine_inactive_rules(
    db_session: AsyncSession,
    active_rules: list[Rule],
    base_transaction: Transaction,
) -> None:
    """Rule engine should skip inactive rules."""
    # Deactivate all rules
    for rule in active_rules:
        rule.is_active = False
    await db_session.flush()

    alerts = await run_rule_engine(db_session, base_transaction)
    assert alerts == []


@pytest.mark.asyncio
async def test_alert_persistence(
    db_session: AsyncSession,
    active_rules: list[Rule],
    sample_account: Account,
    account_2: Account,
) -> None:
    """Alerts created by rule engine should be persisted in the database."""
    txn = Transaction(
        external_id="TXN-PERSIST-001",
        source_account_id=sample_account.id,
        destination_account_id=account_2.id,
        amount=Decimal("10000.00"),
        currency="GBP",
        txn_timestamp=datetime.now(timezone.utc),
        channel="wire",
        status="cleared",
        ingested_at=datetime.now(timezone.utc),
    )
    db_session.add(txn)
    await db_session.flush()

    alerts = await run_rule_engine(db_session, txn)
    await db_session.commit()

    # Verify alerts are in the database
    from sqlalchemy import select

    result = await db_session.execute(
        select(Alert).where(Alert.transaction_id == txn.id)
    )
    persisted = list(result.scalars().all())
    assert len(persisted) == len(alerts)
    for alert in persisted:
        assert alert.id is not None
        assert alert.rule_id is not None