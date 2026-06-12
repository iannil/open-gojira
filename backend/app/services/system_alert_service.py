"""SystemAlert service — create/list/resolve + convenience queries."""
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.system_alert import SystemAlert


def create_alert(
    db: Session,
    *,
    severity: str,
    category: str,
    message: str,
    detail: dict[str, Any] | None = None,
) -> SystemAlert:
    """Create and persist a system alert. Caller commits."""
    alert = SystemAlert(
        severity=severity,
        category=category,
        message=message,
        detail_json=detail,
    )
    db.add(alert)
    db.flush()
    return alert


def list_alerts(
    db: Session,
    *,
    severity: str | None = None,
    category: str | None = None,
    limit: int = 100,
) -> list[SystemAlert]:
    """List alerts, newest first. Optional severity/category filter."""
    stmt = select(SystemAlert).order_by(desc(SystemAlert.created_at))
    if severity:
        stmt = stmt.where(SystemAlert.severity == severity)
    if category:
        stmt = stmt.where(SystemAlert.category == category)
    return list(db.execute(stmt.limit(limit)).scalars().all())


def list_unresolved(
    db: Session,
    *,
    severity: str | None = None,
    category: str | None = None,
    limit: int = 100,
) -> list[SystemAlert]:
    """List alerts where resolved_at IS NULL. Newest first."""
    stmt = (
        select(SystemAlert)
        .where(SystemAlert.resolved_at.is_(None))
        .order_by(desc(SystemAlert.created_at))
    )
    if severity:
        stmt = stmt.where(SystemAlert.severity == severity)
    if category:
        stmt = stmt.where(SystemAlert.category == category)
    return list(db.execute(stmt.limit(limit)).scalars().all())


def resolve_alert(
    db: Session,
    alert_id: int,
    *,
    resolved_by: str = "manual",
) -> SystemAlert | None:
    """Mark an alert resolved. Idempotent: if already resolved, no-op."""
    alert = db.get(SystemAlert, alert_id)
    if not alert:
        return None
    if alert.resolved_at is not None:
        return alert  # already resolved
    alert.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)
    alert.resolved_by = resolved_by
    db.flush()
    return alert


def resolve_matching(
    db: Session,
    *,
    severity: str | None = None,
    category: str | None = None,
    resolved_by: str = "auto",
) -> int:
    """Resolve all unresolved alerts matching the filter. Returns count."""
    stmt = select(SystemAlert).where(SystemAlert.resolved_at.is_(None))
    if severity:
        stmt = stmt.where(SystemAlert.severity == severity)
    if category:
        stmt = stmt.where(SystemAlert.category == category)
    alerts = list(db.execute(stmt).scalars().all())
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for a in alerts:
        a.resolved_at = now
        a.resolved_by = resolved_by
    db.flush()
    return len(alerts)


def get_critical_unresolved_count(db: Session) -> int:
    """Count critical alerts still unresolved — drives UI badge."""
    return db.execute(
        select(func.count(SystemAlert.id)).where(
            SystemAlert.severity == "critical",
            SystemAlert.resolved_at.is_(None),
        )
    ).scalar_one()
