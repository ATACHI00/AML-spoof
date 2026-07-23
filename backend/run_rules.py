"""Run rule engine manually for all transactions."""
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import _get_session_factory
from app.models.transaction import Transaction
from app.services.rule_engine import run_rule_engine


async def run_rule_engine_for_all():
    """Run rule engine for all transactions."""
    session_factory = _get_session_factory()

    async with session_factory() as session:
        result = await session.execute(
            select(Transaction).order_by(Transaction.ingested_at.desc())
        )
        transactions = list(result.scalars().all())

        print(f"Found {len(transactions)} transactions")

        alerts_count = 0
        for txn in transactions:
            print(f"\nProcessing: {txn.external_id} ({txn.amount} {txn.currency})")

            alerts = await run_rule_engine(session, txn)
            await session.commit()

            if alerts:
                alerts_count += len(alerts)
                for alert in alerts:
                    print(f"  ALERT: {alert.title} (severity: {alert.severity}, score: {alert.risk_score})")
            else:
                print(f"  No alerts")

        print(f"\n\nTotal alerts created: {alerts_count}")


if __name__ == "__main__":
    asyncio.run(run_rule_engine_for_all())
