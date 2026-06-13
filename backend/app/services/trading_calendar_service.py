"""Trading calendar service — is_trading_day + holiday seeding."""
import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.trading_calendar import TradingCalendar


logger = logging.getLogger(__name__)


# 已知 A 股节假日(扩展时更新)
_KNOWN_HOLIDAYS: dict[int, list[tuple[str, str]]] = {
    2025: [
        ("2025-01-01", "元旦"),
        ("2025-01-28", "春节假期"),
        ("2025-01-29", "春节假期"),
        ("2025-01-30", "春节假期"),
        ("2025-01-31", "春节假期"),
        ("2025-02-03", "春节假期"),
        ("2025-04-04", "清明节"),
        ("2025-05-01", "劳动节"),
        ("2025-05-02", "劳动节"),
        ("2025-05-05", "劳动节"),
        ("2025-06-02", "端午节"),
        ("2025-10-01", "国庆节"),
        ("2025-10-02", "国庆节"),
        ("2025-10-03", "国庆节"),
        ("2025-10-06", "国庆节"),
        ("2025-10-07", "国庆节"),
        ("2025-10-08", "国庆节"),
    ],
    2026: [
        ("2026-01-01", "元旦"),
        ("2026-02-16", "春节假期"),
        ("2026-02-17", "春节假期"),
        ("2026-02-18", "春节假期"),
        ("2026-02-19", "春节假期"),
        ("2026-02-23", "春节假期"),
        ("2026-04-06", "清明节"),
        ("2026-05-01", "劳动节"),
        ("2026-05-25", "端午节"),
        ("2026-10-01", "国庆节"),
        ("2026-10-02", "国庆节"),
        ("2026-10-05", "国庆节"),
        ("2026-10-06", "国庆节"),
        ("2026-10-07", "国庆节"),
        ("2026-10-08", "国庆节"),
    ],
    2027: [
        ("2027-01-01", "元旦"),
        ("2027-02-08", "春节假期"),
        ("2027-02-09", "春节假期"),
        ("2027-02-10", "春节假期"),
        ("2027-02-11", "春节假期"),
        ("2027-02-12", "春节假期"),
        ("2027-04-05", "清明节"),
        ("2027-05-03", "劳动节"),
        ("2027-06-09", "端午节"),
        ("2027-09-20", "中秋节"),
        ("2027-10-01", "国庆节"),
    ],
}


def is_trading_day(db: Session, day: date) -> bool:
    """Check if a day is an A-share trading day.

    Falls back to weekday check (Mon-Fri) for dates not in DB.
    """
    row = db.execute(
        select(TradingCalendar).where(TradingCalendar.date == day)
    ).scalar_one_or_none()
    if row:
        return row.is_trading_day
    # Fallback: weekday check (Mon=0, Sun=6)
    return day.weekday() < 5


def get_trading_days_in_range(
    db: Session, start: date, end: date
) -> list[date]:
    """List of trading days in [start, end], weekday fallback applied."""
    days = []
    current = start
    while current <= end:
        if is_trading_day(db, current):
            days.append(current)
        current += timedelta(days=1)
    return days


def seed_default_holidays(db: Session, year: int) -> int:
    """Seed trading_calendar with known holidays for the given year.

    Idempotent: skips dates already in table. Returns count of new rows.
    """
    holidays = _KNOWN_HOLIDAYS.get(year, [])
    if not holidays:
        logger.warning("No known holidays for year %s, skipping seed", year)
        return 0

    inserted = 0
    for date_str, name in holidays:
        d = date.fromisoformat(date_str)
        existing = db.execute(
            select(TradingCalendar).where(TradingCalendar.date == d)
        ).scalar_one_or_none()
        if existing:
            continue
        db.add(TradingCalendar(date=d, is_trading_day=False, holiday_name=name))
        inserted += 1
    db.flush()
    return inserted


def seed_all_years(db: Session) -> int:
    """Seed all years in _KNOWN_HOLIDAYS."""
    total = 0
    for year in _KNOWN_HOLIDAYS:
        total += seed_default_holidays(db, year)
    return total
