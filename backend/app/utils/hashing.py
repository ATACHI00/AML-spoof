"""AML Monitor — Hash chain utilities for audit log tamper evidence.

Each audit log entry stores:
- previous_hash: SHA-256 of the previous row's current_hash
- current_hash: SHA-256 of (previous_hash + entity_type + entity_id + action + actor_id + changes + created_at)

This makes tampering detectable: changing any row breaks the chain.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone


def _normalize_datetime(dt: datetime) -> str:
    """Normalize a datetime to a consistent UTC ISO format string.

    - If the datetime is naive (no timezone), assume UTC.
    - If the datetime is timezone-aware, convert to UTC.
    - Always produce the same string format regardless of input type.
    """
    if dt.tzinfo is None:
        # Naive datetime — assume UTC and add Z suffix
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond:06d}Z"
    else:
        # Aware datetime — convert to UTC
        dt_utc = dt.astimezone(timezone.utc)
        return dt_utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt_utc.microsecond:06d}Z"


def compute_audit_hash(
    previous_hash: str | None,
    entity_type: str,
    entity_id: str,
    action: str,
    actor_id: str,
    changes: dict | None,
    created_at: datetime | str,
) -> str:
    """Compute SHA-256 hash for an audit log entry.

    Args:
        previous_hash: Hash of the previous audit log entry (None for first entry).
        entity_type: Type of entity (alert, case, rule, etc.).
        entity_id: UUID of the entity.
        action: Action performed.
        actor_id: Who performed the action.
        changes: Before/after diff as dict.
        created_at: Timestamp of the entry.

    Returns:
        SHA-256 hex digest.
    """
    prev = previous_hash or ""
    changes_json = json.dumps(changes, sort_keys=True, default=str) if changes else "{}"

    if isinstance(created_at, datetime):
        created = _normalize_datetime(created_at)
    else:
        created = str(created_at)

    raw = f"{prev}|{entity_type}|{entity_id}|{action}|{actor_id}|{changes_json}|{created}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_chain_integrity(audit_entries: list[dict]) -> bool:
    """Verify the integrity of an audit log hash chain.

    Args:
        audit_entries: List of audit log dicts with 'previous_hash', 'current_hash',
                      'entity_type', 'entity_id', 'action', 'actor_id', 'changes', 'created_at'.

    Returns:
        True if the chain is intact, False if tampering is detected.
    """
    for i, entry in enumerate(audit_entries):
        # Verify the hash matches
        expected_hash = compute_audit_hash(
            previous_hash=entry.get("previous_hash"),
            entity_type=entry["entity_type"],
            entity_id=str(entry["entity_id"]),
            action=entry["action"],
            actor_id=entry["actor_id"],
            changes=entry.get("changes"),
            created_at=entry["created_at"],
        )
        if expected_hash != entry["current_hash"]:
            return False

        # Verify the chain link
        if i > 0:
            if entry["previous_hash"] != audit_entries[i - 1]["current_hash"]:
                return False

    return True