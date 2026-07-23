"""Initial schema — all models

Revision ID: 0001
Revises:
Create Date: 2026-07-22 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create ENUM types (PostgreSQL specific, will be skipped for SQLite)
    try:
        sa.Enum("individual", "legal_entity", name="client_type").create(op.get_bind())
        sa.Enum("pending", "cleared", "failed", "reversed", name="txn_status").create(op.get_bind())
        sa.Enum("low", "medium", "high", "critical", name="alert_severity").create(op.get_bind())
        sa.Enum("new", "in_review", "escalated", "closed", name="alert_status").create(op.get_bind())
        sa.Enum("open", "in_review", "closed", "escalated", name="case_status").create(op.get_bind())
        sa.Enum(
            "structuring", "rapid_movement", "round_amount",
            "velocity", "geographic", "dormant", "ml_anomaly",
            name="detector_type",
        ).create(op.get_bind())
        sa.Enum("ofac", "eu", "un", name="sanctions_source").create(op.get_bind())
        sa.Enum("individual", "entity", name="sanctions_entity_type").create(op.get_bind())
    except Exception:
        # SQLite doesn't support ENUMs, skip
        pass

    # clients
    op.create_table(
        "clients",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("external_id", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("client_type", sa.String(16), nullable=False),
        sa.Column("risk_score", sa.Numeric(5, 2), default=0.00),
        sa.Column("is_sanctioned", sa.Boolean(), default=False, nullable=False),
    )

    # accounts
    op.create_table(
        "accounts",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("client_id", sa.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False, index=True),
        sa.Column("account_number", sa.String(128), unique=True, nullable=False, index=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("balance", sa.Numeric(18, 2), default=0.00),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
    )

    # transactions
    op.create_table(
        "transactions",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("external_id", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("source_account_id", sa.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False, index=True),
        sa.Column("destination_account_id", sa.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False, index=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("txn_timestamp", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("channel", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, default="pending"),
        sa.Column("extra_data", sa.JSON(), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
    )

    # rules
    op.create_table(
        "rules",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(128), unique=True, nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("detector_type", sa.String(64), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False, default=dict),
        sa.Column("weight", sa.Numeric(5, 2), default=1.00),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
    )

    # cases
    op.create_table(
        "cases",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, default="open"),
        sa.Column("assigned_to", sa.String(255), nullable=True),
    )

    # alerts
    op.create_table(
        "alerts",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("transaction_id", sa.UUID(as_uuid=True), sa.ForeignKey("transactions.id"), nullable=True, index=True),
        sa.Column("rule_id", sa.UUID(as_uuid=True), sa.ForeignKey("rules.id"), nullable=True, index=True),
        sa.Column("case_id", sa.UUID(as_uuid=True), sa.ForeignKey("cases.id"), nullable=True, index=True),
        sa.Column("severity", sa.String(16), nullable=False, default="medium"),
        sa.Column("risk_score", sa.Numeric(5, 2), default=0.00),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, default="new"),
    )

    # audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, index=True),
        sa.Column("entity_type", sa.String(64), nullable=False, index=True),
        sa.Column("entity_id", sa.String(255), nullable=False, index=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(255), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=True),
        sa.Column("previous_hash", sa.String(64), nullable=True),
        sa.Column("current_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )

    # sanctions_lists
    op.create_table(
        "sanctions_lists",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("list_source", sa.String(16), nullable=False, index=True),
        sa.Column("full_name", sa.String(512), nullable=False, index=True),
        sa.Column("name_variations", sa.JSON(), nullable=True),
        sa.Column("entity_type", sa.String(16), nullable=False),
        sa.Column("country", sa.String(128), nullable=True),
        sa.Column("program", sa.String(256), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("last_updated", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("sanctions_lists")
    op.drop_table("audit_logs")
    op.drop_table("alerts")
    op.drop_table("cases")
    op.drop_table("rules")
    op.drop_table("transactions")
    op.drop_table("accounts")
    op.drop_table("clients")

    # Drop ENUMs (PostgreSQL only)
    try:
        sa.Enum(name="sanctions_entity_type").drop(op.get_bind())
        sa.Enum(name="sanctions_source").drop(op.get_bind())
        sa.Enum(name="detector_type").drop(op.get_bind())
        sa.Enum(name="case_status").drop(op.get_bind())
        sa.Enum(name="alert_status").drop(op.get_bind())
        sa.Enum(name="alert_severity").drop(op.get_bind())
        sa.Enum(name="txn_status").drop(op.get_bind())
        sa.Enum(name="client_type").drop(op.get_bind())
    except Exception:
        pass
