"""AML Monitor — Graph Analysis Service.

Построение графа транзакций, обнаружение циклов и подозрительных кластеров.

Алгоритмы:
1. **Transaction Graph** — направленный взвешенный граф (account → account, вес = сумма)
2. **Cycle Detection** — DFS-based поиск циклов произвольной длины
3. **Suspicious Cluster Detection** — поиск кластеров по порогу плотности (минимальный объём средств)
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


class GraphEdge:
    """A directed edge in the transaction graph."""

    def __init__(
        self,
        source_account_id: str,
        destination_account_id: str,
        total_amount: Decimal,
        currency: str,
        txn_count: int,
        first_seen: datetime,
        last_seen: datetime,
    ) -> None:
        self.source_account_id = source_account_id
        self.destination_account_id = destination_account_id
        self.total_amount = total_amount
        self.currency = currency
        self.txn_count = txn_count
        self.first_seen = first_seen
        self.last_seen = last_seen


class GraphCluster:
    """A cluster of accounts identified as suspicious."""

    def __init__(
        self,
        account_ids: list[str],
        total_volume: Decimal,
        currency: str,
        txn_count: int,
        density_score: float,
        reason: str,
    ) -> None:
        self.account_ids = account_ids
        self.total_volume = total_volume
        self.currency = currency
        self.txn_count = txn_count
        self.density_score = density_score
        self.reason = reason


class CycleResult:
    """Result of cycle detection."""

    def __init__(
        self,
        cycle: list[str],
        total_volume: Decimal,
        currency: str,
        txn_count: int,
        depth: int,
    ) -> None:
        self.cycle = cycle
        self.total_volume = total_volume
        self.currency = currency
        self.txn_count = txn_count
        self.depth = depth


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


async def build_transaction_graph(
    db: AsyncSession,
    hours_lookback: int = 72,
    min_amount: Decimal | None = None,
) -> dict[tuple[str, str], GraphEdge]:
    """Build a directed weighted graph from recent transactions.

    Args:
        db: Database session.
        hours_lookback: Look back this many hours for transactions.
        min_amount: Optional minimum total amount to include an edge.

    Returns:
        Dict mapping ``(source_account_id, destination_account_id)`` → ``GraphEdge``.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_lookback)

    logger.debug(
        "build_transaction_graph: hours_lookback=%d cutoff=%s",
        hours_lookback, cutoff.isoformat(),
    )

    query = (
        select(
            Transaction.source_account_id,
            Transaction.destination_account_id,
            Transaction.currency,
            sa_func.sum(Transaction.amount).label("total_amount"),
            sa_func.count(Transaction.id).label("txn_count"),
            sa_func.min(Transaction.txn_timestamp).label("first_seen"),
            sa_func.max(Transaction.txn_timestamp).label("last_seen"),
        )
        .where(Transaction.txn_timestamp >= cutoff)
        .group_by(
            Transaction.source_account_id,
            Transaction.destination_account_id,
            Transaction.currency,
        )
    )

    result = await db.execute(query)
    rows = result.all()

    logger.debug("build_transaction_graph: got %d rows", len(rows))

    edges: dict[tuple[str, str], GraphEdge] = {}

    for row in rows:
        source = str(row.source_account_id)
        dest = str(row.destination_account_id)
        total = row.total_amount or Decimal("0")
        currency = row.currency or "UNKNOWN"

        logger.debug(
            "  edge: %s -> %s amount=%s currency=%s txns=%d",
            source, dest, total, currency, row.txn_count,
        )

        if min_amount is not None and total < min_amount:
            logger.debug("  -> skipped (below min_amount=%s)", min_amount)
            continue

        if row.last_seen is None:
            logger.warning(
                "last_seen is None for edge %s->%s, using first_seen",
                source, dest,
            )

        edges[(source, dest)] = GraphEdge(
            source_account_id=source,
            destination_account_id=dest,
            total_amount=total,
            currency=currency,
            txn_count=row.txn_count,
            first_seen=row.first_seen,
            last_seen=row.last_seen or row.first_seen or datetime.now(timezone.utc),
        )

    logger.debug("build_transaction_graph: returning %d edges", len(edges))
    return edges


# ---------------------------------------------------------------------------
# Cycle detection (DFS-based)
# ---------------------------------------------------------------------------


def _build_adjacency_list(
    edges: dict[tuple[str, str], GraphEdge],
) -> dict[str, list[tuple[str, GraphEdge]]]:
    """Convert edge dict to adjacency list.

    Self-loops (source == destination) are excluded from the adjacency
    list since they do not represent meaningful cycles for AML analysis.
    """
    adj: dict[str, list[tuple[str, GraphEdge]]] = defaultdict(list)
    for (source, dest), edge in edges.items():
        if source != dest:  # skip self-loops
            adj[source].append((dest, edge))
    return adj


def detect_cycles(
    edges: dict[tuple[str, str], GraphEdge],
    max_cycle_length: int = 10,
    min_cycle_volume: Decimal = Decimal("0"),
) -> list[CycleResult]:
    """Detect cycles in the transaction graph using DFS.

    Args:
        edges: The transaction graph edges.
        max_cycle_length: Maximum cycle length to consider (to limit complexity).
        min_cycle_volume: Minimum total volume for a cycle to be reported.

    Returns:
        List of ``CycleResult`` instances.
    """
    adj = _build_adjacency_list(edges)
    all_accounts = set(adj.keys()) | {dest for (_, dest) in edges}

    logger.debug(
        "detect_cycles: %d accounts, %d edges, max_depth=%d, min_volume=%s",
        len(all_accounts), len(edges), max_cycle_length, min_cycle_volume,
    )

    cycles: list[CycleResult] = []
    visited: set[str] = set()
    path: list[str] = []
    path_set: set[str] = set()
    dfs_depth = 0

    def dfs(node: str, depth: int) -> None:
        nonlocal dfs_depth
        dfs_depth = max(dfs_depth, depth)

        if depth > max_cycle_length:
            logger.debug("  dfs: max depth %d reached at %s", max_cycle_length, node)
            return

        visited.add(node)
        path.append(node)
        path_set.add(node)

        for neighbor, edge in adj.get(node, []):
            if neighbor in path_set:
                # Found a cycle — extract it
                cycle_start = path.index(neighbor)
                cycle_path = path[cycle_start:] + [neighbor]

                # Calculate cycle metrics
                cycle_volume = Decimal("0")
                cycle_txn_count = 0
                currency = edge.currency

                for i in range(len(cycle_path) - 1):
                    e = edges.get((cycle_path[i], cycle_path[i + 1]))
                    if e:
                        cycle_volume += e.total_amount
                        cycle_txn_count += e.txn_count

                logger.debug(
                    "  cycle found: %s volume=%s txns=%d depth=%d",
                    " -> ".join(cycle_path), cycle_volume, cycle_txn_count, len(cycle_path) - 1,
                )

                if cycle_volume >= min_cycle_volume:
                    cycles.append(CycleResult(
                        cycle=list(dict.fromkeys(cycle_path)),  # unique, ordered
                        total_volume=cycle_volume,
                        currency=currency,
                        txn_count=cycle_txn_count,
                        depth=len(cycle_path) - 1,
                    ))
                else:
                    logger.debug("    -> skipped (below min_cycle_volume)")

            elif neighbor not in visited:
                dfs(neighbor, depth + 1)

        path.pop()
        path_set.discard(node)

    for account in sorted(all_accounts):
        if account not in visited:
            dfs(account, 0)

    logger.debug(
        "detect_cycles: %d cycles found, max_dfs_depth=%d",
        len(cycles), dfs_depth,
    )

    # Deduplicate cycles — keep only unique sets of accounts
    seen_sets: set[frozenset[str]] = set()
    unique_cycles: list[CycleResult] = []
    for cycle in sorted(cycles, key=lambda c: c.total_volume, reverse=True):
        cycle_set = frozenset(cycle.cycle)
        if cycle_set not in seen_sets:
            seen_sets.add(cycle_set)
            unique_cycles.append(cycle)

    return unique_cycles


# ---------------------------------------------------------------------------
# Suspicious cluster detection
# ---------------------------------------------------------------------------


def detect_clusters(
    edges: dict[tuple[str, str], GraphEdge],
    min_cluster_size: int = 3,
    min_total_volume: Decimal = Decimal("10000"),
) -> list[GraphCluster]:
    """Detect suspicious clusters using BFS connected components + density scoring.

    A cluster is considered suspicious if:
    - It has at least ``min_cluster_size`` accounts.
    - The total transaction volume exceeds ``min_total_volume``.
    - The internal connectivity (density) is above a heuristic threshold.

    Args:
        edges: The transaction graph edges.
        min_cluster_size: Minimum number of accounts in a cluster.
        min_total_volume: Minimum total transaction volume.

    Returns:
        List of ``GraphCluster`` instances, sorted by density_score descending.
    """
    adj = _build_adjacency_list(edges)

    # Build undirected adjacency for BFS
    undirected_adj: dict[str, set[str]] = defaultdict(set)
    for (source, dest) in edges:
        undirected_adj[source].add(dest)
        undirected_adj[dest].add(source)

    all_accounts = set(undirected_adj.keys())
    visited: set[str] = set()
    clusters: list[GraphCluster] = []

    for account in all_accounts:
        if account in visited:
            continue

        # BFS to find connected component
        component: set[str] = set()
        queue: deque[str] = deque([account])
        visited.add(account)

        while queue:
            node = queue.popleft()
            component.add(node)
            for neighbor in undirected_adj.get(node, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        if len(component) < min_cluster_size:
            continue

        # Calculate cluster metrics
        total_volume = Decimal("0")
        txn_count = 0
        internal_edges = 0
        possible_edges = len(component) * (len(component) - 1)
        currencies: set[str] = set()

        for (source, dest), edge in edges.items():
            if source in component and dest in component:
                total_volume += edge.total_amount
                txn_count += edge.txn_count
                internal_edges += 1
                currencies.add(edge.currency)

        if total_volume < min_total_volume:
            continue

        # Density score: ratio of actual internal edges to possible edges
        density = internal_edges / possible_edges if possible_edges > 0 else 0.0

        # Determine primary currency (most common)
        primary_currency = max(currencies) if currencies else "UNKNOWN"

        # Reason based on characteristics
        reasons: list[str] = []
        if density > 0.5:
            reasons.append(f"highly interconnected (density={density:.2f})")
        if total_volume > Decimal("100000"):
            reasons.append(f"high volume ({total_volume} {primary_currency})")
        if txn_count > 50:
            reasons.append(f"high transaction count ({txn_count})")

        reason = "; ".join(reasons) if reasons else f"cluster of {len(component)} accounts"

        clusters.append(GraphCluster(
            account_ids=sorted(component),
            total_volume=total_volume,
            currency=primary_currency,
            txn_count=txn_count,
            density_score=density,
            reason=reason,
        ))

    # Sort by density descending
    clusters.sort(key=lambda c: c.density_score, reverse=True)
    return clusters


# ---------------------------------------------------------------------------
# High-level analysis orchestrator
# ---------------------------------------------------------------------------


async def analyze_transaction_graph(
    db: AsyncSession,
    hours_lookback: int = 72,
    min_amount: Decimal | None = None,
    max_cycle_length: int = 10,
    min_cycle_volume: Decimal = Decimal("0"),
    min_cluster_size: int = 3,
    min_cluster_volume: Decimal = Decimal("10000"),
) -> dict[str, Any]:
    """Run full graph analysis: build graph, detect cycles and clusters.

    Returns:
        A dict with keys:
        - ``edge_count``: number of edges in the graph.
        - ``account_count``: number of unique accounts.
        - ``total_volume``: total transaction volume.
        - ``cycles``: list of detected cycles.
        - ``clusters``: list of detected suspicious clusters.
    """
    edges = await build_transaction_graph(
        db=db,
        hours_lookback=hours_lookback,
        min_amount=min_amount,
    )

    if not edges:
        return {
            "edge_count": 0,
            "account_count": 0,
            "total_volume": Decimal("0"),
            "cycles": [],
            "clusters": [],
        }

    # Calculate total volume
    total_volume = sum(e.total_amount for e in edges.values())

    # Unique accounts
    accounts: set[str] = set()
    for (source, dest) in edges:
        accounts.add(source)
        accounts.add(dest)

    cycles = detect_cycles(
        edges=edges,
        max_cycle_length=max_cycle_length,
        min_cycle_volume=min_cycle_volume,
    )

    clusters = detect_clusters(
        edges=edges,
        min_cluster_size=min_cluster_size,
        min_total_volume=min_cluster_volume,
    )

    return {
        "edge_count": len(edges),
        "account_count": len(accounts),
        "total_volume": total_volume,
        "cycles": cycles,
        "clusters": clusters,
    }


# ---------------------------------------------------------------------------
# Graph anomaly detector for Rule Engine integration
# ---------------------------------------------------------------------------


async def check_graph_anomalies(
    db: AsyncSession,
    transaction: Transaction,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Check if a transaction is part of suspicious graph patterns.

    This is called by the ``graph_anomaly`` rule engine detector.

    Config keys:
    - ``hours_lookback`` (int, default 72): lookback window.
    - ``max_cycle_length`` (int, default 6): max cycle length.
    - ``min_cycle_volume`` (float, default 50000): min cycle volume.
    - ``min_cluster_size`` (int, default 3): min cluster size.
    - ``min_cluster_volume`` (float, default 50000): min cluster volume.

    Returns:
        Dict with keys:
        - ``is_suspicious``: bool.
        - ``reasons``: list of reason strings.
        - ``severity``: str (low/medium/high/critical).
        - ``risk_score``: Decimal 0-100.
    """
    hours_lookback = int(config.get("hours_lookback", 72))
    max_cycle_length = int(config.get("max_cycle_length", 6))
    min_cycle_volume = Decimal(str(config.get("min_cycle_volume", "50000")))
    min_cluster_size = int(config.get("min_cluster_size", 3))
    min_cluster_volume = Decimal(str(config.get("min_cluster_volume", "50000")))

    logger.debug(
        "check_graph_anomalies: txn=%s config=%s",
        transaction.id, config,
    )

    result = await analyze_transaction_graph(
        db=db,
        hours_lookback=hours_lookback,
        max_cycle_length=max_cycle_length,
        min_cycle_volume=min_cycle_volume,
        min_cluster_size=min_cluster_size,
        min_cluster_volume=min_cluster_volume,
    )

    logger.debug(
        "check_graph_anomalies: graph has %d edges, %d accounts, %d cycles, %d clusters",
        result["edge_count"], result["account_count"],
        len(result["cycles"]), len(result["clusters"]),
    )

    reasons: list[str] = []
    max_severity = "low"
    risk_score = Decimal("0")

    # Check if the transaction's accounts are in any cycle
    txn_source = str(transaction.source_account_id)
    txn_dest = str(transaction.destination_account_id)

    for cycle in result.get("cycles", []):
        if txn_source in cycle.cycle or txn_dest in cycle.cycle:
            cycle_risk = min(Decimal("80"), cycle.total_volume / Decimal("1000"))
            logger.debug(
                "  cycle match: %s volume=%s risk_score=%s",
                " -> ".join(cycle.cycle), cycle.total_volume, cycle_risk,
            )
            reasons.append(
                f"Account involved in transaction cycle: "
                f"{' → '.join(cycle.cycle)} "
                f"(volume: {cycle.total_volume} {cycle.currency})"
            )
            max_severity = "high"
            risk_score = max(risk_score, cycle_risk)

    # Check if the transaction's accounts are in any suspicious cluster
    for cluster in result.get("clusters", []):
        if txn_source in cluster.account_ids or txn_dest in cluster.account_ids:
            cluster_risk = min(Decimal("90"), cluster.total_volume / Decimal("1000"))
            logger.debug(
                "  cluster match: %d accounts volume=%s density=%.2f risk_score=%s",
                len(cluster.account_ids), cluster.total_volume,
                cluster.density_score, cluster_risk,
            )
            reasons.append(
                f"Account part of suspicious cluster: "
                f"{len(cluster.account_ids)} accounts, "
                f"volume: {cluster.total_volume} {cluster.currency}, "
                f"density: {cluster.density_score:.2f}"
            )
            if cluster.density_score > 0.7:
                max_severity = "critical"
            elif cluster.density_score > 0.4:
                max_severity = "high" if max_severity != "critical" else max_severity
            risk_score = max(risk_score, cluster_risk)

    if not reasons:
        logger.debug("  -> no graph anomalies detected")
        return {
            "is_suspicious": False,
            "reasons": [],
            "severity": "low",
            "risk_score": Decimal("0"),
        }

    risk_score = min(risk_score, Decimal("100"))
    logger.debug(
        "  -> suspicious: severity=%s risk_score=%s reasons=%d",
        max_severity, risk_score, len(reasons),
    )

    return {
        "is_suspicious": True,
        "reasons": reasons,
        "severity": max_severity,
        "risk_score": risk_score,
    }