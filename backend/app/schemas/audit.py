"""AML Monitor — Audit Log Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AuditLogResponse(BaseModel):
    """A single audit log entry."""

    id: str = Field(description="Audit log entry ID")
    entity_type: str = Field(description="Type of entity (alert, case, rule)")
    entity_id: str = Field(description="Entity ID")
    action: str = Field(description="Action performed")
    actor_id: str = Field(description="Who performed the action")
    changes: dict | None = Field(default=None, description="Before/after diff")
    previous_hash: str | None = Field(default=None, description="Hash of previous entry")
    current_hash: str = Field(description="Hash of this entry")
    created_at: str = Field(description="ISO timestamp")


class AuditLogListResponse(BaseModel):
    """Paginated list of audit log entries."""

    items: list[AuditLogResponse] = Field(description="List of audit log entries")
    total: int = Field(description="Total number of entries")
    page: int = Field(description="Current page number")
    page_size: int = Field(description="Items per page")


class AuditLogVerifyResponse(BaseModel):
    """Result of audit log hash chain verification."""

    is_intact: bool = Field(description="Whether the hash chain is intact")
    total_entries: int = Field(description="Total number of entries checked")
    broken_links: list[dict] = Field(
        default_factory=list,
        description="List of broken links (empty if intact)",
    )