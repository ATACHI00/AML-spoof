"""AML Monitor — Transaction schemas.

Pydantic models for transaction request/response validation.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class TransactionCreate(BaseModel):
    """Schema for creating a new transaction."""

    external_id: str = Field(..., description="Client's internal transaction ID")
    source_account_number: str = Field(..., description="Source account number/IBAN")
    destination_account_number: str = Field(..., description="Destination account number/IBAN")
    amount: Decimal = Field(..., gt=0, description="Transaction amount")
    currency: str = Field(..., min_length=3, max_length=3, description="ISO 4217 currency code")
    txn_timestamp: datetime = Field(..., description="When the transaction occurred")
    channel: str | None = Field(None, description="Transaction channel")
    status: str = Field("pending", description="Transaction status")
    extra_data: dict | None = Field(None, description="Extra data")


class TransactionResponse(BaseModel):
    """Schema for transaction response."""

    id: str
    external_id: str
    source_account_id: str
    destination_account_id: str
    amount: Decimal
    currency: str
    txn_timestamp: datetime
    channel: str | None
    status: str
    ingested_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class TransactionBatchResponse(BaseModel):
    """Schema for batch import response."""

    imported: int
    skipped: int
    errors: list[str]