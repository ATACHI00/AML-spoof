"""Tests for Graph Analysis API endpoints.

Covers:
- POST /api/v1/graph/analyze — full analysis
- GET /api/v1/graph/cycles — cycle detection
- GET /api/v1/graph/clusters — cluster detection
- GET /api/v1/graph/edges — edge listing
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.client import Client
from app.models.transaction import Transaction

API_KEY = "dev-api-key-1"
HEADERS = {"X-API-Key": API_KEY}


async def _create_txn(
    db_session: AsyncSession,
    source: Account,
    dest: Account,
    amount: Decimal,
    external_id: str | None = None,
) -> Transaction:
    """Helper to create a transaction."""
    if external_id is None:
        external_id = str(uuid4())

    txn = Transaction(
        external_id=external_id,
        source_account_id=source.id,
        destination_account_id=dest.id,
        amount=amount,
        currency="USD",
        txn_timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
        channel="wire",
        status="cleared",
        ingested_at=datetime.now(timezone.utc),
    )
    db_session.add(txn)
    await db_session.flush()
    return txn


async def _setup_graph_data(db_session: AsyncSession) -> dict[str, Account]:
    """Create accounts and transactions forming a cycle + cluster."""
    client = Client(
        external_id="API-GRAPH-CLIENT",
        name="API Graph Test Client",
        client_type="legal_entity",
        risk_score=Decimal("10.00"),
    )
    db_session.add(client)
    await db_session.flush()

    accounts = {}
    for i in range(5):
        acc = Account(
            client_id=client.id,
            account_number=f"API-GRAPH-ACC-{i:03d}",
            currency="USD",
            balance=Decimal("100000.00"),
        )
        db_session.add(acc)
        await db_session.flush()
        accounts[f"acc_{i}"] = acc

    # Cycle: 0→1→2→0
    await _create_txn(db_session, accounts["acc_0"], accounts["acc_1"], Decimal("50000"), "g1")
    await _create_txn(db_session, accounts["acc_1"], accounts["acc_2"], Decimal("50000"), "g2")
    await _create_txn(db_session, accounts["acc_2"], accounts["acc_0"], Decimal("50000"), "g3")

    # Additional edges for cluster: 3↔4
    await _create_txn(db_session, accounts["acc_3"], accounts["acc_4"], Decimal("30000"), "g4")
    await _create_txn(db_session, accounts["acc_4"], accounts["acc_3"], Decimal("30000"), "g5")

    return accounts


# ---------------------------------------------------------------------------
# POST /api/v1/graph/analyze
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_graph_empty(client: AsyncClient) -> None:
    """Analyze with no transactions returns empty result."""
    response = await client.post(
        "/api/v1/graph/analyze",
        headers=HEADERS,
        json={
            "hours_lookback": 72,
            "min_cycle_volume": 10000,
            "min_cluster_volume": 10000,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["edge_count"] == 0
    assert data["account_count"] == 0
    assert data["total_volume"] == "0"
    assert data["cycles"] == []
    assert data["clusters"] == []


@pytest.mark.asyncio
async def test_analyze_graph_with_data(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Analyze with transaction data returns correct results."""
    await _setup_graph_data(db_session)

    response = await client.post(
        "/api/v1/graph/analyze",
        headers=HEADERS,
        json={
            "hours_lookback": 72,
            "min_cycle_volume": 10000,
            "min_cluster_volume": 10000,
            "min_cluster_size": 2,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["edge_count"] >= 4
    assert data["account_count"] >= 4
    assert len(data["cycles"]) >= 1
    assert len(data["clusters"]) >= 1


@pytest.mark.asyncio
async def test_analyze_graph_unauthorized(client: AsyncClient) -> None:
    """Request with invalid API key returns 401."""
    response = await client.post(
        "/api/v1/graph/analyze",
        headers={"X-API-Key": "invalid-key"},
        json={"hours_lookback": 72},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/graph/cycles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_cycles(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /cycles returns detected cycles."""
    await _setup_graph_data(db_session)

    response = await client.get(
        "/api/v1/graph/cycles",
        headers=HEADERS,
        params={"hours_lookback": 72, "min_cycle_volume": 10000},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        assert "cycle" in data[0]
        assert "total_volume" in data[0]
        assert "depth" in data[0]


@pytest.mark.asyncio
async def test_list_cycles_empty(client: AsyncClient) -> None:
    """GET /cycles with no data returns empty list."""
    response = await client.get(
        "/api/v1/graph/cycles",
        headers=HEADERS,
        params={"hours_lookback": 72},
    )
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# GET /api/v1/graph/clusters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_clusters(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /clusters returns detected clusters."""
    await _setup_graph_data(db_session)

    response = await client.get(
        "/api/v1/graph/clusters",
        headers=HEADERS,
        params={"hours_lookback": 72, "min_cluster_volume": 10000, "min_cluster_size": 2},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        assert "account_ids" in data[0]
        assert "density_score" in data[0]
        assert "reason" in data[0]


@pytest.mark.asyncio
async def test_list_clusters_empty(client: AsyncClient) -> None:
    """GET /clusters with no data returns empty list."""
    response = await client.get(
        "/api/v1/graph/clusters",
        headers=HEADERS,
        params={"hours_lookback": 72},
    )
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# GET /api/v1/graph/edges
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_edges(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /edges returns graph edges."""
    await _setup_graph_data(db_session)

    response = await client.get(
        "/api/v1/graph/edges",
        headers=HEADERS,
        params={"hours_lookback": 72},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 4
    assert "source_account_id" in data[0]
    assert "destination_account_id" in data[0]
    assert "total_amount" in data[0]
    assert "txn_count" in data[0]


@pytest.mark.asyncio
async def test_list_edges_min_amount(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /edges with min_amount filters low-value edges."""
    await _setup_graph_data(db_session)

    response = await client.get(
        "/api/v1/graph/edges",
        headers=HEADERS,
        params={"hours_lookback": 72, "min_amount": 40000},
    )
    assert response.status_code == 200
    data = response.json()
    # Only edges >= 40000 should remain
    for edge in data:
        assert float(edge["total_amount"]) >= 40000


@pytest.mark.asyncio
async def test_list_edges_empty(client: AsyncClient) -> None:
    """GET /edges with no data returns empty list."""
    response = await client.get(
        "/api/v1/graph/edges",
        headers=HEADERS,
        params={"hours_lookback": 72},
    )
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# Rule engine integration test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graph_anomaly_detector_in_rule_engine(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Graph anomaly detector is registered and can be triggered via rule engine."""
    from app.models.rule import Rule
    from app.services.rule_engine import run_rule_engine, DETECTOR_REGISTRY

    # Verify detector is registered
    assert "graph_anomaly" in DETECTOR_REGISTRY

    # Create a graph_anomaly rule
    rule = Rule(
        name="Graph Anomaly Test",
        slug="graph_anomaly_test",
        description="Test graph anomaly detector",
        detector_type="graph_anomaly",
        config={
            "hours_lookback": 720,
            "min_cycle_volume": 10000,
            "min_cluster_volume": 999999999,
        },
        weight=Decimal("1.00"),
        is_active=True,
    )
    db_session.add(rule)
    await db_session.flush()

    # Create a cycle
    accounts = await _setup_graph_data(db_session)

    # Get the last transaction (part of the cycle)
    from sqlalchemy import select as sa_select
    from app.models.transaction import Transaction

    result = await db_session.execute(
        sa_select(Transaction).order_by(Transaction.ingested_at.desc()).limit(1)
    )
    txn = result.scalar_one()

    # Run rule engine directly
    alerts = await run_rule_engine(db_session, txn)

    # Check that an alert was created
    assert len(alerts) >= 1
    assert alerts[0].rule_id == rule.id
    assert alerts[0].severity in ("medium", "high", "critical")
    assert "cycle" in alerts[0].description.lower()