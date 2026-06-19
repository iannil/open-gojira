"""DataFreshness service — staleness gate + sync tracking."""
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.data_freshness import DataFreshness
from app.services.system_alert_service import create_alert
from app.core.datetime_utils import now


def _utcnow_naive() -> datetime:
    return now()


class DataStaleError(HTTPException):
    def __init__(self, category: str, last_success: datetime | None, max_age_hours: int):
        last_str = last_success.isoformat() if last_success else "never"
        super().__init__(
            status_code=503,
            detail=(
                f"Data stale: category '{category}' last successful sync at "
                f"{last_str}, max age {max_age_hours}h. Refusing to run."
            ),
        )


def _get_or_create(db: Session, category: str) -> DataFreshness:
    f = db.execute(
        select(DataFreshness).where(DataFreshness.category == category)
    ).scalar_one_or_none()
    if not f:
        f = DataFreshness(category=category)
        db.add(f)
        db.flush()
    return f


def record_sync_attempt(db: Session, category: str) -> None:
    f = _get_or_create(db, category)
    f.last_synced_at = _utcnow_naive()
    db.flush()


def record_sync_success(db: Session, category: str, record_count: int) -> None:
    f = _get_or_create(db, category)
    now = _utcnow_naive()
    f.last_synced_at = now
    f.last_success_at = now
    f.last_record_count = record_count
    f.last_error = None
    db.flush()


def record_sync_failure(db: Session, category: str, error: str) -> None:
    f = _get_or_create(db, category)
    f.last_synced_at = _utcnow_naive()
    f.last_error = error[:500]  # truncate
    db.flush()


def assert_fresh_enough(db: Session, category: str, max_age_hours: int = 24) -> None:
    """Raise DataStaleError if last_success_at older than max_age_hours.

    Also creates a system_alert so UI can show red banner.
    """
    f = db.execute(
        select(DataFreshness).where(DataFreshness.category == category)
    ).scalar_one_or_none()

    if not f or not f.last_success_at:
        create_alert(
            db,
            severity="critical",
            category="data",
            message=f"Data category '{category}' has never been synced",
            detail={"category": category, "max_age_hours": max_age_hours},
        )
        raise DataStaleError(category, None, max_age_hours)

    age = _utcnow_naive() - f.last_success_at
    if age.total_seconds() > max_age_hours * 3600:
        age_hours = age.total_seconds() / 3600
        create_alert(
            db,
            severity="critical",
            category="data",
            message=f"Data category '{category}' is {age_hours:.1f}h stale (max {max_age_hours}h)",
            detail={
                "category": category,
                "last_success_at": f.last_success_at.isoformat(),
                "age_hours": round(age_hours, 1),
                "max_age_hours": max_age_hours,
            },
        )
        raise DataStaleError(category, f.last_success_at, max_age_hours)


def get_freshness_report(db: Session) -> dict[str, dict]:
    """Summary for UI: per-category last_success_at / age / record_count."""
    rows = db.execute(select(DataFreshness)).scalars().all()
    now = _utcnow_naive()
    report = {}
    for f in rows:
        age_hours = (
            (now - f.last_success_at).total_seconds() / 3600
            if f.last_success_at else None
        )
        report[f.category] = {
            "last_synced_at": f.last_synced_at.isoformat() if f.last_synced_at else None,
            "last_success_at": f.last_success_at.isoformat() if f.last_success_at else None,
            "age_hours": round(age_hours, 1) if age_hours is not None else None,
            "record_count": f.last_record_count,
            "last_error": f.last_error,
        }
    return report
