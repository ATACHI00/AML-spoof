"""AML Monitor — Blockchain poller Celery tasks.

Periodic tasks for scanning BTC, ETH, USDT, XMR blockchains
and creating AML alerts for suspicious transactions.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List

from app.workers.celery_app import celery_app
from app.models.transaction import Transaction
from app.models.alert import Alert
from app.models.account import Account
from app.models.client import Client
from app.services.blockchain_client import (
    BitcoinClient,
    EthereumClient,
    USDTClient,
    MoneroClient,
)
from app.services.rule_engine import run_rule_engine
from sqlalchemy import select, func

logger = logging.getLogger(__name__)


def _get_client_class(chain: str):
    """Get the appropriate blockchain client for a chain."""
    clients = {
        "btc": BitcoinClient,
        "eth": EthereumClient,
        "usdt": USDTClient,
        "xmr": MoneroClient,
    }
    return clients.get(chain)


async def _process_blockchain_transactions(
    chain: str,
    get_transactions_func,
    limit: int = 50,
) -> Dict[str, Any]:
    """Common function to poll blockchain and process transactions."""
    from app.database import _get_session_factory

    factory = _get_session_factory()
    session = factory()

    try:
        client_class = _get_client_class(chain)
        if not client_class:
            return {"chain": chain, "status": "error", "message": "Unknown chain"}

        client = client_class()

        # Get recent transactions
        transactions = await get_transactions_func(client, limit)

        transactions_ingested = 0
        alerts_created = []

        for tx in transactions:
            # Check if transaction already exists
            txid = tx.get("txid") or tx.get("hash") or tx.get("txID")
            if not txid:
                continue

            # Check for duplicate (async)
            result = await session.execute(
                select(Transaction).where(Transaction.external_id == txid)
            )
            existing = result.scalar_one_or_none()

            if existing:
                continue

            # Extract transaction details
            amount = tx.get("amount") or "0"
            if isinstance(amount, str):
                try:
                    amount = Decimal(amount)
                except:
                    amount = Decimal("0")

            from_address = tx.get("from_address") or tx.get("from") or ""
            to_address = tx.get("to_address") or tx.get("to") or ""

            # For Bitcoin, extract addresses from vin/vout if not in top-level fields
            if not from_address and chain == "btc":
                vin = tx.get("vin", [])
                if vin:
                    for v in vin:
                        if v.get("prevout") and v["prevout"].get("scriptpubkey_address"):
                            from_address = v["prevout"]["scriptpubkey_address"]
                            break
                        elif v.get("coinbase"):
                            # Coinbase transaction - no source address (minted coins)
                            from_address = "coinbase"
                            break

            if not to_address and chain == "btc":
                vout = tx.get("vout", [])
                if vout:
                    for v in vout:
                        if v.get("scriptpubkey_address"):
                            to_address = v["scriptpubkey_address"]
                            break

            block_number = tx.get("block_number") or tx.get("block_height") or 0
            timestamp = tx.get("timestamp") or 0
            if isinstance(timestamp, int) and timestamp > 1e10:  # ms to seconds
                timestamp = timestamp // 1000

            # Create client for source (if available)
            source_client = None
            if from_address:
                result = await session.execute(
                    select(Client).where(Client.external_id == from_address[:20])
                )
                source_client = result.scalar_one_or_none()
                if not source_client:
                    source_client = Client(
                        external_id=from_address[:20],
                        name=f"Blockchain Source: {from_address[:30]}",
                        client_type="external",
                        risk_score=Decimal("25.00"),
                    )
                    session.add(source_client)
                    await session.flush()

            # Create account for source
            source_account = None
            if source_client:
                result = await session.execute(
                    select(Account).where(Account.account_number == from_address[:32])
                )
                source_account = result.scalar_one_or_none()
                if not source_account:
                    source_account = Account(
                        client_id=source_client.id,
                        account_number=from_address[:32],
                        currency="CRYPTO",
                        balance=Decimal("0.00"),
                    )
                    session.add(source_account)
                    await session.flush()

            # Create client for destination (if available)
            dest_client = None
            if to_address:
                result = await session.execute(
                    select(Client).where(Client.external_id == to_address[:20])
                )
                dest_client = result.scalar_one_or_none()
                if not dest_client:
                    dest_client = Client(
                        external_id=to_address[:20],
                        name=f"Blockchain Destination: {to_address[:30]}",
                        client_type="external",
                        risk_score=Decimal("30.00"),
                    )
                    session.add(dest_client)
                    await session.flush()

            # Create account for destination
            dest_account = None
            if dest_client:
                result = await session.execute(
                    select(Account).where(Account.account_number == to_address[:32])
                )
                dest_account = result.scalar_one_or_none()
                if not dest_account:
                    dest_account = Account(
                        client_id=dest_client.id,
                        account_number=to_address[:32],
                        currency="CRYPTO",
                        balance=Decimal("0.00"),
                    )
                    session.add(dest_account)
                    await session.flush()

            # Create transaction record
            txn = Transaction(
                external_id=txid,
                source_account_id=source_account.id if source_account else None,
                destination_account_id=dest_account.id if dest_account else None,
                amount=amount,
                currency="CRYPTO",
                txn_timestamp=datetime.fromtimestamp(timestamp, tz=timezone.utc) if timestamp else datetime.now(timezone.utc),
                channel="crypto",
                status="cleared",
                ingested_at=datetime.now(timezone.utc),
                extra_data={
                    "chain": chain,
                    "block_number": block_number,
                    "from_address": from_address,
                    "to_address": to_address,
                    "tx_type": tx.get("tx_type", "transfer"),
                },
            )
            session.add(txn)
            await session.flush()

            # Run rule engine for AML detection
            alerts = await run_rule_engine(session, txn)
            await session.commit()

            if alerts:
                for alert in alerts:
                    alerts_created.append({
                        "transaction_id": str(txn.id),
                        "alert_id": str(alert.id),
                        "rule": alert.title,
                        "severity": alert.severity,
                    })

            transactions_ingested += 1

        await client.close()

        logger.info(
            f"Blockchain poll completed: {chain} - "
            f"{transactions_ingested} transactions ingested, "
            f"{len(alerts_created)} alerts created"
        )

        return {
            "chain": chain,
            "transactions_ingested": transactions_ingested,
            "alerts_created": len(alerts_created),
            "alerts": alerts_created[:10],  # First 10 alerts for logging
            "status": "success",
        }

    except Exception as exc:
        logger.exception(f"Blockchain poll failed for {chain}")
        await session.rollback()
        raise self.retry(exc=exc, countdown=60) if hasattr(self, "retry") else exc
    finally:
        await session.close()


# ===========================================================================
# Individual chain polling tasks
# ===========================================================================

@celery_app.task(name="app.workers.blockchain_poller.poll_bitcoin_chain", bind=True, max_retries=3)
async def poll_bitcoin_chain(self):
    """Poll Bitcoin blockchain for new transactions and analyze for AML."""
    logger.info("Starting Bitcoin chain poll")

    async def get_transactions(client: BitcoinClient, limit: int):
        return await client.get_block_transactions(limit=limit)

    return await _process_blockchain_transactions("btc", get_transactions, limit=50)


@celery_app.task(name="app.workers.blockchain_poller.poll_ethereum_chain", bind=True, max_retries=3)
async def poll_ethereum_chain(self):
    """Poll Ethereum blockchain for new transactions and analyze for AML."""
    logger.info("Starting Ethereum chain poll")

    async def get_transactions(client: EthereumClient, limit: int):
        return await client.get_latest_transactions(limit=limit)

    return await _process_blockchain_transactions("eth", get_transactions, limit=50)


@celery_app.task(name="app.workers.blockchain_poller.poll_usdt_chain", bind=True, max_retries=3)
async def poll_usdt_chain(self):
    """Poll USDT (ERC20/TRC20) transactions and analyze for AML."""
    logger.info("Starting USDT chain poll")

    async def get_transactions(client: USDTClient, limit: int):
        return await client.get_recent_transactions(limit=limit)

    return await _process_blockchain_transactions("usdt", get_transactions, limit=50)


@celery_app.task(name="app.workers.blockchain_poller.poll_monero_chain", bind=True, max_retries=3)
async def poll_monero_chain(self):
    """Poll Monero blockchain for new transactions and analyze for AML."""
    logger.info("Starting Monero chain poll")

    async def get_transactions(client: MoneroClient, limit: int):
        return await client.get_recent_transactions(limit=limit)

    return await _process_blockchain_transactions("xmr", get_transactions, limit=50)


# ===========================================================================
# High-risk exchange checking
# ===========================================================================

@celery_app.task(name="app.workers.blockchain_poller.check_high_risk_exchanges", bind=True, max_retries=3)
def check_high_risk_exchanges(self):
    """Check for high-risk exchange transactions and create alerts."""
    from app.database import _get_session_factory

    factory = _get_session_factory()
    session = factory()

    try:
        now = datetime.now(timezone.utc)
        hours_back = 24

        # Get transactions with exchange data
        transactions = session.query(Transaction).filter(
            Transaction.extra_data.isnot(None),
            Transaction.created_at >= now - timedelta(hours=hours_back),
        ).all()

        alerts_created = []

        for txn in transactions:
            extra = txn.extra_data or {}
            exchange = extra.get("exchange")

            if not exchange:
                continue

            risk_score = exchange.get("risk_score", 0)
            if risk_score >= 50:
                alert = Alert(
                    transaction_id=txn.id,
                    rule_id=extra.get("rule_id"),
                    severity="high" if risk_score >= 75 else "medium",
                    risk_score=Decimal(str(risk_score)),
                    title="High-Risk Exchange Transaction",
                    description=(
                        f"Transaction involves exchange: {exchange.get('name', 'unknown')} "
                        f"(KYC: {exchange.get('kyc_level', 'unknown')}, Risk: {risk_score})"
                    ),
                    status="new",
                )
                session.add(alert)
                alerts_created.append({
                    "transaction_id": str(txn.id),
                    "title": "High-Risk Exchange",
                    "severity": alert.severity,
                })

        session.commit()

        logger.info(f"High-risk exchange check: {len(alerts_created)} alerts created")
        return {"alerts_created": len(alerts_created)}

    except Exception as exc:
        logger.exception("High-risk exchange check failed")
        session.rollback()
        raise self.retry(exc=exc, countdown=60)
    finally:
        session.close()


# ===========================================================================
# Daily risk summary
# ===========================================================================

@celery_app.task(name="app.workers.blockchain_poller.daily_risk_summary", bind=True)
def daily_risk_summary(self):
    """Generate daily risk summary report."""
    from app.database import _get_session_factory
    from sqlalchemy import func

    factory = _get_session_factory()
    session = factory()

    try:
        now = datetime.now(timezone.utc)
        hours_back = 24

        # Alerts by severity
        severity_counts = session.query(
            Alert.severity,
            func.count(Alert.id)
        ).filter(
            Alert.created_at >= now - timedelta(hours=hours_back)
        ).group_by(Alert.severity).all()

        alerts_by_severity = {row[0]: row[1] for row in severity_counts}

        # Total transactions processed
        total_transactions = session.query(func.count(Transaction.id)).filter(
            Transaction.created_at >= now - timedelta(hours=hours_back)
        ).scalar() or 0

        # High-risk count
        high_risk_count = session.query(func.count(Alert.id)).filter(
            Alert.severity.in_(["high", "critical"]),
            Alert.created_at >= now - timedelta(hours=hours_back)
        ).scalar() or 0

        result = {
            "period": "24h",
            "total_transactions": total_transactions,
            "alerts_by_severity": alerts_by_severity,
            "high_risk_count": high_risk_count,
            "generated_at": now.isoformat(),
        }

        logger.info(
            f"Daily risk summary: {result['total_transactions']} txns, "
            f"{result['high_risk_count']} high-risk alerts"
        )
        return result

    except Exception as exc:
        logger.exception("Daily risk summary failed")
        raise self.retry(exc=exc, countdown=300)
    finally:
        session.close()
