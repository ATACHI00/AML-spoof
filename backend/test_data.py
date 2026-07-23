"""Test data setup script."""
import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import _get_session_factory
from app.models.account import Account
from app.models.client import Client
from app.models.transaction import Transaction


async def setup_test_data():
    """Create test clients, accounts and transactions."""
    session_factory = _get_session_factory()

    async with session_factory() as session:
        # Create test clients
        client1 = Client(
            id=uuid.uuid4(),
            external_id="client-001",
            name="John Smith Trading Ltd",
            client_type="legal_entity",
            is_sanctioned=False,
        )
        session.add(client1)

        client2 = Client(
            id=uuid.uuid4(),
            external_id="client-002",
            name="Jane Doe Holdings",
            client_type="legal_entity",
            is_sanctioned=False,
        )
        session.add(client2)

        await session.flush()

        # Create accounts
        account1 = Account(
            id=uuid.uuid4(),
            client_id=client1.id,
            account_number="ACC001",
            currency="USD",
            balance=100000,
            is_active=True,
        )
        session.add(account1)

        account2 = Account(
            id=uuid.uuid4(),
            client_id=client2.id,
            account_number="ACC002",
            currency="USD",
            balance=50000,
            is_active=True,
        )
        session.add(account2)

        await session.flush()

        # Create transactions
        now = datetime.now(timezone.utc)

        # Normal transaction
        txn1 = Transaction(
            id=uuid.uuid4(),
            external_id="txn-normal-001",
            source_account_id=account1.id,
            destination_account_id=account2.id,
            amount=5000,
            currency="USD",
            txn_timestamp=now,
            channel="wire",
            status="cleared",
            ingested_at=now,
        )
        session.add(txn1)

        # Structuring test - multiple small transactions
        for i in range(5):
            txn = Transaction(
                id=uuid.uuid4(),
                external_id=f"txn-struct-{i}",
                source_account_id=account1.id,
                destination_account_id=account2.id,
                amount=8000,  # Just below 9999 threshold
                currency="USD",
                txn_timestamp=now,
                channel="wire",
                status="cleared",
                ingested_at=now,
            )
            session.add(txn)

        # Round amount test
        txn_round = Transaction(
            id=uuid.uuid4(),
            external_id="txn-round-001",
            source_account_id=account1.id,
            destination_account_id=account2.id,
            amount=10000,  # Round number
            currency="USD",
            txn_timestamp=now,
            channel="crypto",  # High risk channel
            status="cleared",
            ingested_at=now,
        )
        session.add(txn_round)

        await session.commit()

        print("Test data created successfully!")
        print(f"  - Clients: {client1.name}, {client2.name}")
        print(f"  - Accounts: ACC001, ACC002")
        print(f"  - Transactions: normal, 5 structuring, 1 round")


if __name__ == "__main__":
    asyncio.run(setup_test_data())
