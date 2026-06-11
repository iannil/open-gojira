"""Tests for TTM (trailing-four-quarter) rollup in get_ratio_trends."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.financial import FinancialStatement
from app.services.financial_service import get_ratio_trends


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _q(stock_code, year, month, revenue, net_profit, roe=None):
    return FinancialStatement(
        stock_code=stock_code,
        report_date=datetime(year, month, {3: 31, 6: 30, 9: 30, 12: 31}[month]),
        report_type="quarterly",
        revenue=revenue,
        net_profit=net_profit,
        roe=roe,
    )


def test_ttm_sums_trailing_four_quarters_and_growth(db):
    # 8 quarters: 2023 Q1..Q4 and 2024 Q1..Q4
    rows = [
        _q("600519", 2023, 3, 100, 30, roe=5),
        _q("600519", 2023, 6, 110, 33, roe=10),
        _q("600519", 2023, 9, 120, 36, roe=15),
        _q("600519", 2023, 12, 130, 39, roe=20),  # TTM_2023 = 460 / 138
        _q("600519", 2024, 3, 140, 42, roe=6),
        _q("600519", 2024, 6, 150, 45, roe=12),
        _q("600519", 2024, 9, 160, 48, roe=18),
        _q("600519", 2024, 12, 170, 51, roe=24),  # TTM_2024 = 620 / 186
    ]
    for r in rows:
        db.add(r)
    db.commit()

    trends = get_ratio_trends(db, "600519")
    assert len(trends.quarterly) == 8

    # First TTM point is at index 3 (2023-Q4)
    q4_2023 = trends.quarterly[3]
    # No growth available yet (only one full TTM window)
    assert q4_2023.revenue_growth in (None, 0) or q4_2023.revenue_growth == rows[3].revenue_growth

    # 2024-Q4 has a full prior-year window
    q4_2024 = trends.quarterly[7]
    # TTM revenue: 620; prior TTM: 460; growth = (620-460)/460 = ~34.78%
    assert q4_2024.revenue_growth is not None
    assert abs(q4_2024.revenue_growth - (620 - 460) / 460 * 100) < 1e-6
    # TTM net profit: 186; prior: 138; growth = (186-138)/138 ≈ 34.78%
    assert q4_2024.net_profit_growth is not None
    assert abs(q4_2024.net_profit_growth - (186 - 138) / 138 * 100) < 1e-6
    # Point-in-time ROE passes through
    assert q4_2024.roe == 24


def test_ttm_handles_missing_quarters_gracefully(db):
    # Only 2 quarters — no TTM growth possible
    db.add(_q("600519", 2024, 6, 100, 30))
    db.add(_q("600519", 2024, 9, 110, 33))
    db.commit()

    trends = get_ratio_trends(db, "600519")
    assert len(trends.quarterly) == 2
    # No TTM growth computed (insufficient history); falls back to stored field (None)
    assert trends.quarterly[1].revenue_growth is None
