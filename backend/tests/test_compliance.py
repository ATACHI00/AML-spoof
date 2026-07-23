"""Tests for Compliance & Reporting API endpoints.

Covers:
- GET /api/v1/compliance/stats — dashboard statistics
- GET /api/v1/compliance/export/alerts.csv — CSV export
- GET /api/v1/compliance/export/alert/{id}/report — SAR report
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.alert import Alert
from app.models.client import Client
from app.models.rule import Rule
from app.models.transaction import Transaction

API_KEY = "dev-api-key-1"
HEADERS = {"X-API-Key": API_KEY}


async def _setup_test_data(db_session: AsyncSession) -> Alert:
    """Create test data: client, account, transaction, rule, alert."""
    client = Client(
        external_id="COMPLIANCE-TEST",
        name="Compliance Test Client",
        client_type="legal_entity",
        risk_score=Decimal("10.00"),
    )
    db_session.add(client)
    await db_session.flush()

    account = Account(
        client_id=client.id,
        account_number="COMP-ACC-001",
        currency="USD",
        balance=Decimal("50000.00"),
    )
    db_session.add(account)
    await db_session.flush()

    rule = Rule(
        name="Test Rule",
        slug="test_rule_compliance",
        description="Test rule for compliance",
        detector_type="structuring",
        config={"threshold_amount": 9999.99},
        weight=Decimal("1.00"),
        is_active=True,
    )
    db_session.add(rule)
    await db_session.flush()

    txn = Transaction(
        external_id="COMP-TXN-001",
        source_account_id=account.id,
        destination_account_id=account.id,
        amount=Decimal("5000.00"),
        currency="USD",
        txn_timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
        channel="wire",
        status="cleared",
        ingested_at=datetime.now(timezone.utc),
    )
    db_session.add(txn)
    await db_session.flush()

    alert = Alert(
        transaction_id=txn.id,
        rule_id=rule.id,
        severity="high",
        risk_score=Decimal("75.00"),
        title="Test Alert for Compliance",
        description="This is a test alert for compliance reporting",
        status="new",
    )
    db_session.add(alert)
    await db_session.flush()

    return alert


# ---------------------------------------------------------------------------
# GET /api/v1/compliance/stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compliance_stats_empty(client: AsyncClient) -> None:
    """Stats with no data returns zeros."""
    response = await client.get("/api/v1/compliance/stats", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["total_alerts"] == 0
    assert data["total_transactions"] == 0
    assert data["total_cases"] == 0
    assert data["total_audit_entries"] == 0


@pytest.mark.asyncio
async def test_compliance_stats_with_data(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Stats with data returns correct counts."""
    await _setup_test_data(db_session)

    response = await client.get("/api/v1/compliance/stats", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["total_alerts"] >= 1
    assert data["total_transactions"] >= 1
    assert "alerts_by_severity" in data
    assert "alerts_by_status" in data


# ---------------------------------------------------------------------------
# GET /api/v1/compliance/export/alerts.csv
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_alerts_csv_empty(client: AsyncClient) -> None:
    """CSV export with no data returns header only."""
    response = await client.get(
        "/api/v1/compliance/export/alerts.csv",
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    content = response.text
    assert "Alert ID" in content
    assert "Severity" in content


@pytest.mark.asyncio
async def test_export_alerts_csv_with_data(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """CSV export with data includes alert rows."""
    alert = await _setup_test_data(db_session)

    response = await client.get(
        "/api/v1/compliance/export/alerts.csv",
        headers=HEADERS,
    )
    assert response.status_code == 200
    content = response.text
    assert str(alert.id) in content
    assert "Test Alert for Compliance" in content
    assert "high" in content


@pytest.mark.asyncio
async def test_export_alerts_csv_filtered(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """CSV export with status filter works."""
    await _setup_test_data(db_session)

    # Filter by existing status
    response = await client.get(
        "/api/v1/compliance/export/alerts.csv",
        headers=HEADERS,
        params={"status": "new"},
    )
    assert response.status_code == 200
    content = response.text
    assert "Test Alert for Compliance" in content

    # Filter by non-existing status
    response = await client.get(
        "/api/v1/compliance/export/alerts.csv",
        headers=HEADERS,
        params={"status": "closed"},
    )
    assert response.status_code == 200
    content = response.text
    assert "Test Alert for Compliance" not in content


# ---------------------------------------------------------------------------
# GET /api/v1/compliance/export/alert/{id}/report
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_alert_report(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """SAR report for an alert returns formatted text."""
    alert = await _setup_test_data(db_session)

    response = await client.get(
        f"/api/v1/compliance/export/alert/{alert.id}/report",
        headers=HEADERS,
    )
    assert response.status_code == 200
    content = response.text
    assert "SUSPICIOUS ACTIVITY REPORT" in content
    assert alert.title in content
    assert alert.severity in content


@pytest.mark.asyncio
async def test_export_alert_report_not_found(client: AsyncClient) -> None:
    """SAR report for non-existent alert returns error."""
    response = await client.get(
        "/api/v1/compliance/export/alert/00000000-0000-0000-0000-000000000000/report",
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert "not found" in response.text.lower()


# ---------------------------------------------------------------------------
# Unauthorized access
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compliance_api_unauthorized(client: AsyncClient) -> None:
    """Request without valid API key returns 401."""
    response = await client.get(
        "/api/v1/compliance/stats",
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401