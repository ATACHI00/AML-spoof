"""AML Monitor — Model tests.

Tests for creating and querying all data models.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Client, Account, Transaction, Rule, Alert, Case, AuditLog, SanctionsList


@pytest.mark.asyncio
async def test_create_client(db_session: AsyncSession):
    """Test creating a client."""
    client = Client(
        external_id="CLIENT-TEST-001",
        name="Test Client",
        client_type="individual",
        risk_score=Decimal("25.00"),
    )
    db_session.add(client)
    await db_session.flush()

    result = await db_session.execute(
        select(Client).where(Client.external_id == "CLIENT-TEST-001")
    )
    saved = result.scalar_one()
    assert saved.name == "Test Client"
    assert saved.client_type == "individual"
    assert saved.risk_score == Decimal("25.00")
    assert saved.id is not None


@pytest.mark.asyncio
async def test_create_account(db_session: AsyncSession, sample_client: Client):
    """Test creating an account linked to a client."""
    account = Account(
        client_id=sample_client.id,
        account_number="TEST-ACCT-001",
        currency="USD",
        balance=Decimal("5000.00"),
    )
    db_session.add(account)
    await db_session.flush()

    result = await db_session.execute(
        select(Account).where(Account.account_number == "TEST-ACCT-001")
    )
    saved = result.scalar_one()
    assert saved.client_id == sample_client.id
    assert saved.currency == "USD"
    assert saved.is_active is True


@pytest.mark.asyncio
async def test_create_transaction(
    db_session: AsyncSession,
    sample_account: Account,
):
    """Test creating a transaction with idempotency key."""
    from datetime import datetime, timezone

    txn = Transaction(
        external_id="TXN-TEST-001",
        source_account_id=sample_account.id,
        destination_account_id=sample_account.id,
        amount=Decimal("1500.00"),
        currency="GBP",
        txn_timestamp=datetime.now(timezone.utc),
        channel="wire",
        status="cleared",
        ingested_at=datetime.now(timezone.utc),
    )
    db_session.add(txn)
    await db_session.flush()

    result = await db_session.execute(
        select(Transaction).where(Transaction.external_id == "TXN-TEST-001")
    )
    saved = result.scalar_one()
    assert saved.amount == Decimal("1500.00")
    assert saved.currency == "GBP"
    assert saved.status == "cleared"


@pytest.mark.asyncio
async def test_create_rule(db_session: AsyncSession):
    """Test creating a configurable rule."""
    rule = Rule(
        name="Velocity Spike Detection",
        slug="velocity",
        description="Detects unusual spike in transaction volume",
        detector_type="velocity",
        config={
            "multiplier": 3.0,
            "baseline_days": 30,
            "min_transactions": 5,
        },
        weight=Decimal("1.50"),
        is_active=True,
    )
    db_session.add(rule)
    await db_session.flush()

    result = await db_session.execute(
        select(Rule).where(Rule.slug == "velocity")
    )
    saved = result.scalar_one()
    assert saved.detector_type == "velocity"
    assert saved.config["multiplier"] == 3.0
    assert saved.weight == Decimal("1.50")


@pytest.mark.asyncio
async def test_create_alert(db_session: AsyncSession, sample_rule: Rule):
    """Test creating an alert linked to a rule."""
    alert = Alert(
        rule_id=sample_rule.id,
        severity="high",
        risk_score=Decimal("75.00"),
        title="Potential structuring detected",
        description="3 transactions below 10,000 within 24 hours",
        status="new",
    )
    db_session.add(alert)
    await db_session.flush()

    result = await db_session.execute(
        select(Alert).where(Alert.title == "Potential structuring detected")
    )
    saved = result.scalar_one()
    assert saved.severity == "high"
    assert saved.risk_score == Decimal("75.00")
    assert saved.status == "new"


@pytest.mark.asyncio
async def test_create_case(db_session: AsyncSession):
    """Test creating a case."""
    case = Case(
        title="Suspicious transaction pattern",
        description="Multiple alerts related to account GB29NWBK...",
        status="open",
        assigned_to="compliance-officer-1",
    )
    db_session.add(case)
    await db_session.flush()

    result = await db_session.execute(
        select(Case).where(Case.title == "Suspicious transaction pattern")
    )
    saved = result.scalar_one()
    assert saved.status == "open"
    assert saved.assigned_to == "compliance-officer-1"


@pytest.mark.asyncio
async def test_create_audit_log(db_session: AsyncSession):
    """Test creating an audit log entry."""
    from app.utils.hashing import compute_audit_hash

    log = AuditLog(
        entity_type="alert",
        entity_id="00000000-0000-0000-0000-000000000001",
        action="created",
        actor_id="system",
        changes={"status": {"from": None, "to": "new"}},
        previous_hash=None,
        current_hash=compute_audit_hash(
            previous_hash=None,
            entity_type="alert",
            entity_id="00000000-0000-0000-0000-000000000001",
            action="created",
            actor_id="system",
            changes={"status": {"from": None, "to": "new"}},
            created_at="2026-07-22T00:00:00+00:00",
        ),
    )
    db_session.add(log)
    await db_session.flush()

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.entity_type == "alert")
    )
    saved = result.scalar_one()
    assert saved.action == "created"
    assert saved.current_hash is not None


@pytest.mark.asyncio
async def test_create_sanctions_entry(db_session: AsyncSession):
    """Test creating a sanctions list entry."""
    from datetime import date

    entry = SanctionsList(
        list_source="ofac",
        full_name="IVANOV, Ivan Ivanovich",
        name_variations={"aliases": ["Ivanov I.I.", "Ivan Ivanov"]},
        entity_type="individual",
        country="RU",
        program="UKRAINE-EO13662",
        is_active=True,
        last_updated=date(2024, 1, 1),
    )
    db_session.add(entry)
    await db_session.flush()

    result = await db_session.execute(
        select(SanctionsList).where(SanctionsList.full_name == "IVANOV, Ivan Ivanovich")
    )
    saved = result.scalar_one()
    assert saved.list_source == "ofac"
    assert saved.entity_type == "individual"