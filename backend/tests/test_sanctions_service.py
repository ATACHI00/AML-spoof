"""Tests for the sanctions screening service."""

from __future__ import annotations

from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sanctions_list import SanctionsList
from app.services.sanctions_service import (
    get_sanctions_stats,
    screen_name_against_sanctions,
    screen_transaction_parties,
    search_sanctions,
)


@pytest_asyncio.fixture
async def sample_sanctions_entries(db_session: AsyncSession) -> list[SanctionsList]:
    """Create sample sanctions list entries for testing."""
    entries = [
        SanctionsList(
            list_source="ofac",
            full_name="OSAMA BIN LADEN",
            name_variations=["USAMA BIN LADIN", "OSAMA BIN LADIN"],
            entity_type="individual",
            country="SA",
            program="SDGT",
            is_active=True,
            last_updated=date.today(),
        ),
        SanctionsList(
            list_source="ofac",
            full_name="EVIL CORP LTD",
            name_variations=None,
            entity_type="entity",
            country="IR",
            program="SDGT",
            is_active=True,
            last_updated=date.today(),
        ),
        SanctionsList(
            list_source="eu",
            full_name="JOHN SMITH",
            name_variations=None,
            entity_type="individual",
            country="GB",
            program="UKRAINE",
            is_active=True,
            last_updated=date.today(),
        ),
        SanctionsList(
            list_source="ofac",
            full_name="INACTIVE ENTRY",
            name_variations=None,
            entity_type="entity",
            country="US",
            program="TEST",
            is_active=False,
            last_updated=date.today(),
        ),
    ]
    for entry in entries:
        db_session.add(entry)
    await db_session.flush()
    return entries


class TestScreenName:
    """Tests for screening a single name against sanctions list."""

    @pytest.mark.asyncio
    async def test_exact_match(
        self, db_session: AsyncSession, sample_sanctions_entries: list[SanctionsList]
    ) -> None:
        result = await screen_name_against_sanctions(
            db=db_session, name="OSAMA BIN LADEN", threshold=0.88
        )
        assert result.triggered
        assert result.severity in ("high", "critical")
        assert result.risk_score > 0
        assert len(result.matches) >= 1
        assert result.matches[0]["full_name"] == "OSAMA BIN LADEN"

    @pytest.mark.asyncio
    async def test_fuzzy_match(
        self, db_session: AsyncSession, sample_sanctions_entries: list[SanctionsList]
    ) -> None:
        """Close name should match via fuzzy logic."""
        result = await screen_name_against_sanctions(
            db=db_session, name="Usama Bin Laden", threshold=0.80
        )
        assert result.triggered
        assert len(result.matches) >= 1

    @pytest.mark.asyncio
    async def test_no_match(
        self, db_session: AsyncSession, sample_sanctions_entries: list[SanctionsList]
    ) -> None:
        result = await screen_name_against_sanctions(
            db=db_session, name="Alice Wonderland", threshold=0.88
        )
        assert not result.triggered
        assert result.matches == []

    @pytest.mark.asyncio
    async def test_inactive_entry_not_matched(
        self, db_session: AsyncSession, sample_sanctions_entries: list[SanctionsList]
    ) -> None:
        """Inactive sanctions entries should not trigger matches."""
        result = await screen_name_against_sanctions(
            db=db_session, name="INACTIVE ENTRY", threshold=0.88
        )
        assert not result.triggered

    @pytest.mark.asyncio
    async def test_empty_sanctions_list(self, db_session: AsyncSession) -> None:
        """Empty list should not trigger."""
        result = await screen_name_against_sanctions(
            db=db_session, name="ANY NAME", threshold=0.88
        )
        assert not result.triggered

    @pytest.mark.asyncio
    async def test_match_with_variations(
        self, db_session: AsyncSession, sample_sanctions_entries: list[SanctionsList]
    ) -> None:
        """Name matching should check variations/aliases."""
        result = await screen_name_against_sanctions(
            db=db_session, name="USAMA BIN LADIN", threshold=0.95
        )
        assert result.triggered
        assert result.matches[0]["full_name"] == "OSAMA BIN LADEN"

    @pytest.mark.asyncio
    async def test_levenshtein_method(
        self, db_session: AsyncSession, sample_sanctions_entries: list[SanctionsList]
    ) -> None:
        result = await screen_name_against_sanctions(
            db=db_session,
            name="OSAMA BIN LADEN",
            threshold=0.88,
            method="levenshtein",
        )
        assert result.triggered


class TestScreenTransactionParties:
    """Tests for screening transaction parties."""

    @pytest.mark.asyncio
    async def test_source_match(
        self, db_session: AsyncSession, sample_sanctions_entries: list[SanctionsList]
    ) -> None:
        result = await screen_transaction_parties(
            db=db_session,
            source_name="OSAMA BIN LADEN",
            destination_name=None,
            threshold=0.88,
        )
        assert result.triggered
        assert result.matches[0]["role"] == "source"

    @pytest.mark.asyncio
    async def test_destination_match(
        self, db_session: AsyncSession, sample_sanctions_entries: list[SanctionsList]
    ) -> None:
        result = await screen_transaction_parties(
            db=db_session,
            source_name=None,
            destination_name="EVIL CORP LTD",
            threshold=0.88,
        )
        assert result.triggered
        assert result.matches[0]["role"] == "destination"

    @pytest.mark.asyncio
    async def test_both_match(
        self, db_session: AsyncSession, sample_sanctions_entries: list[SanctionsList]
    ) -> None:
        result = await screen_transaction_parties(
            db=db_session,
            source_name="OSAMA BIN LADEN",
            destination_name="EVIL CORP LTD",
            threshold=0.88,
        )
        assert result.triggered
        assert len(result.matches) >= 1

    @pytest.mark.asyncio
    async def test_no_names_provided(
        self, db_session: AsyncSession, sample_sanctions_entries: list[SanctionsList]
    ) -> None:
        result = await screen_transaction_parties(
            db=db_session,
            source_name=None,
            destination_name=None,
            threshold=0.88,
        )
        assert not result.triggered

    @pytest.mark.asyncio
    async def test_no_match_clean_names(
        self, db_session: AsyncSession, sample_sanctions_entries: list[SanctionsList]
    ) -> None:
        result = await screen_transaction_parties(
            db=db_session,
            source_name="Alice Wonderland",
            destination_name="Bob Smith",
            threshold=0.88,
        )
        assert not result.triggered


class TestSanctionsStats:
    """Tests for sanctions list statistics."""

    @pytest.mark.asyncio
    async def test_stats(
        self, db_session: AsyncSession, sample_sanctions_entries: list[SanctionsList]
    ) -> None:
        stats = await get_sanctions_stats(db=db_session)
        assert stats["total"] == 4
        assert stats["by_source"]["ofac"] == 3
        assert stats["by_source"]["eu"] == 1
        assert stats["by_type"]["individual"] == 2
        assert stats["by_type"]["entity"] == 2

    @pytest.mark.asyncio
    async def test_stats_empty(self, db_session: AsyncSession) -> None:
        stats = await get_sanctions_stats(db=db_session)
        assert stats["total"] == 0
        assert stats["by_source"] == {}
        assert stats["by_type"] == {}


class TestSearchSanctions:
    """Tests for searching sanctions list."""

    @pytest.mark.asyncio
    async def test_search_by_name(
        self, db_session: AsyncSession, sample_sanctions_entries: list[SanctionsList]
    ) -> None:
        entries, total = await search_sanctions(db=db_session, query="OSAMA")
        assert total == 1
        assert entries[0].full_name == "OSAMA BIN LADEN"

    @pytest.mark.asyncio
    async def test_search_partial(
        self, db_session: AsyncSession, sample_sanctions_entries: list[SanctionsList]
    ) -> None:
        entries, total = await search_sanctions(db=db_session, query="BIN")
        assert total == 1

    @pytest.mark.asyncio
    async def test_search_no_results(
        self, db_session: AsyncSession, sample_sanctions_entries: list[SanctionsList]
    ) -> None:
        entries, total = await search_sanctions(db=db_session, query="NONEXISTENT")
        assert total == 0
        assert entries == []

    @pytest.mark.asyncio
    async def test_search_pagination(
        self, db_session: AsyncSession, sample_sanctions_entries: list[SanctionsList]
    ) -> None:
        entries, total = await search_sanctions(
            db=db_session, query="", limit=2, offset=0
        )
        assert total == 4
        assert len(entries) == 2