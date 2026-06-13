"""Test trading_calendar + is_trading_day."""
from datetime import date
import pytest

from app.models.trading_calendar import TradingCalendar
from app.services.trading_calendar_service import (
    is_trading_day, seed_default_holidays, get_trading_days_in_range,
)


def test_is_trading_day_weekday(db_session):
    """Normal weekday is a trading day."""
    db_session.add(TradingCalendar(date=date(2026, 6, 12), is_trading_day=True))
    db_session.flush()
    assert is_trading_day(db_session, date(2026, 6, 12)) is True


def test_is_holiday(db_session):
    """Marked as non-trading day."""
    db_session.add(TradingCalendar(date=date(2026, 1, 1), is_trading_day=False,
                                    holiday_name="元旦"))
    db_session.flush()
    assert is_trading_day(db_session, date(2026, 1, 1)) is False


def test_is_trading_day_unknown_returns_weekday_check(db_session):
    """If a date is not in the table, fall back to weekday check."""
    # 2026-06-12 is a Friday, not in table
    # Should return True (weekday)
    assert is_trading_day(db_session, date(2026, 6, 12)) is True


def test_is_trading_day_weekend_unknown(db_session):
    """Weekend not in table → not a trading day."""
    # 2026-06-13 is a Saturday
    assert is_trading_day(db_session, date(2026, 6, 13)) is False


def test_seed_default_holidays_idempotent(db_session):
    """Seeding twice doesn't duplicate."""
    count1 = seed_default_holidays(db_session, year=2026)
    db_session.commit()
    count2 = seed_default_holidays(db_session, year=2026)
    db_session.commit()
    assert count2 == 0  # already seeded


def test_seed_adds_known_holidays(db_session):
    count = seed_default_holidays(db_session, year=2026)
    db_session.commit()
    assert count > 5  # at least NY + spring fest + labor + national day
    # 元旦 should be in
    rows = db_session.query(TradingCalendar).filter(
        TradingCalendar.date >= date(2026, 1, 1),
        TradingCalendar.date <= date(2026, 1, 5),
    ).all()
    assert any(not r.is_trading_day for r in rows)


def test_get_trading_days_in_range(db_session):
    """Filter weekdays excluding holidays."""
    seed_default_holidays(db_session, year=2026)
    db_session.commit()
    days = get_trading_days_in_range(db_session,
                                       date(2026, 6, 8),  # Mon
                                       date(2026, 6, 12))  # Fri
    assert len(days) == 5  # 5 weekdays no holidays
