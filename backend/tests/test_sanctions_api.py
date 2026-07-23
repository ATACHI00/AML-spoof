"""Tests for the sanctions screening API endpoints."""

from __future__ import annotations

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sanctions_list import SanctionsList

API_KEY = "dev-api-key-1"
AUTH_HEADER = {"X-API-Key": API_KEY}


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return AUTH_HEADER


@pytest.mark.asyncio
async def test_screen_name_no_match(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Screen a clean name — should return no match."""
    response = await client.post(
        "/api/v1/sanctions/screen",
        json={"name": "Alice Wonderland", "threshold": 0.88, "method": "jaro_winkler"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["triggered"] is False
    assert data["matches"] == []


@pytest.mark.asyncio
async def test_screen_name_with_match(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """Screen a name that matches a sanctions entry."""
    # Add a sanctions entry
    entry = SanctionsList(
        list_source="ofac",
        full_name="OSAMA BIN LADEN",
        name_variations=["USAMA BIN LADIN"],
        entity_type="individual",
        country="SA",
        program="SDGT",
        is_active=True,
        last_updated=date.today(),
    )
    db_session.add(entry)
    await db_session.flush()

    response = await client.post(
        "/api/v1/sanctions/screen",
        json={"name": "OSAMA BIN LADEN", "threshold": 0.88, "method": "jaro_winkler"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["triggered"] is True
    assert len(data["matches"]) >= 1
    assert data["matches"][0]["full_name"] == "OSAMA BIN LADEN"
    assert data["matches"][0]["score"] >= 0.95


@pytest.mark.asyncio
async def test_screen_name_fuzzy_match(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """Fuzzy match should work with slight name variations."""
    entry = SanctionsList(
        list_source="ofac",
        full_name="OSAMA BIN LADEN",
        entity_type="individual",
        country="SA",
        program="SDGT",
        is_active=True,
        last_updated=date.today(),
    )
    db_session.add(entry)
    await db_session.flush()

    response = await client.post(
        "/api/v1/sanctions/screen",
        json={"name": "Usama Bin Laden", "threshold": 0.80, "method": "jaro_winkler"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["triggered"] is True


@pytest.mark.asyncio
async def test_screen_name_validation(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Invalid method should return 422."""
    response = await client.post(
        "/api/v1/sanctions/screen",
        json={"name": "Test", "threshold": 0.88, "method": "invalid"},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_entries_empty(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """List sanctions entries when list is empty."""
    response = await client.get(
        "/api/v1/sanctions/entries", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["entries"] == []


@pytest.mark.asyncio
async def test_list_entries_with_data(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """List sanctions entries with data."""
    entries = [
        SanctionsList(
            list_source="ofac",
            full_name="ENTRY ONE",
            entity_type="individual",
            is_active=True,
            last_updated=date.today(),
        ),
        SanctionsList(
            list_source="eu",
            full_name="ENTRY TWO",
            entity_type="entity",
            is_active=True,
            last_updated=date.today(),
        ),
    ]
    for e in entries:
        db_session.add(e)
    await db_session.flush()

    response = await client.get(
        "/api/v1/sanctions/entries", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["entries"]) == 2


@pytest.mark.asyncio
async def test_search_entries(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """Search sanctions entries by name."""
    entry = SanctionsList(
        list_source="ofac",
        full_name="SPECIAL TARGET",
        entity_type="individual",
        is_active=True,
        last_updated=date.today(),
    )
    db_session.add(entry)
    await db_session.flush()

    response = await client.get(
        "/api/v1/sanctions/entries?query=SPECIAL", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["entries"][0]["full_name"] == "SPECIAL TARGET"


@pytest.mark.asyncio
async def test_stats(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """Get sanctions list statistics."""
    entries = [
        SanctionsList(
            list_source="ofac",
            full_name="A",
            entity_type="individual",
            is_active=True,
            last_updated=date.today(),
        ),
        SanctionsList(
            list_source="ofac",
            full_name="B",
            entity_type="entity",
            is_active=True,
            last_updated=date.today(),
        ),
    ]
    for e in entries:
        db_session.add(e)
    await db_session.flush()

    response = await client.get(
        "/api/v1/sanctions/stats", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["by_source"]["ofac"] == 2


@pytest.mark.asyncio
async def test_import_endpoint(
    client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test the import endpoint with a mocked download."""

    async def mock_import(db_session_factory):
        return 42

    monkeypatch.setattr(
        "app.api.v1.sanctions.import_ofac_sdn", mock_import
    )

    response = await client.post(
        "/api/v1/sanctions/import", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["imported"] == 42
    assert data["source"] == "ofac"


@pytest.mark.asyncio
async def test_unauthorized_access(
    client: AsyncClient,
) -> None:
    """Requests with invalid API key should return 401."""
    response = await client.post(
        "/api/v1/sanctions/screen",
        json={"name": "Test", "threshold": 0.88, "method": "jaro_winkler"},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401