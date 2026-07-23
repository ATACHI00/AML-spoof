"""AML Monitor — Hash chain integrity tests.

Tests for the audit log tamper-evidence mechanism.
"""

from __future__ import annotations

from app.utils.hashing import compute_audit_hash, verify_chain_integrity


def test_compute_hash_consistency():
    """Test that the same inputs produce the same hash."""
    hash1 = compute_audit_hash(
        previous_hash=None,
        entity_type="alert",
        entity_id="00000000-0000-0000-0000-000000000001",
        action="created",
        actor_id="system",
        changes={"status": {"from": None, "to": "new"}},
        created_at="2026-07-22T00:00:00+00:00",
    )
    hash2 = compute_audit_hash(
        previous_hash=None,
        entity_type="alert",
        entity_id="00000000-0000-0000-0000-000000000001",
        action="created",
        actor_id="system",
        changes={"status": {"from": None, "to": "new"}},
        created_at="2026-07-22T00:00:00+00:00",
    )
    assert hash1 == hash2


def test_different_inputs_produce_different_hashes():
    """Test that different inputs produce different hashes."""
    hash1 = compute_audit_hash(
        previous_hash=None,
        entity_type="alert",
        entity_id="00000000-0000-0000-0000-000000000001",
        action="created",
        actor_id="system",
        changes=None,
        created_at="2026-07-22T00:00:00+00:00",
    )
    hash2 = compute_audit_hash(
        previous_hash=None,
        entity_type="case",
        entity_id="00000000-0000-0000-0000-000000000001",
        action="created",
        actor_id="system",
        changes=None,
        created_at="2026-07-22T00:00:00+00:00",
    )
    assert hash1 != hash2


def test_chain_integrity_valid():
    """Test that a valid chain passes verification."""
    entries = [
        {
            "previous_hash": None,
            "current_hash": compute_audit_hash(
                previous_hash=None,
                entity_type="alert",
                entity_id="00000000-0000-0000-0000-000000000001",
                action="created",
                actor_id="system",
                changes={"status": {"from": None, "to": "new"}},
                created_at="2026-07-22T00:00:00+00:00",
            ),
            "entity_type": "alert",
            "entity_id": "00000000-0000-0000-0000-000000000001",
            "action": "created",
            "actor_id": "system",
            "changes": {"status": {"from": None, "to": "new"}},
            "created_at": "2026-07-22T00:00:00+00:00",
        },
    ]

    # Second entry links to first
    prev_hash = entries[0]["current_hash"]
    entries.append(
        {
            "previous_hash": prev_hash,
            "current_hash": compute_audit_hash(
                previous_hash=prev_hash,
                entity_type="alert",
                entity_id="00000000-0000-0000-0000-000000000001",
                action="updated",
                actor_id="compliance-officer-1",
                changes={"status": {"from": "new", "to": "in_review"}},
                created_at="2026-07-22T01:00:00+00:00",
            ),
            "entity_type": "alert",
            "entity_id": "00000000-0000-0000-0000-000000000001",
            "action": "updated",
            "actor_id": "compliance-officer-1",
            "changes": {"status": {"from": "new", "to": "in_review"}},
            "created_at": "2026-07-22T01:00:00+00:00",
        },
    )

    assert verify_chain_integrity(entries) is True


def test_chain_integrity_tampered():
    """Test that a tampered chain fails verification."""
    entries = [
        {
            "previous_hash": None,
            "current_hash": compute_audit_hash(
                previous_hash=None,
                entity_type="alert",
                entity_id="00000000-0000-0000-0000-000000000001",
                action="created",
                actor_id="system",
                changes={"status": {"from": None, "to": "new"}},
                created_at="2026-07-22T00:00:00+00:00",
            ),
            "entity_type": "alert",
            "entity_id": "00000000-0000-0000-0000-000000000001",
            "action": "created",
            "actor_id": "system",
            "changes": {"status": {"from": None, "to": "new"}},
            "created_at": "2026-07-22T00:00:00+00:00",
        },
    ]

    prev_hash = entries[0]["current_hash"]
    entries.append(
        {
            "previous_hash": prev_hash,
            "current_hash": compute_audit_hash(
                previous_hash=prev_hash,
                entity_type="alert",
                entity_id="00000000-0000-0000-0000-000000000001",
                action="updated",
                actor_id="compliance-officer-1",
                changes={"status": {"from": "new", "to": "in_review"}},
                created_at="2026-07-22T01:00:00+00:00",
            ),
            "entity_type": "alert",
            "entity_id": "00000000-0000-0000-0000-000000000001",
            "action": "updated",
            "actor_id": "compliance-officer-1",
            "changes": {"status": {"from": "new", "to": "in_review"}},
            "created_at": "2026-07-22T01:00:00+00:00",
        },
    )

    # Tamper: change the action in the first entry
    tampered_entries = entries.copy()
    tampered_entries[0]["action"] = "deleted"

    assert verify_chain_integrity(tampered_entries) is False


def test_chain_integrity_broken_link():
    """Test that a broken chain link fails verification."""
    entries = [
        {
            "previous_hash": None,
            "current_hash": "some-fake-hash",
            "entity_type": "alert",
            "entity_id": "00000000-0000-0000-0000-000000000001",
            "action": "created",
            "actor_id": "system",
            "changes": None,
            "created_at": "2026-07-22T00:00:00+00:00",
        },
    ]
    assert verify_chain_integrity(entries) is False