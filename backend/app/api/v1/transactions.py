"""AML Monitor — Transaction API endpoints.

Transaction ingestion: single (REST) and batch (CSV).
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import verify_api_key
from app.database import get_db
from app.schemas.transaction import (
    TransactionBatchResponse,
    TransactionCreate,
    TransactionResponse,
)
from app.services.transaction_service import (
    AccountNotFoundError,
    ingest_transaction,
)
from app.workers.tasks import process_transaction

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _build_response(txn) -> TransactionResponse:
    """Convert a Transaction ORM instance to a TransactionResponse."""
    return TransactionResponse(
        id=str(txn.id),
        external_id=txn.external_id,
        source_account_id=str(txn.source_account_id),
        destination_account_id=str(txn.destination_account_id),
        amount=txn.amount,
        currency=txn.currency,
        txn_timestamp=txn.txn_timestamp,
        channel=txn.channel,
        status=txn.status,
        ingested_at=txn.ingested_at,
        created_at=txn.created_at,
    )


@router.post("/", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    payload: TransactionCreate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> TransactionResponse:
    """Ingest a single transaction.

    Idempotent: if ``external_id`` already exists, returns the existing
    record with HTTP 200 (instead of 201).
    """
    try:
        txn, is_new = await ingest_transaction(
            db=db,
            external_id=payload.external_id,
            source_account_number=payload.source_account_number,
            destination_account_number=payload.destination_account_number,
            amount=payload.amount,
            currency=payload.currency,
            txn_timestamp=payload.txn_timestamp,
            channel=payload.channel,
            status=payload.status,
            extra_data=payload.extra_data,
        )
    except AccountNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    # Dispatch async processing (fire-and-forget)
    process_transaction.delay(str(txn.id))

    if not is_new:
        # Idempotency hit — return existing with 200
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=_build_response(txn).model_dump(mode="json"),
            headers={"X-Idempotent": "true"},
        )

    return _build_response(txn)


@router.post("/batch", response_model=TransactionBatchResponse)
async def batch_import(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> TransactionBatchResponse:
    """Import transactions from a CSV file.

    Expected CSV columns (case-insensitive):
        external_id, source_account_number, destination_account_number,
        amount, currency, txn_timestamp[, channel, status, metadata]

    Returns a summary of imported, skipped, and errored rows.
    """
    imported = 0
    skipped = 0
    errors: list[str] = []

    content = await file.read()
    text = content.decode("utf-8-sig")  # handle BOM
    reader = csv.DictReader(io.StringIO(text))

    for row_idx, row in enumerate(reader, start=2):  # 1-based, header=1
        try:
            external_id = row.get("external_id", "").strip()
            if not external_id:
                errors.append(f"Row {row_idx}: missing external_id")
                continue

            source = row.get("source_account_number", "").strip()
            dest = row.get("destination_account_number", "").strip()
            amount_str = row.get("amount", "").strip()
            currency = row.get("currency", "").strip().upper()
            txn_ts_str = row.get("txn_timestamp", "").strip()

            if not all([source, dest, amount_str, currency, txn_ts_str]):
                errors.append(f"Row {row_idx}: missing required field(s)")
                continue

            amount = Decimal(amount_str)
            txn_timestamp = datetime.fromisoformat(txn_ts_str)

            channel = row.get("channel", "").strip() or None
            status_val = row.get("status", "pending").strip()
            extra_data_raw = row.get("extra_data", "").strip()
            extra_data: dict | None = None
            if extra_data_raw:
                import json

                try:
                    extra_data = json.loads(extra_data_raw)
                except json.JSONDecodeError:
                    errors.append(f"Row {row_idx}: invalid JSON in extra_data")
                    continue

            txn, is_new = await ingest_transaction(
                db=db,
                external_id=external_id,
                source_account_number=source,
                destination_account_number=dest,
                amount=amount,
                currency=currency,
                txn_timestamp=txn_timestamp,
                channel=channel,
                status=status_val,
                extra_data=extra_data,
            )

            if is_new:
                imported += 1
                process_transaction.delay(str(txn.id))
            else:
                skipped += 1

        except AccountNotFoundError as exc:
            errors.append(f"Row {row_idx}: {exc}")
        except (ValueError, TypeError) as exc:
            errors.append(f"Row {row_idx}: {exc}")

    return TransactionBatchResponse(imported=imported, skipped=skipped, errors=errors)


# Keep the original list endpoint
@router.get("/")
async def list_transactions(
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key),
) -> dict:
    """List transactions (basic pagination placeholder)."""
    from sqlalchemy import select

    from app.models.transaction import Transaction

    result = await db.execute(select(Transaction).order_by(Transaction.ingested_at.desc()).limit(100))
    txns = result.scalars().all()
    return {
        "transactions": [_build_response(t).model_dump(mode="json") for t in txns],
        "total": len(txns),
    }