"""Tests for transaction ingestion API and service.

Covers:
- Single transaction creation (POST /api/v1/transactions/)
- Idempotency (same external_id → 200)
- Unknown account → 422
- CSV batch import (POST /api/v1/transactions/batch)
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncGenerator
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_db
from app.main import app
from app.models import Account, Base, Client, Transaction

TEST_DATABASE_URL = "sqlite+aiosqlite://"

API_KEY = "dev-api-key-1"
HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture(autouse=True)
def mock_celery():
    """Mock Celery's process_transaction.delay to avoid Redis dependency."""
    with patch("app.api.v1.transactions.process_transaction.delay") as mock:
        mock.return_value = None
        yield


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="session")
async def engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
        await session.close()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession) -> AsyncSession:
    """Seed the database with a client and two accounts."""
    client = Client(
        external_id="CLIENT-TXN-001",
        name="Transaction Test Client",
        client_type="legal_entity",
        risk_score=Decimal("10.00"),
    )
    db_session.add(client)
    await db_session.flush()

    src = Account(
        client_id=client.id,
        account_number="SOURCE-001",
        currency="USD",
        balance=Decimal("50000.00"),
    )
    dst = Account(
        client_id=client.id,
        account_number="DEST-001",
        currency="USD",
        balance=Decimal("10000.00"),
    )
    db_session.add(src)
    db_session.add(dst)
    await db_session.flush()
    return db_session


# ── Helpers ───────────────────────────────────────────────────────────


def make_txn_payload(
    external_id: str = "TXN-001",
    source: str = "SOURCE-001",
    dest: str = "DEST-001",
    amount: str = "1500.00",
    currency: str = "USD",
    channel: str | None = "wire",
) -> dict:
    return {
        "external_id": external_id,
        "source_account_number": source,
        "destination_account_number": dest,
        "amount": amount,
        "currency": currency,
        "txn_timestamp": datetime.now(timezone.utc).isoformat(),
        "channel": channel,
    }


# ── Tests: POST /api/v1/transactions/ ────────────────────────────────


@pytest.mark.asyncio
async def test_create_transaction_success(client: AsyncClient, seeded_db: AsyncSession):
    """A valid transaction should return 201 with the created record."""
    payload = make_txn_payload()
    resp = await client.post("/api/v1/transactions/", json=payload, headers=HEADERS)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["external_id"] == "TXN-001"
    assert data["amount"] == "1500.00"
    assert data["currency"] == "USD"
    assert data["status"] == "pending"
    assert "id" in data
    assert "ingested_at" in data


@pytest.mark.asyncio
async def test_create_transaction_idempotent(client: AsyncClient, seeded_db: AsyncSession):
    """Same external_id twice → second returns 200 with X-Idempotent header."""
    payload = make_txn_payload(external_id="IDEMP-001")
    resp1 = await client.post("/api/v1/transactions/", json=payload, headers=HEADERS)
    assert resp1.status_code == 201

    resp2 = await client.post("/api/v1/transactions/", json=payload, headers=HEADERS)
    assert resp2.status_code == 200
    assert resp2.headers.get("x-idempotent") == "true"
    # Both responses should reference the same transaction
    assert resp2.json()["id"] == resp1.json()["id"]


@pytest.mark.asyncio
async def test_create_transaction_unknown_account(client: AsyncClient, seeded_db: AsyncSession):
    """Unknown account number → 422."""
    payload = make_txn_payload(source="NONEXISTENT")
    resp = await client.post("/api/v1/transactions/", json=payload, headers=HEADERS)
    assert resp.status_code == 422
    assert "NONEXISTENT" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_transaction_missing_api_key(client: AsyncClient, seeded_db: AsyncSession):
    """Missing API key → 401 (or 403 if debug mode allows)."""
    from app.config import settings

    # Temporarily disable debug mode to enforce API key check
    original_debug = settings.debug
    settings.debug = False
    try:
        payload = make_txn_payload()
        resp = await client.post("/api/v1/transactions/", json=payload)
        assert resp.status_code == 401
    finally:
        settings.debug = original_debug


# ── Tests: POST /api/v1/transactions/batch ───────────────────────────


CSV_VALID = """\
external_id,source_account_number,destination_account_number,amount,currency,txn_timestamp,channel
BATCH-001,SOURCE-001,DEST-001,200.00,USD,2025-01-15T10:00:00Z,ach
BATCH-002,SOURCE-001,DEST-001,300.00,USD,2025-01-15T10:05:00Z,wire
"""

CSV_PARTIAL_ERRORS = """\
external_id,source_account_number,destination_account_number,amount,currency,txn_timestamp,channel
BATCH-003,SOURCE-001,DEST-001,400.00,USD,2025-01-15T10:10:00Z,wire
,SOURCE-001,DEST-001,500.00,USD,2025-01-15T10:15:00Z,wire
BATCH-005,UNKNOWN,DEST-001,600.00,USD,2025-01-15T10:20:00Z,wire
"""


@pytest.mark.asyncio
async def test_batch_import_success(client: AsyncClient, seeded_db: AsyncSession):
    """Valid CSV → all rows imported."""
    resp = await client.post(
        "/api/v1/transactions/batch",
        files={"file": ("txns.csv", CSV_VALID, "text/csv")},
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["imported"] == 2
    assert data["skipped"] == 0
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_batch_import_partial_errors(client: AsyncClient, seeded_db: AsyncSession):
    """CSV with some invalid rows → partial import with error list."""
    resp = await client.post(
        "/api/v1/transactions/batch",
        files={"file": ("txns.csv", CSV_PARTIAL_ERRORS, "text/csv")},
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["imported"] == 1  # BATCH-003
    assert data["skipped"] == 0
    assert len(data["errors"]) == 2  # missing external_id + unknown account


@pytest.mark.asyncio
async def test_batch_import_idempotent(client: AsyncClient, seeded_db: AsyncSession):
    """Re-importing same external_ids → skipped, not duplicated."""
    # First import
    resp1 = await client.post(
        "/api/v1/transactions/batch",
        files={"file": ("txns.csv", CSV_VALID, "text/csv")},
        headers=HEADERS,
    )
    assert resp1.status_code == 200
    assert resp1.json()["imported"] == 2

    # Second import (same data)
    resp2 = await client.post(
        "/api/v1/transactions/batch",
        files={"file": ("txns.csv", CSV_VALID, "text/csv")},
        headers=HEADERS,
    )
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["imported"] == 0
    assert data["skipped"] == 2
    assert data["errors"] == []


# ── Tests: GET /api/v1/transactions/ ─────────────────────────────────


@pytest.mark.asyncio
async def test_list_transactions(client: AsyncClient, seeded_db: AsyncSession):
    """GET returns ingested transactions."""
    # Seed one transaction first
    payload = make_txn_payload(external_id="LIST-TEST-001")
    await client.post("/api/v1/transactions/", json=payload, headers=HEADERS)

    resp = await client.get("/api/v1/transactions/", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    ids = [t["external_id"] for t in data["transactions"]]
    assert "LIST-TEST-001" in ids