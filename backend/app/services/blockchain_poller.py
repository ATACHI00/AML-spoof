"""Blockchair API integration for cryptocurrency transaction data."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exchange import Exchange
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)


class BlockchairAPI:
    """Blockchair API client for cryptocurrency data."""

    BASE_URL = "https://api.blockchair.com"

    CHAIN_TO_API = {
        "btc": "bitcoin",
        "eth": "ethereum",
        "usdt_erc20": "ethereum",
        "usdt_trc20": "tron",
        "xmr": "monero",
    }

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(
                headers=headers,
                timeout=30.0,
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get_block_height(self, chain: str) -> int:
        """Get current block height for a chain."""
        chain_name = self.CHAIN_TO_API.get(chain)
        if not chain_name:
            raise ValueError(f"Unsupported chain: {chain}")

        client = await self._get_client()
        response = await client.get(f"{self.BASE_URL}/{chain_name}/stats")
        response.raise_for_status()
        data = response.json()
        return data["data"]["blocks"]

    async def get_blocks(self, chain: str, start: int, end: int) -> list[dict[str, Any]]:
        """Get blocks in a range."""
        chain_name = self.CHAIN_TO_API.get(chain)
        if not chain_name:
            raise ValueError(f"Unsupported chain: {chain}")

        client = await self._get_client()
        response = await client.get(
            f"{self.BASE_URL}/{chain_name}/blocks/{start}-{end}"
        )
        response.raise_for_status()
        return response.json().get("data", {})

    async def get_transactions(self, chain: str, addresses: list[str]) -> list[dict[str, Any]]:
        """Get transactions for addresses."""
        chain_name = self.CHAIN_TO_API.get(chain)
        if not chain_name:
            raise ValueError(f"Unsupported chain: {chain}")

        if not addresses:
            return []

        client = await self._get_client()
        # Blockchair allows comma-separated addresses
        addr_param = ",".join(addresses)
        response = await client.get(
            f"{self.BASE_URL}/{chain_name}/outputs?search_query={addr_param}&limit=100"
        )
        response.raise_for_status()
        data = response.json()
        return data.get("data", [])

    async def get_block(self, chain: str, block_hash: str) -> dict[str, Any]:
        """Get block by hash."""
        chain_name = self.CHAIN_TO_API.get(chain)
        if not chain_name:
            raise ValueError(f"Unsupported chain: {chain}")

        client = await self._get_client()
        response = await client.get(
            f"{self.BASE_URL}/{chain_name}/block/{block_hash}"
        )
        response.raise_for_status()
        return response.json()


async def parse_transaction_from_blockchair(
    chain: str,
    tx_data: dict[str, Any],
    db: AsyncSession,
) -> Transaction | None:
    """Parse Blockchair transaction data into our Transaction model."""
    from app.models.account import Account
    from app.models.client import Client

    if not isinstance(tx_data, dict):
        return None

    # Get address info
    output = tx_data.get("output", {})
    addresses = output.get("addresses", [])

    if not addresses:
        return None

    # Extract amount
    amount = Decimal(str(output.get("value", 0))) / Decimal("100000000")  # satoshis to BTC

    if amount <= 0:
        return None

    # Get timestamps
    timestamp = tx_data.get("timestamp")
    if timestamp:
        # Blockchair returns Unix timestamp
        if isinstance(timestamp, int):
            txn_timestamp = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        else:
            txn_timestamp = datetime.now(timezone.utc)
    else:
        txn_timestamp = datetime.now(timezone.utc)

    # Check if this transaction was already processed
    transaction_id = tx_data.get("hash")
    if not transaction_id:
        return None

    # Try to resolve accounts
    source_account = None
    dest_account = None

    # For now, create accounts on the fly
    for addr in addresses[:2]:  # Take first two addresses
        result = await db.execute(
            select(Account).where(Account.account_number == addr)
        )
        account = result.scalar_one_or_none()
        if account:
            if not source_account:
                source_account = account
            elif not dest_account:
                dest_account = account

    # Create accounts if not found
    if not source_account:
        source_account = Account(
            account_number=addresses[0],
            currency=chain.upper(),
            balance=amount,
            is_active=True,
        )
        db.add(source_account)

    if not dest_account and len(addresses) > 1:
        dest_account = Account(
            account_number=addresses[1],
            currency=chain.upper(),
            is_active=True,
        )
        db.add(dest_account)

    await db.flush()

    # Check for exchange classification
    exchange_info = await classify_exchange(db, chain, addresses)

    # Create extra data with exchange info
    extra_data = {
        "blockchain": chain,
        "transaction_id": transaction_id,
        "block_height": tx_data.get("block_id"),
        "confirmations": tx_data.get("confirmations", 0),
    }
    if exchange_info:
        extra_data["exchange"] = exchange_info

    # Create transaction
    transaction = Transaction(
        external_id=f"{chain}:{transaction_id}",
        source_account_id=source_account.id if source_account else None,
        destination_account_id=dest_account.id if dest_account else None,
        amount=amount,
        currency=chain.upper(),
        txn_timestamp=txn_timestamp,
        channel=f"{chain}_blockchain",
        status="cleared",
        extra_data=extra_data,
        ingested_at=datetime.now(timezone.utc),
    )
    db.add(transaction)

    return transaction


async def classify_exchange(
    db: AsyncSession,
    chain: str,
    addresses: list[str],
) -> dict[str, Any] | None:
    """Classify if transaction involves a known exchange."""
    # Check if any address belongs to a known exchange
    result = await db.execute(
        select(Exchange).where(
            Exchange.is_active == True,  # noqa: E712
            Exchange.is_sanctioned == False,  # noqa: E712
        )
    )
    exchanges = result.scalars().all()

    for exchange in exchanges:
        # Check if any address matches exchange pattern
        if exchange.slug in [addr.lower() for addr in addresses]:
            return {
                "name": exchange.name,
                "slug": exchange.slug,
                "kyc_level": exchange.kyc_level,
                "risk_score": float(exchange.risk_score),
            }

    # Check for known exchange address patterns
    known_exchanges = {
        "binance": {
            "addresses": ["binance", "binance-chains"],
            "kyc_level": "full",
            "risk_score": 15.0,
        },
        "coinbase": {
            "addresses": ["coinbase", "coinbase.com"],
            "kyc_level": "full",
            "risk_score": 10.0,
        },
        "kraken": {
            "addresses": ["kraken"],
            "kyc_level": "full",
            "risk_score": 12.0,
        },
        "tornado_cash": {
            "addresses": ["tornado", "0x0000000000000000000000000000000000000000"],
            "kyc_level": "none",
            "risk_score": 95.0,
        },
    }

    for name, config in known_exchanges.items():
        for pattern in config["addresses"]:
            if any(pattern in addr.lower() for addr in addresses):
                return {
                    "name": name,
                    "slug": name,
                    "kyc_level": config["kyc_level"],
                    "risk_score": config["risk_score"],
                }

    return None


async def poll_blockchain_transactions(
    chain: str,
    db: AsyncSession,
    hours_back: int = 24,
) -> int:
    """Poll blockchain for new transactions, analyze them, and create alerts."""
    from app.services.rule_engine import run_rule_engine
    from app.models.alert import Alert

    api = BlockchairAPI()

    try:
        # Get current block height
        current_height = await api.get_block_height(chain)

        # Get transactions from recent blocks
        transactions = []
        alerts_created = 0

        # Only poll recent blocks to avoid too much data
        # Blockchair API has rate limits - be conservative
        blocks_to_poll = min(5, max(1, current_height - 10))

        for block_num in range(max(1, current_height - blocks_to_poll), current_height + 1):
            try:
                blocks = await api.get_blocks(chain, block_num, block_num)
                for block_hash, block_data in blocks.items():
                    for tx_hash, tx_data in block_data.get("transactions", {}).items():
                        parsed = await parse_transaction_from_blockchair(chain, tx_data, db)
                        if parsed:
                            transactions.append(parsed)
                            # Run rule engine on each transaction to detect patterns
                            try:
                                alerts = await run_rule_engine(db, parsed)
                                await db.flush()
                                alerts_created += len(alerts)
                                logger.info(
                                    f"Transaction {tx_hash[:16]}...: {len(alerts)} alerts"
                                )
                            except Exception as rule_exc:
                                logger.warning(
                                    f"Rule engine failed for txn {tx_hash}: {rule_exc}"
                                )
            except Exception as block_exc:
                logger.warning(f"Error polling block {block_num}: {block_exc}")
                continue

        await db.commit()

        logger.info(
            f"Polled {chain}: found {len(transactions)} transactions, "
            f"{alerts_created} alerts created"
        )
        return len(transactions)

    except Exception as e:
        logger.error(f"Error polling {chain}: {e}")
        await db.rollback()
        return 0
    finally:
        await api.close()


async def check_exchange_transactions(
    db: AsyncSession,
    hours_back: int = 24,
) -> list[dict]:
    """Check transactions involving high-risk exchanges."""
    from app.models.alert import Alert
    from app.models.rule import Rule

    # Find transactions with exchange data
    result = await db.execute(
        select(Transaction).where(
            Transaction.extra_data.isnot(None),
            Transaction.created_at >= datetime.now(timezone.utc) - timedelta(hours=hours_back),
        )
    )
    transactions = result.scalars().all()

    alerts_created = []

    for txn in transactions:
        extra = txn.extra_data or {}
        if not extra.get("exchange"):
            continue

        exchange = extra["exchange"]

        # Check if exchange is high-risk
        if exchange.get("risk_score", 0) >= 50:
            alert = Alert(
                transaction_id=txn.id,
                severity="high",
                risk_score=Decimal(str(exchange["risk_score"])),
                title=f"High-Risk Exchange Transaction",
                description=(
                    f"Transaction involves exchange: {exchange['name']} "
                    f"(KYC: {exchange['kyc_level']}, Risk: {exchange['risk_score']})"
                ),
                status="new",
            )
            db.add(alert)
            alerts_created.append({
                "transaction_id": str(txn.id),
                "title": alert.title,
                "severity": alert.severity,
            })

    if alerts_created:
        await db.flush()

    return alerts_created
