"""AML Monitor — Graph Analysis API endpoints.

REST API для построения графа транзакций, обнаружения циклов и кластеров.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import verify_api_key
from app.database import get_db
from app.schemas.graph import (
    GraphAnalysisRequest,
    GraphAnalysisResponse,
    GraphClusterResponse,
    GraphCycleResponse,
    GraphEdgeResponse,
)
from app.services.graph_analysis import analyze_transaction_graph

router = APIRouter(prefix="/graph", tags=["graph"])


def _edge_to_dict(edge) -> dict:
    return {
        "source_account_id": edge.source_account_id,
        "destination_account_id": edge.destination_account_id,
        "total_amount": str(edge.total_amount),
        "currency": edge.currency,
        "txn_count": edge.txn_count,
        "first_seen": edge.first_seen.isoformat(),
        "last_seen": edge.last_seen.isoformat(),
    }


def _cycle_to_dict(cycle) -> dict:
    return {
        "cycle": cycle.cycle,
        "total_volume": str(cycle.total_volume),
        "currency": cycle.currency,
        "txn_count": cycle.txn_count,
        "depth": cycle.depth,
    }


def _cluster_to_dict(cluster) -> dict:
    return {
        "account_ids": cluster.account_ids,
        "total_volume": str(cluster.total_volume),
        "currency": cluster.currency,
        "txn_count": cluster.txn_count,
        "density_score": cluster.density_score,
        "reason": cluster.reason,
    }


@router.post("/analyze", response_model=GraphAnalysisResponse)
async def analyze_graph(
    payload: GraphAnalysisRequest,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> GraphAnalysisResponse:
    """Run full graph analysis: build transaction graph, detect cycles and clusters.

    Returns edge list, detected cycles, and suspicious clusters.
    """
    result = await analyze_transaction_graph(
        db=db,
        hours_lookback=payload.hours_lookback,
        min_amount=Decimal(str(payload.min_amount)) if payload.min_amount is not None else None,
        max_cycle_length=payload.max_cycle_length,
        min_cycle_volume=Decimal(str(payload.min_cycle_volume)),
        min_cluster_size=payload.min_cluster_size,
        min_cluster_volume=Decimal(str(payload.min_cluster_volume)),
    )

    return GraphAnalysisResponse(
        edge_count=result["edge_count"],
        account_count=result["account_count"],
        total_volume=str(result["total_volume"]),
        edges=[_edge_to_dict(e) for e in result.get("_edges", [])],
        cycles=[_cycle_to_dict(c) for c in result["cycles"]],
        clusters=[_cluster_to_dict(c) for c in result["clusters"]],
    )


@router.get("/cycles", response_model=list[GraphCycleResponse])
async def list_cycles(
    hours_lookback: int = Query(72, ge=1, le=720, description="Lookback window in hours"),
    min_cycle_volume: float = Query(50000.0, ge=0, description="Minimum cycle volume"),
    max_cycle_length: int = Query(10, ge=2, le=20, description="Maximum cycle length"),
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> list[GraphCycleResponse]:
    """Detect and return transaction cycles in the graph."""
    result = await analyze_transaction_graph(
        db=db,
        hours_lookback=hours_lookback,
        max_cycle_length=max_cycle_length,
        min_cycle_volume=Decimal(str(min_cycle_volume)),
        min_cluster_size=1000,  # effectively disable cluster detection
        min_cluster_volume=Decimal("999999999"),
    )

    return [
        GraphCycleResponse(
            cycle=c.cycle,
            total_volume=str(c.total_volume),
            currency=c.currency,
            txn_count=c.txn_count,
            depth=c.depth,
        )
        for c in result["cycles"]
    ]


@router.get("/clusters", response_model=list[GraphClusterResponse])
async def list_clusters(
    hours_lookback: int = Query(72, ge=1, le=720, description="Lookback window in hours"),
    min_cluster_size: int = Query(3, ge=2, le=100, description="Minimum cluster size"),
    min_cluster_volume: float = Query(10000.0, ge=0, description="Minimum cluster volume"),
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> list[GraphClusterResponse]:
    """Detect and return suspicious clusters in the transaction graph."""
    result = await analyze_transaction_graph(
        db=db,
        hours_lookback=hours_lookback,
        max_cycle_length=100,  # effectively disable cycle detection
        min_cycle_volume=Decimal("999999999"),
        min_cluster_size=min_cluster_size,
        min_cluster_volume=Decimal(str(min_cluster_volume)),
    )

    return [
        GraphClusterResponse(
            account_ids=c.account_ids,
            total_volume=str(c.total_volume),
            currency=c.currency,
            txn_count=c.txn_count,
            density_score=c.density_score,
            reason=c.reason,
        )
        for c in result["clusters"]
    ]


@router.get("/edges", response_model=list[GraphEdgeResponse])
async def list_edges(
    hours_lookback: int = Query(72, ge=1, le=720, description="Lookback window in hours"),
    min_amount: float | None = Query(None, ge=0, description="Minimum edge amount"),
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> list[GraphEdgeResponse]:
    """Return the transaction graph edges (aggregated account-to-account flows)."""
    from app.services.graph_analysis import build_transaction_graph

    edges = await build_transaction_graph(
        db=db,
        hours_lookback=hours_lookback,
        min_amount=Decimal(str(min_amount)) if min_amount is not None else None,
    )

    return [
        GraphEdgeResponse(
            source_account_id=edge.source_account_id,
            destination_account_id=edge.destination_account_id,
            total_amount=str(edge.total_amount),
            currency=edge.currency,
            txn_count=edge.txn_count,
            first_seen=edge.first_seen.isoformat(),
            last_seen=edge.last_seen.isoformat(),
        )
        for edge in edges.values()
    ]