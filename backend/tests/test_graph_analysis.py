"""Tests for Graph Analysis service.

Covers:
- Graph construction from transactions
- Cycle detection (DFS-based)
- Suspicious cluster detection (BFS-based)
- Full analysis orchestrator
- Graph anomaly detector for rule engine
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.client import Client
from app.models.transaction import Transaction
from app.services.graph_analysis import (
    analyze_transaction_graph,
    build_transaction_graph,
    check_graph_anomalies,
    detect_clusters,
    detect_cycles,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def graph_accounts(db_session: AsyncSession) -> dict[str, Account]:
    """Create a set of accounts for graph testing."""
    client = Client(
        external_id="GRAPH-CLIENT",
        name="Graph Test Client",
        client_type="legal_entity",
        risk_score=Decimal("10.00"),
    )
    db_session.add(client)
    await db_session.flush()

    accounts = {}
    for i in range(6):
        acc = Account(
            client_id=client.id,
            account_number=f"GRAPH-ACC-{i:03d}",
            currency="USD",
            balance=Decimal("100000.00"),
        )
        db_session.add(acc)
        await db_session.flush()
        accounts[f"acc_{i}"] = acc

    return accounts


async def _create_txn(
    db_session: AsyncSession,
    source: Account,
    dest: Account,
    amount: Decimal,
    txn_timestamp: datetime | None = None,
    external_id: str | None = None,
) -> Transaction:
    """Helper to create a transaction."""
    if txn_timestamp is None:
        txn_timestamp = datetime.now(timezone.utc) - timedelta(hours=1)
    if external_id is None:
        external_id = str(uuid4())

    txn = Transaction(
        external_id=external_id,
        source_account_id=source.id,
        destination_account_id=dest.id,
        amount=amount,
        currency="USD",
        txn_timestamp=txn_timestamp,
        channel="wire",
        status="cleared",
        ingested_at=datetime.now(timezone.utc),
    )
    db_session.add(txn)
    await db_session.flush()
    return txn


# ---------------------------------------------------------------------------
# Graph construction tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_graph_empty(db_session: AsyncSession) -> None:
    """Empty graph when no transactions exist."""
    edges = await build_transaction_graph(db_session, hours_lookback=72)
    assert len(edges) == 0


@pytest.mark.asyncio
async def test_build_graph_single_edge(
    db_session: AsyncSession, graph_accounts: dict[str, Account]
) -> None:
    """Single transaction creates one edge."""
    acc = graph_accounts
    await _create_txn(db_session, acc["acc_0"], acc["acc_1"], Decimal("1000"))

    edges = await build_transaction_graph(db_session, hours_lookback=72)
    assert len(edges) == 1

    edge = edges[(str(acc["acc_0"].id), str(acc["acc_1"].id))]
    assert edge.total_amount == Decimal("1000")
    assert edge.txn_count == 1
    assert edge.currency == "USD"


@pytest.mark.asyncio
async def test_build_graph_aggregation(
    db_session: AsyncSession, graph_accounts: dict[str, Account]
) -> None:
    """Multiple transactions between same accounts are aggregated."""
    acc = graph_accounts
    await _create_txn(db_session, acc["acc_0"], acc["acc_1"], Decimal("1000"), external_id="t1")
    await _create_txn(db_session, acc["acc_0"], acc["acc_1"], Decimal("2000"), external_id="t2")
    await _create_txn(db_session, acc["acc_0"], acc["acc_1"], Decimal("3000"), external_id="t3")

    edges = await build_transaction_graph(db_session, hours_lookback=72)
    assert len(edges) == 1

    edge = edges[(str(acc["acc_0"].id), str(acc["acc_1"].id))]
    assert edge.total_amount == Decimal("6000")
    assert edge.txn_count == 3


@pytest.mark.asyncio
async def test_build_graph_min_amount_filter(
    db_session: AsyncSession, graph_accounts: dict[str, Account]
) -> None:
    """Edges below min_amount are excluded."""
    acc = graph_accounts
    await _create_txn(db_session, acc["acc_0"], acc["acc_1"], Decimal("500"))
    await _create_txn(db_session, acc["acc_0"], acc["acc_2"], Decimal("5000"))

    edges = await build_transaction_graph(
        db_session, hours_lookback=72, min_amount=Decimal("1000")
    )
    assert len(edges) == 1
    assert str(acc["acc_2"].id) in [edges[(str(acc["acc_0"].id), str(acc["acc_2"].id))].destination_account_id]


@pytest.mark.asyncio
async def test_build_graph_lookback_window(
    db_session: AsyncSession, graph_accounts: dict[str, Account]
) -> None:
    """Transactions outside lookback window are excluded."""
    acc = graph_accounts
    old_time = datetime.now(timezone.utc) - timedelta(hours=100)
    await _create_txn(db_session, acc["acc_0"], acc["acc_1"], Decimal("1000"), txn_timestamp=old_time)

    edges = await build_transaction_graph(db_session, hours_lookback=72)
    assert len(edges) == 0


# ---------------------------------------------------------------------------
# Cycle detection tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_cycles_no_cycle(
    db_session: AsyncSession, graph_accounts: dict[str, Account]
) -> None:
    """Linear chain of transactions produces no cycles."""
    acc = graph_accounts
    await _create_txn(db_session, acc["acc_0"], acc["acc_1"], Decimal("1000"))
    await _create_txn(db_session, acc["acc_1"], acc["acc_2"], Decimal("1000"))

    edges = await build_transaction_graph(db_session, hours_lookback=72)
    cycles = detect_cycles(edges)
    assert len(cycles) == 0


@pytest.mark.asyncio
async def test_detect_cycles_simple_cycle(
    db_session: AsyncSession, graph_accounts: dict[str, Account]
) -> None:
    """A→B→C→A forms a cycle."""
    acc = graph_accounts
    await _create_txn(db_session, acc["acc_0"], acc["acc_1"], Decimal("1000"))
    await _create_txn(db_session, acc["acc_1"], acc["acc_2"], Decimal("1000"))
    await _create_txn(db_session, acc["acc_2"], acc["acc_0"], Decimal("1000"))

    edges = await build_transaction_graph(db_session, hours_lookback=72)
    cycles = detect_cycles(edges)
    assert len(cycles) >= 1

    # Check that the cycle contains all three accounts
    cycle_accounts = set(cycles[0].cycle)
    assert str(acc["acc_0"].id) in cycle_accounts
    assert str(acc["acc_1"].id) in cycle_accounts
    assert str(acc["acc_2"].id) in cycle_accounts


@pytest.mark.asyncio
async def test_detect_cycles_multi_cycle(
    db_session: AsyncSession, graph_accounts: dict[str, Account]
) -> None:
    """Two separate cycles are both detected."""
    acc = graph_accounts
    # Cycle 1: A→B→C→A
    await _create_txn(db_session, acc["acc_0"], acc["acc_1"], Decimal("1000"))
    await _create_txn(db_session, acc["acc_1"], acc["acc_2"], Decimal("1000"))
    await _create_txn(db_session, acc["acc_2"], acc["acc_0"], Decimal("1000"))
    # Cycle 2: D→E→D
    await _create_txn(db_session, acc["acc_3"], acc["acc_4"], Decimal("2000"))
    await _create_txn(db_session, acc["acc_4"], acc["acc_3"], Decimal("2000"))

    edges = await build_transaction_graph(db_session, hours_lookback=72)
    cycles = detect_cycles(edges)
    assert len(cycles) >= 2


@pytest.mark.asyncio
async def test_detect_cycles_min_volume(
    db_session: AsyncSession, graph_accounts: dict[str, Account]
) -> None:
    """Cycles below min_cycle_volume are filtered out."""
    acc = graph_accounts
    await _create_txn(db_session, acc["acc_0"], acc["acc_1"], Decimal("10"))
    await _create_txn(db_session, acc["acc_1"], acc["acc_0"], Decimal("10"))

    edges = await build_transaction_graph(db_session, hours_lookback=72)
    cycles = detect_cycles(edges, min_cycle_volume=Decimal("100"))
    assert len(cycles) == 0


# ---------------------------------------------------------------------------
# Cluster detection tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_clusters_no_cluster(
    db_session: AsyncSession, graph_accounts: dict[str, Account]
) -> None:
    """Single edge does not form a cluster."""
    acc = graph_accounts
    await _create_txn(db_session, acc["acc_0"], acc["acc_1"], Decimal("1000"))

    edges = await build_transaction_graph(db_session, hours_lookback=72)
    clusters = detect_clusters(edges, min_cluster_size=3)
    assert len(clusters) == 0


@pytest.mark.asyncio
async def test_detect_clusters_fully_connected(
    db_session: AsyncSession, graph_accounts: dict[str, Account]
) -> None:
    """Fully connected 3-account component forms a cluster."""
    acc = graph_accounts
    # Fully connected: A↔B, B↔C, A↔C
    await _create_txn(db_session, acc["acc_0"], acc["acc_1"], Decimal("10000"))
    await _create_txn(db_session, acc["acc_1"], acc["acc_0"], Decimal("10000"))
    await _create_txn(db_session, acc["acc_1"], acc["acc_2"], Decimal("10000"))
    await _create_txn(db_session, acc["acc_2"], acc["acc_1"], Decimal("10000"))
    await _create_txn(db_session, acc["acc_0"], acc["acc_2"], Decimal("10000"))
    await _create_txn(db_session, acc["acc_2"], acc["acc_0"], Decimal("10000"))

    edges = await build_transaction_graph(db_session, hours_lookback=72)
    clusters = detect_clusters(edges, min_cluster_size=3, min_total_volume=Decimal("10000"))
    assert len(clusters) >= 1
    assert len(clusters[0].account_ids) == 3
    assert clusters[0].density_score > 0.5  # high density


@pytest.mark.asyncio
async def test_detect_clusters_min_volume_filter(
    db_session: AsyncSession, graph_accounts: dict[str, Account]
) -> None:
    """Clusters below min_total_volume are filtered out."""
    acc = graph_accounts
    await _create_txn(db_session, acc["acc_0"], acc["acc_1"], Decimal("100"))
    await _create_txn(db_session, acc["acc_1"], acc["acc_2"], Decimal("100"))
    await _create_txn(db_session, acc["acc_2"], acc["acc_0"], Decimal("100"))

    edges = await build_transaction_graph(db_session, hours_lookback=72)
    clusters = detect_clusters(edges, min_cluster_size=3, min_total_volume=Decimal("100000"))
    assert len(clusters) == 0


# ---------------------------------------------------------------------------
# Full analysis orchestrator tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_transaction_graph_empty(db_session: AsyncSession) -> None:
    """Analysis with no transactions returns empty result."""
    result = await analyze_transaction_graph(db_session)
    assert result["edge_count"] == 0
    assert result["account_count"] == 0
    assert result["total_volume"] == Decimal("0")
    assert result["cycles"] == []
    assert result["clusters"] == []


@pytest.mark.asyncio
async def test_analyze_transaction_graph_with_data(
    db_session: AsyncSession, graph_accounts: dict[str, Account]
) -> None:
    """Analysis with transaction data returns correct metrics."""
    acc = graph_accounts
    await _create_txn(db_session, acc["acc_0"], acc["acc_1"], Decimal("50000"))
    await _create_txn(db_session, acc["acc_1"], acc["acc_2"], Decimal("50000"))
    await _create_txn(db_session, acc["acc_2"], acc["acc_0"], Decimal("50000"))

    result = await analyze_transaction_graph(
        db_session,
        min_cluster_volume=Decimal("10000"),
        min_cycle_volume=Decimal("10000"),
    )

    assert result["edge_count"] == 3
    assert result["account_count"] == 3
    assert result["total_volume"] == Decimal("150000")
    assert len(result["cycles"]) >= 1
    assert len(result["clusters"]) >= 1


# ---------------------------------------------------------------------------
# Graph anomaly detector tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_graph_anomalies_no_anomaly(
    db_session: AsyncSession, graph_accounts: dict[str, Account]
) -> None:
    """Single transaction with no graph context returns not suspicious."""
    acc = graph_accounts
    txn = await _create_txn(db_session, acc["acc_0"], acc["acc_1"], Decimal("1000"))

    result = await check_graph_anomalies(db_session, txn, config={})
    assert result["is_suspicious"] is False
    assert len(result["reasons"]) == 0


@pytest.mark.asyncio
async def test_check_graph_anomalies_cycle(
    db_session: AsyncSession, graph_accounts: dict[str, Account]
) -> None:
    """Transaction in a cycle is flagged as suspicious."""
    acc = graph_accounts
    # Create a cycle: A→B→C→A
    txn1 = await _create_txn(db_session, acc["acc_0"], acc["acc_1"], Decimal("50000"))
    await _create_txn(db_session, acc["acc_1"], acc["acc_2"], Decimal("50000"))
    await _create_txn(db_session, acc["acc_2"], acc["acc_0"], Decimal("50000"))

    result = await check_graph_anomalies(
        db_session, txn1, config={"min_cycle_volume": 10000, "min_cluster_volume": 999999999}
    )
    assert result["is_suspicious"] is True
    assert any("cycle" in r.lower() for r in result["reasons"])
    assert result["severity"] in ("high", "critical")


@pytest.mark.asyncio
async def test_check_graph_anomalies_cluster(
    db_session: AsyncSession, graph_accounts: dict[str, Account]
) -> None:
    """Transaction in a dense cluster is flagged as suspicious."""
    acc = graph_accounts
    # Create a dense cluster
    txn = await _create_txn(db_session, acc["acc_0"], acc["acc_1"], Decimal("50000"))
    await _create_txn(db_session, acc["acc_1"], acc["acc_0"], Decimal("50000"))
    await _create_txn(db_session, acc["acc_1"], acc["acc_2"], Decimal("50000"))
    await _create_txn(db_session, acc["acc_2"], acc["acc_1"], Decimal("50000"))
    await _create_txn(db_session, acc["acc_0"], acc["acc_2"], Decimal("50000"))
    await _create_txn(db_session, acc["acc_2"], acc["acc_0"], Decimal("50000"))

    result = await check_graph_anomalies(
        db_session, txn, config={"min_cluster_volume": 10000, "min_cycle_volume": 999999999}
    )
    assert result["is_suspicious"] is True
    assert any("cluster" in r.lower() for r in result["reasons"])


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_cycles_self_loop(
    db_session: AsyncSession, graph_accounts: dict[str, Account]
) -> None:
    """Self-loops (account sending to itself) are not detected as cycles."""
    acc = graph_accounts
    await _create_txn(db_session, acc["acc_0"], acc["acc_0"], Decimal("1000"))

    edges = await build_transaction_graph(db_session, hours_lookback=72)
    cycles = detect_cycles(edges)
    assert len(cycles) == 0


@pytest.mark.asyncio
async def test_detect_cycles_max_length(
    db_session: AsyncSession, graph_accounts: dict[str, Account]
) -> None:
    """Cycles longer than max_cycle_length are not reported."""
    acc = graph_accounts
    # Create a 4-account cycle
    await _create_txn(db_session, acc["acc_0"], acc["acc_1"], Decimal("1000"))
    await _create_txn(db_session, acc["acc_1"], acc["acc_2"], Decimal("1000"))
    await _create_txn(db_session, acc["acc_2"], acc["acc_3"], Decimal("1000"))
    await _create_txn(db_session, acc["acc_3"], acc["acc_0"], Decimal("1000"))

    edges = await build_transaction_graph(db_session, hours_lookback=72)
    cycles = detect_cycles(edges, max_cycle_length=2)
    assert len(cycles) == 0


@pytest.mark.asyncio
async def test_detect_clusters_single_account(
    db_session: AsyncSession, graph_accounts: dict[str, Account]
) -> None:
    """Single account with no edges is not a cluster."""
    acc = graph_accounts
    # Only one account with transactions to itself
    await _create_txn(db_session, acc["acc_0"], acc["acc_0"], Decimal("1000"))

    edges = await build_transaction_graph(db_session, hours_lookback=72)
    clusters = detect_clusters(edges, min_cluster_size=2)
    assert len(clusters) == 0