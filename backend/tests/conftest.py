"""AML Monitor — Pytest fixtures.

Provides async test client, test database session, and sample data.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Override database URL before any app imports to ensure lazy engine
# picks up the test URL instead of the default PostgreSQL one.
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_aml.db"
os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)

from app.database import get_db
from app.main import app
from app.models import Base, Client, Account, Transaction, Rule, SanctionsList


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Create a test engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_tables(engine):
    """Clean all tables before each test to ensure test isolation."""
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh test database session."""
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
        await session.close()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create a test HTTP client with overridden DB dependency."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def sample_client(db_session: AsyncSession) -> Client:
    """Create a sample client for testing."""
    client = Client(
        external_id="CLIENT-001",
        name="Test Client Ltd",
        client_type="legal_entity",
        risk_score=Decimal("15.00"),
    )
    db_session.add(client)
    await db_session.flush()
    return client


@pytest_asyncio.fixture
async def sample_account(db_session: AsyncSession, sample_client: Client) -> Account:
    """Create a sample account for testing."""
    account = Account(
        client_id=sample_client.id,
        account_number="GB29NWBK60161331926819",
        currency="GBP",
        balance=Decimal("10000.00"),
    )
    db_session.add(account)
    await db_session.flush()
    return account


@pytest_asyncio.fixture
async def sample_rule(db_session: AsyncSession) -> Rule:
    """Create a sample rule for testing."""
    rule = Rule(
        name="Structuring Detection",
        slug="structuring",
        description="Detects smurfing patterns below reporting threshold",
        detector_type="structuring",
        config={
            "threshold_amount": 9999.99,
            "time_window_minutes": 1440,
            "min_transactions": 3,
        },
        weight=Decimal("1.00"),
        is_active=True,
    )
    db_session.add(rule)
    await db_session.flush()
    return rule