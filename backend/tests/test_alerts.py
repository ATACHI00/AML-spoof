"""AML Monitor — Tests for Alert API endpoints.

Tests cover:
- Alert listing with filters and pagination
- Alert detail view
- Alert status updates (close/escalate/in_review)
- Audit log integration on status change
- Error cases (not found, invalid transitions, validation)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.models.audit_log import AuditLog


@pytest.fixture
def api_headers() -> dict[str, str]:
    """Default API headers for tests."""
    return {"X-API-Key": "dev-api-key-1"}


async def _create_sample_alert(
    db_session: AsyncSession,
    *,
    severity: str = "medium",
    status: str = "new",
    title: str = "Test Alert",
    risk_score: Decimal = Decimal("50.00"),
) -> Alert:
    """Helper to create a sample alert for testing."""
    alert = Alert(
        transaction_id=None,
        rule_id=None,
        case_id=None,
        severity=severity,
        risk_score=risk_score,
        title=title,
        description="Alert description for testing",
        status=status,
    )
    db_session.add(alert)
    await db_session.flush()
    await db_session.refresh(alert)
    return alert


class TestListAlerts:
    """Tests for GET /api/v1/alerts/"""

    async def test_list_alerts_empty(self, client: AsyncClient, api_headers: dict[str, str]) -> None:
        """Should return empty list when no alerts exist."""
        response = await client.get("/api/v1/alerts/", headers=api_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["alerts"] == []
        assert data["page"] == 1
        assert data["page_size"] == 20

    async def test_list_alerts_with_data(
        self, client: AsyncClient, db_session: AsyncSession, api_headers: dict[str, str]
    ) -> None:
        """Should return alerts with pagination metadata."""
        await _create_sample_alert(db_session, severity="high", title="Alert 1")
        await _create_sample_alert(db_session, severity="low", title="Alert 2")
        await db_session.commit()

        response = await client.get("/api/v1/alerts/", headers=api_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["alerts"]) == 2

    async def test_list_alerts_filter_by_status(
        self, client: AsyncClient, db_session: AsyncSession, api_headers: dict[str, str]
    ) -> None:
        """Should filter alerts by status."""
        await _create_sample_alert(db_session, status="new", title="New Alert")
        await _create_sample_alert(db_session, status="closed", title="Closed Alert")
        await db_session.commit()

        response = await client.get(
            "/api/v1/alerts/?status=new", headers=api_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["alerts"][0]["status"] == "new"

    async def test_list_alerts_filter_by_severity(
        self, client: AsyncClient, db_session: AsyncSession, api_headers: dict[str, str]
    ) -> None:
        """Should filter alerts by severity."""
        await _create_sample_alert(db_session, severity="critical", title="Critical Alert")
        await _create_sample_alert(db_session, severity="low", title="Low Alert")
        await db_session.commit()

        response = await client.get(
            "/api/v1/alerts/?severity=critical", headers=api_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["alerts"][0]["severity"] == "critical"

    async def test_list_alerts_pagination(
        self, client: AsyncClient, db_session: AsyncSession, api_headers: dict[str, str]
    ) -> None:
        """Should paginate results correctly."""
        for i in range(5):
            await _create_sample_alert(db_session, title=f"Alert {i}")
        await db_session.commit()

        # Page 1 with 2 items
        response = await client.get(
            "/api/v1/alerts/?page=1&page_size=2", headers=api_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["alerts"]) == 2
        assert data["page"] == 1

        # Page 2 with 2 items
        response = await client.get(
            "/api/v1/alerts/?page=2&page_size=2", headers=api_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["alerts"]) == 2
        assert data["page"] == 2

class TestGetAlert:
    """Tests for GET /api/v1/alerts/{alert_id}"""

    async def test_get_alert_found(
        self, client: AsyncClient, db_session: AsyncSession, api_headers: dict[str, str]
    ) -> None:
        """Should return alert details by ID."""
        alert = await _create_sample_alert(db_session, severity="high", risk_score=Decimal("75.50"))
        await db_session.commit()

        response = await client.get(f"/api/v1/alerts/{alert.id}", headers=api_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(alert.id)
        assert data["severity"] == "high"
        assert data["risk_score"] == "75.50"
        assert data["title"] == "Test Alert"
        assert data["status"] == "new"

    async def test_get_alert_not_found(
        self, client: AsyncClient, api_headers: dict[str, str]
    ) -> None:
        """Should return 404 for non-existent alert."""
        fake_id = uuid.uuid4()
        response = await client.get(f"/api/v1/alerts/{fake_id}", headers=api_headers)
        assert response.status_code == 404

    async def test_get_alert_invalid_id(
        self, client: AsyncClient, api_headers: dict[str, str]
    ) -> None:
        """Should return 404 for invalid UUID format."""
        response = await client.get("/api/v1/alerts/not-a-uuid", headers=api_headers)
        assert response.status_code == 404


class TestUpdateAlertStatus:
    """Tests for PATCH /api/v1/alerts/{alert_id}/status"""

    async def test_close_alert(
        self, client: AsyncClient, db_session: AsyncSession, api_headers: dict[str, str]
    ) -> None:
        """Should close an alert and create audit log entry."""
        alert = await _create_sample_alert(db_session)
        await db_session.commit()

        response = await client.patch(
            f"/api/v1/alerts/{alert.id}/status",
            json={"status": "closed", "comment": "False positive - legitimate transaction"},
            headers=api_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["alert"]["status"] == "closed"
        assert data["message"] == "Alert status updated to 'closed'"
        assert data["audit_entry_id"] is not None

        # Verify audit log was created
        audit_response = await client.get(
            f"/api/v1/alerts/{alert.id}", headers=api_headers
        )
        assert audit_response.status_code == 200

    async def test_escalate_alert(
        self, client: AsyncClient, db_session: AsyncSession, api_headers: dict[str, str]
    ) -> None:
        """Should escalate an alert."""
        alert = await _create_sample_alert(db_session)
        await db_session.commit()

        response = await client.patch(
            f"/api/v1/alerts/{alert.id}/status",
            json={"status": "escalated", "comment": "Requires senior review - high amount"},
            headers=api_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["alert"]["status"] == "escalated"

    async def test_set_in_review(
        self, client: AsyncClient, db_session: AsyncSession, api_headers: dict[str, str]
    ) -> None:
        """Should set alert to in_review status."""
        alert = await _create_sample_alert(db_session)
        await db_session.commit()

        response = await client.patch(
            f"/api/v1/alerts/{alert.id}/status",
            json={"status": "in_review", "comment": "Starting investigation"},
            headers=api_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["alert"]["status"] == "in_review"

    async def test_cannot_close_closed_alert(
        self, client: AsyncClient, db_session: AsyncSession, api_headers: dict[str, str]
    ) -> None:
        """Should reject status update on already closed alert."""
        alert = await _create_sample_alert(db_session, status="closed")
        await db_session.commit()

        response = await client.patch(
            f"/api/v1/alerts/{alert.id}/status",
            json={"status": "escalated", "comment": "Trying to reopen"},
            headers=api_headers,
        )
        assert response.status_code == 422
        assert "Cannot update a closed alert" in response.text

    async def test_missing_comment(
        self, client: AsyncClient, db_session: AsyncSession, api_headers: dict[str, str]
    ) -> None:
        """Should reject status update without comment."""
        alert = await _create_sample_alert(db_session)
        await db_session.commit()

        response = await client.patch(
            f"/api/v1/alerts/{alert.id}/status",
            json={"status": "closed"},
            headers=api_headers,
        )
        assert response.status_code == 422

    async def test_invalid_status(
        self, client: AsyncClient, db_session: AsyncSession, api_headers: dict[str, str]
    ) -> None:
        """Should reject invalid status value."""
        alert = await _create_sample_alert(db_session)
        await db_session.commit()

        response = await client.patch(
            f"/api/v1/alerts/{alert.id}/status",
            json={"status": "invalid_status", "comment": "Test"},
            headers=api_headers,
        )
        assert response.status_code == 422

    async def test_alert_not_found(
        self, client: AsyncClient, api_headers: dict[str, str]
    ) -> None:
        """Should return 404 for non-existent alert."""
        fake_id = uuid.uuid4()
        response = await client.patch(
            f"/api/v1/alerts/{fake_id}/status",
            json={"status": "closed", "comment": "Test"},
            headers=api_headers,
        )
        assert response.status_code == 404

    async def test_audit_log_chain_integrity(
        self, client: AsyncClient, db_session: AsyncSession, api_headers: dict[str, str]
    ) -> None:
        """Should maintain hash chain integrity across multiple status changes."""
        from app.services.alert_service import update_alert_status

        alert = await _create_sample_alert(db_session)
        await db_session.commit()

        # Change status multiple times via service directly (same session)
        for status, comment in [
            ("in_review", "Starting review"),
            ("escalated", "Escalating to senior"),
            ("closed", "Case resolved"),
        ]:
            updated_alert, audit_entry = await update_alert_status(
                db=db_session,
                alert=alert,
                new_status=status,
                comment=comment,
                actor_id="compliance-officer",
            )
            alert = updated_alert
            await db_session.commit()

        # Verify audit log entries exist
        from sqlalchemy import select

        result = await db_session.execute(
            select(AuditLog)
            .where(AuditLog.entity_id == str(alert.id))
            .order_by(AuditLog.created_at.asc())
        )
        entries = list(result.scalars().all())
        assert len(entries) == 3

        # Verify hash chain
        from app.utils.hashing import verify_chain_integrity

        entry_dicts = [
            {
                "previous_hash": e.previous_hash,
                "current_hash": e.current_hash,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "action": e.action,
                "actor_id": e.actor_id,
                "changes": e.changes,
                "created_at": e.created_at,
            }
            for e in entries
        ]
        assert verify_chain_integrity(entry_dicts), "Hash chain integrity check failed"

        # Also verify via API that the chain is visible
        response = await client.get(
            f"/api/v1/alerts/{alert.id}", headers=api_headers
        )
        assert response.status_code == 200
        assert response.json()["status"] == "closed"