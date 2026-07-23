"""Tests for Audit Log API endpoints.

Covers:
- GET /api/v1/audit/logs — list audit logs
- GET /api/v1/audit/logs/{id} — get single audit log
- GET /api/v1/audit/verify — verify hash chain integrity
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.models.audit_log import AuditLog
from app.models.rule import Rule
from app.models.transaction import Transaction
from app.utils.hashing import compute_audit_hash

API_KEY = "dev-api-key-1"
HEADERS = {"X-API-Key": API_KEY}


async def _create_audit_entry(
    db_session: AsyncSession,
    previous_hash: str | None = None,
) -> AuditLog:
    """Helper to create an audit log entry."""
    now = datetime.now(timezone.utc)
    current_hash = compute_audit_hash(
        previous_hash=previous_hash,
        entity_type="alert",
        entity_id="test-entity-1",
        action="status_closed",
        actor_id="test-actor",
        changes={"status": {"before": "new", "after": "closed"}},
        created_at=now,
    )
    entry = AuditLog(
        entity_type="alert",
        entity_id="test-entity-1",
        action="status_closed",
        actor_id="test-actor",
        changes={"status": {"before": "new", "after": "closed"}},
        previous_hash=previous_hash,
        current_hash=current_hash,
        created_at=now,
    )
    db_session.add(entry)
    await db_session.flush()
    return entry


# ---------------------------------------------------------------------------
# GET /api/v1/audit/logs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_audit_logs_empty(client: AsyncClient) -> None:
    """Empty audit log returns empty list."""
    response = await client.get("/api/v1/audit/logs", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_audit_logs_with_data(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Audit logs are returned correctly."""
    await _create_audit_entry(db_session)

    response = await client.get("/api/v1/audit/logs", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) >= 1
    assert data["items"][0]["entity_type"] == "alert"
    assert data["items"][0]["action"] == "status_closed"
    assert data["items"][0]["current_hash"] is not None


@pytest.mark.asyncio
async def test_list_audit_logs_filter_entity_type(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Filter by entity_type works."""
    await _create_audit_entry(db_session)

    response = await client.get(
        "/api/v1/audit/logs",
        headers=HEADERS,
        params={"entity_type": "alert"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) >= 1

    response = await client.get(
        "/api/v1/audit/logs",
        headers=HEADERS,
        params={"entity_type": "nonexistent"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []


@pytest.mark.asyncio
async def test_list_audit_logs_pagination(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Pagination works correctly."""
    for i in range(5):
        await _create_audit_entry(db_session)

    response = await client.get(
        "/api/v1/audit/logs",
        headers=HEADERS,
        params={"page": 1, "page_size": 2},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) <= 2
    assert data["page"] == 1
    assert data["page_size"] == 2


# ---------------------------------------------------------------------------
# GET /api/v1/audit/logs/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_audit_log_by_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Get single audit log by ID."""
    entry = await _create_audit_entry(db_session)

    response = await client.get(
        f"/api/v1/audit/logs/{entry.id}",
        headers=HEADERS,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(entry.id)
    assert data["action"] == "status_closed"


@pytest.mark.asyncio
async def test_get_audit_log_not_found(client: AsyncClient) -> None:
    """Non-existent audit log returns 404."""
    response = await client.get(
        "/api/v1/audit/logs/00000000-0000-0000-0000-000000000000",
        headers=HEADERS,
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/audit/verify
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_audit_chain_empty(client: AsyncClient) -> None:
    """Empty audit log chain is intact."""
    response = await client.get("/api/v1/audit/verify", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["is_intact"] is True
    assert data["total_entries"] == 0


@pytest.mark.asyncio
async def test_verify_audit_chain_intact(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Valid hash chain is reported as intact."""
    prev_hash = None
    for _ in range(3):
        entry = await _create_audit_entry(db_session, previous_hash=prev_hash)
        prev_hash = entry.current_hash

    response = await client.get("/api/v1/audit/verify", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["is_intact"] is True
    assert data["total_entries"] >= 3
    assert data["broken_links"] == []


@pytest.mark.asyncio
async def test_verify_audit_chain_tampered(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Tampered hash chain is detected."""
    prev = None
    entries = []
    for _ in range(3):
        entry = await _create_audit_entry(db_session, previous_hash=prev)
        entries.append(entry)
        prev = entry.current_hash

    # Tamper with the second entry
    entries[1].current_hash = "tampered_hash"
    await db_session.flush()

    response = await client.get("/api/v1/audit/verify", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["is_intact"] is False
    assert len(data["broken_links"]) >= 1


# ---------------------------------------------------------------------------
# Unauthorized access
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_api_unauthorized(client: AsyncClient) -> None:
    """Request without valid API key returns 401."""
    response = await client.get(
        "/api/v1/audit/logs",
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401