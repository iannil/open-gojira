"""SystemAlert — infrastructure-level alerts (distinct from business AlertEvent).

SystemAlerts cover problems with the system itself:
- Lixinger API consecutive failures
- Data sync staleness (> 24h)
- Data sanity violations (> 1% records rejected)
- Scheduler job missed heartbeats
- Token expired / quota exhausted
- Disk full / DB corruption

Business AlertEvents cover market/price events (stop loss hit, thesis
breach, etc.) — those are separate (see app/models/alert.py).
"""
from datetime import datetime
from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base


class SystemAlert(Base):
    __tablename__ = "system_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    severity: Mapped[str] = mapped_column(String, nullable=False, index=True)
    """info | warning | critical"""

    category: Mapped[str] = mapped_column(String, nullable=False, index=True)
    """data | scheduler | api | db | token"""

    message: Mapped[str] = mapped_column(String, nullable=False)
    """One-line summary for UI banner."""

    detail_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    """Arbitrary structured details: endpoint, error message, count, etc."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    resolved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    """User/system that resolved it (e.g. 'manual', 'auto:recovery')."""
