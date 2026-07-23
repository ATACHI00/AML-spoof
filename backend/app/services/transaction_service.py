"""AML Monitor — Transaction service.

Business logic for transaction ingestion and processing.
Supports idempotency via external_id and account resolution via account_number.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.transaction import Transaction


class AccountNotFoundError(ValueError):
    """Raised when an account number is not found."""

    def __init__(self, account_number: str) -> None:
        self.account_number = account_number
        super().__init__(f"Account not found: {account_number}")


async def resolve_account(
    db: AsyncSession, account_number: str, field_name: str = "account_number"
) -> Account:
    """Resolve an account number to an Account model instance.

    Args:
        db: Database session.
        account_number: The account number to look up.
        field_name: Human-readable field name for error messages.

    Returns:
        The Account instance.

    Raises:
        AccountNotFoundError: If no account with the given number exists.
    """
    result = await db.execute(
        select(Account).where(Account.account_number == account_number)
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise AccountNotFoundError(account_number)
    return account


async def ingest_transaction(
    db: AsyncSession,
    external_id: str,
    source_account_number: str,
    destination_account_number: str,
    amount: Decimal,
    currency: str,
    txn_timestamp: datetime,
    channel: str | None = None,
    status: str = "pending",
    extra_data: dict | None = None,
) -> tuple[Transaction, bool]:
    """Ingest a single transaction with idempotency check.

    If a transaction with the same ``external_id`` already exists, it is
    returned as-is (HTTP 200).  Otherwise a new transaction is created and
    the caller should commit the session (HTTP 201).

    Args:
        db: Active database session.
        external_id: Client's internal transaction ID (used for idempotency).
        source_account_number: Source account number/IBAN.
        destination_account_number: Destination account number/IBAN.
        amount: Transaction amount (must be > 0).
        currency: ISO 4217 currency code.
        txn_timestamp: When the transaction occurred.
        channel: Transaction channel (wire, ach, card, internal, crypto, …).
        status: Transaction status (default ``pending``).
        extra_data: Arbitrary extra data.

    Returns:
        A tuple of ``(Transaction, is_new)`` where ``is_new`` is ``True``
        when a new record was created and ``False`` when an existing record
        was returned (idempotency hit).

    Raises:
        AccountNotFoundError: If either account number is unknown.
    """
    # --- Idempotency check ---
    result = await db.execute(
        select(Transaction).where(Transaction.external_id == external_id)
    )
    existing: Transaction | None = result.scalar_one_or_none()
    if existing is not None:
        return existing, False

    # --- Resolve account numbers to UUIDs ---
    source = await resolve_account(db, source_account_number, "source_account_number")
    dest = await resolve_account(db, destination_account_number, "destination_account_number")

    # --- Create transaction ---
    transaction = Transaction(
        external_id=external_id,
        source_account_id=source.id,
        destination_account_id=dest.id,
        amount=amount,
        currency=currency,
        txn_timestamp=txn_timestamp,
        channel=channel,
        status=status,
        extra_data=extra_data,
        ingested_at=datetime.now(timezone.utc),
    )
    db.add(transaction)
    await db.flush()
    return transaction, True