"""AML Monitor — Graph Analysis Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GraphAnalysisRequest(BaseModel):
    """Request body for full graph analysis."""

    hours_lookback: int = Field(
        default=72, ge=1, le=720, description="Lookback window in hours"
    )
    min_amount: float | None = Field(
        default=None, ge=0, description="Minimum edge amount to include"
    )
    max_cycle_length: int = Field(
        default=10, ge=2, le=20, description="Maximum cycle length to detect"
    )
    min_cycle_volume: float = Field(
        default=50000.0, ge=0, description="Minimum cycle volume to report"
    )
    min_cluster_size: int = Field(
        default=3, ge=2, le=100, description="Minimum cluster size"
    )
    min_cluster_volume: float = Field(
        default=10000.0, ge=0, description="Minimum cluster volume"
    )


class GraphEdgeResponse(BaseModel):
    """A single edge in the transaction graph."""

    source_account_id: str = Field(description="Source account UUID")
    destination_account_id: str = Field(description="Destination account UUID")
    total_amount: str = Field(description="Total amount flowing through this edge")
    currency: str = Field(description="Currency code")
    txn_count: int = Field(description="Number of transactions")
    first_seen: str = Field(description="ISO timestamp of first transaction")
    last_seen: str = Field(description="ISO timestamp of last transaction")


class GraphCycleResponse(BaseModel):
    """A detected transaction cycle."""

    cycle: list[str] = Field(description="Ordered list of account UUIDs in the cycle")
    total_volume: str = Field(description="Total volume of the cycle")
    currency: str = Field(description="Primary currency")
    txn_count: int = Field(description="Number of transactions in the cycle")
    depth: int = Field(description="Length of the cycle (number of edges)")


class GraphClusterResponse(BaseModel):
    """A detected suspicious cluster."""

    account_ids: list[str] = Field(description="Account UUIDs in the cluster")
    total_volume: str = Field(description="Total transaction volume")
    currency: str = Field(description="Primary currency")
    txn_count: int = Field(description="Number of transactions")
    density_score: float = Field(description="Internal connectivity density (0-1)")
    reason: str = Field(description="Human-readable reason for flagging")


class GraphAnalysisResponse(BaseModel):
    """Full graph analysis result."""

    edge_count: int = Field(description="Number of edges in the graph")
    account_count: int = Field(description="Number of unique accounts")
    total_volume: str = Field(description="Total transaction volume")
    edges: list[dict] = Field(
        default_factory=list, description="List of graph edges"
    )
    cycles: list[dict] = Field(
        default_factory=list, description="Detected transaction cycles"
    )
    clusters: list[dict] = Field(
        default_factory=list, description="Detected suspicious clusters"
    )