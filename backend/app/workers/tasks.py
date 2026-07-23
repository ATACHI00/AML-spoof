"""AML Monitor — Celery task definitions.

Async transaction processing and rule detection tasks.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction
from app.services.rule_engine import run_rule_engine
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from a synchronous Celery task context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _get_session() -> AsyncSession:
    """Create a new database session for the Celery worker."""
    from app.database import _get_session_factory

    factory = _get_session_factory()
    return factory()


@celery_app.task(name="process_transaction", bind=True, max_retries=3, default_retry_delay=60)
def process_transaction(self, transaction_id: str) -> dict:
    """Process a single transaction through the rule engine.

    Loads the transaction from the database, runs all active rules against
    it, and creates alerts for any triggered detectors.

    Args:
        transaction_id: UUID of the ingested transaction.

    Returns:
        A dict with processing status and alert count.
    """
    logger.info("Processing transaction %s through rule engine", transaction_id)

    session = _get_session()

    try:

        async def _process():
            # Load transaction
            result = await session.execute(
                select(Transaction).where(Transaction.id == transaction_id)
            )
            transaction = result.scalar_one_or_none()
            if transaction is None:
                logger.error("Transaction %s not found", transaction_id)
                return {
                    "status": "error",
                    "transaction_id": transaction_id,
                    "message": "Transaction not found",
                }

            # Run rule engine
            alerts = await run_rule_engine(session, transaction)
            await session.commit()

            return {
                "status": "completed",
                "transaction_id": transaction_id,
                "alerts_created": len(alerts),
                "alert_ids": [str(a.id) for a in alerts],
            }

        return _run_async(_process())

    except Exception as exc:
        logger.exception("Rule engine failed for transaction %s", transaction_id)
        _run_async(session.rollback())
        raise self.retry(exc=exc)

    finally:
        _run_async(session.close())