"""AML Monitor — SAR (Suspicious Activity Report) Export Service.

Генерация PDF и CSV отчётов по алертам для compliance-отчётности.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.models.transaction import Transaction
from app.models.rule import Rule


# ---------------------------------------------------------------------------
# CSV Export
# ---------------------------------------------------------------------------


async def export_alerts_csv(
    db: AsyncSession,
    status: str | None = None,
    severity: str | None = None,
    limit: int = 1000,
) -> str:
    """Export alerts as CSV string.

    Returns:
        CSV-formatted string with alert data suitable for SAR reporting.
    """
    query = (
        select(Alert)
        .order_by(Alert.created_at.desc())
        .limit(limit)
    )

    if status:
        query = query.where(Alert.status == status)
    if severity:
        query = query.where(Alert.severity == severity)

    result = await db.execute(query)
    alerts = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "Alert ID",
        "Created At",
        "Severity",
        "Status",
        "Risk Score",
        "Title",
        "Description",
        "Rule ID",
        "Rule Name",
        "Transaction ID",
        "Transaction Amount",
        "Transaction Currency",
        "Transaction Timestamp",
    ])

    for alert in alerts:
        txn_amount = ""
        txn_currency = ""
        txn_timestamp = ""
        rule_name = ""

        if alert.transaction:
            txn_amount = str(alert.transaction.amount)
            txn_currency = alert.transaction.currency
            txn_timestamp = alert.transaction.txn_timestamp.isoformat() if alert.transaction.txn_timestamp else ""

        if alert.rule:
            rule_name = alert.rule.name

        writer.writerow([
            str(alert.id),
            alert.created_at.isoformat() if alert.created_at else "",
            alert.severity,
            alert.status,
            str(alert.risk_score) if alert.risk_score else "",
            alert.title,
            (alert.description or "").replace("\n", " "),
            str(alert.rule_id) if alert.rule_id else "",
            rule_name,
            str(alert.transaction_id) if alert.transaction_id else "",
            txn_amount,
            txn_currency,
            txn_timestamp,
        ])

    return output.getvalue()


# ---------------------------------------------------------------------------
# PDF Export (simple text-based report)
# ---------------------------------------------------------------------------


async def export_alert_report_text(
    db: AsyncSession,
    alert_id: str,
) -> str:
    """Generate a human-readable SAR-style report for a single alert.

    Returns:
        Plain text report formatted for compliance review.
    """
    import uuid

    try:
        alert_uuid = uuid.UUID(alert_id)
    except ValueError:
        return "Invalid alert ID"

    result = await db.execute(
        select(Alert).where(Alert.id == alert_uuid)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        return f"Alert {alert_id} not found"

    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("SUSPICIOUS ACTIVITY REPORT (SAR)")
    lines.append("=" * 72)
    lines.append("")
    lines.append(f"Report Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append("")
    lines.append("-" * 72)
    lines.append("ALERT INFORMATION")
    lines.append("-" * 72)
    lines.append(f"  Alert ID:       {alert.id}")
    lines.append(f"  Title:          {alert.title}")
    lines.append(f"  Severity:       {alert.severity}")
    lines.append(f"  Status:         {alert.status}")
    lines.append(f"  Risk Score:     {alert.risk_score}")
    lines.append(f"  Created At:     {alert.created_at.isoformat() if alert.created_at else 'N/A'}")
    lines.append("")
    lines.append(f"  Description:")
    lines.append(f"    {alert.description or 'No description'}")
    lines.append("")

    if alert.rule:
        lines.append("-" * 72)
        lines.append("RULE INFORMATION")
        lines.append("-" * 72)
        lines.append(f"  Rule ID:        {alert.rule.id}")
        lines.append(f"  Rule Name:      {alert.rule.name}")
        lines.append(f"  Detector Type:  {alert.rule.detector_type}")
        lines.append("")

    if alert.transaction:
        lines.append("-" * 72)
        lines.append("TRANSACTION DETAILS")
        lines.append("-" * 72)
        lines.append(f"  Transaction ID: {alert.transaction.id}")
        lines.append(f"  External ID:    {alert.transaction.external_id}")
        lines.append(f"  Amount:         {alert.transaction.amount} {alert.transaction.currency}")
        lines.append(f"  Timestamp:      {alert.transaction.txn_timestamp.isoformat() if alert.transaction.txn_timestamp else 'N/A'}")
        lines.append(f"  Channel:        {alert.transaction.channel or 'N/A'}")
        lines.append(f"  Source Account: {alert.transaction.source_account_id}")
        lines.append(f"  Dest Account:   {alert.transaction.destination_account_id}")
        lines.append("")

    lines.append("=" * 72)
    lines.append("END OF REPORT")
    lines.append("=" * 72)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Compliance statistics
# ---------------------------------------------------------------------------


async def get_compliance_stats(
    db: AsyncSession,
) -> dict:
    """Get compliance dashboard statistics.

    Returns:
        Dict with keys: total_alerts, by_severity, by_status,
        open_cases, total_transactions, etc.
    """
    from sqlalchemy import func as sa_func

    # Total alerts
    result = await db.execute(select(sa_func.count(Alert.id)))
    total_alerts = result.scalar() or 0

    # Alerts by severity
    result = await db.execute(
        select(Alert.severity, sa_func.count(Alert.id))
        .group_by(Alert.severity)
    )
    by_severity = {row[0]: row[1] for row in result.all()}

    # Alerts by status
    result = await db.execute(
        select(Alert.status, sa_func.count(Alert.id))
        .group_by(Alert.status)
    )
    by_status = {row[0]: row[1] for row in result.all()}

    # Total transactions
    from app.models.transaction import Transaction
    result = await db.execute(select(sa_func.count(Transaction.id)))
    total_transactions = result.scalar() or 0

    # Total cases
    from app.models.case import Case
    result = await db.execute(select(sa_func.count(Case.id)))
    total_cases = result.scalar() or 0

    # Open cases
    result = await db.execute(
        select(sa_func.count(Case.id)).where(Case.status.in_(["open", "in_review"]))
    )
    open_cases = result.scalar() or 0

    # Total audit log entries
    from app.models.audit_log import AuditLog
    result = await db.execute(select(sa_func.count(AuditLog.id)))
    total_audit_entries = result.scalar() or 0

    return {
        "total_alerts": total_alerts,
        "alerts_by_severity": by_severity,
        "alerts_by_status": by_status,
        "total_transactions": total_transactions,
        "total_cases": total_cases,
        "open_cases": open_cases,
        "total_audit_entries": total_audit_entries,
    }