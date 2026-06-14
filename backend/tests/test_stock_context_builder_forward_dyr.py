"""T2: stock_context_builder — StockContext.forward_dyr population.

G3 预期股息率: build_context should populate forward_dyr via
compute_forward_dyr_for_stock. build_screening_contexts (lightweight)
intentionally leaves forward_dyr=None — fail-fast screening handles
None fields by deferring to pass 2.
"""

from datetime import date

from app.models.dividend import DividendRecord
from app.models.price_kline import PriceKline
from app.models.stock import Stock
from app.services.stock_context_builder import (
    build_context,
    build_screening_contexts,
)


class TestStockContextForwardDyrField:
    def test_forward_dyr_field_exists_on_stock_context(self):
        from app.services.strategy_engine import StockContext
        ctx = StockContext(code="X")
        # Field should exist with default None
        assert hasattr(ctx, "forward_dyr")
        assert ctx.forward_dyr is None


class TestBuildContextPopulatesForwardDyr:
    def test_populates_forward_dyr_when_history_and_price_present(self, db_session):
        db_session.add(Stock(code="888001", name="测试股"))
        # 3-year history: 0.30, 0.32, 0.34 → avg 0.32
        db_session.add(DividendRecord(stock_code="888001", ex_date=date(2026, 6, 15),
                                      amount_per_share=0.34, quantity_held=0, total_received=0.0))
        db_session.add(DividendRecord(stock_code="888001", ex_date=date(2025, 6, 15),
                                      amount_per_share=0.32, quantity_held=0, total_received=0.0))
        db_session.add(DividendRecord(stock_code="888001", ex_date=date(2024, 6, 15),
                                      amount_per_share=0.30, quantity_held=0, total_received=0.0))
        # Latest close 8.0
        db_session.add(PriceKline(stock_code="888001", date=date(2026, 6, 13),
                                  open=8.0, high=8.2, low=7.9, close=8.0, volume=1000))
        db_session.commit()

        ctx = build_context(db_session, "888001")
        assert ctx.forward_dyr is not None
        # avg 0.32 / price 8.0 = 0.04
        assert abs(ctx.forward_dyr - 0.04) < 1e-6

    def test_forward_dyr_none_when_no_dividend_history(self, db_session):
        db_session.add(Stock(code="888002", name="无分红"))
        db_session.add(PriceKline(stock_code="888002", date=date(2026, 6, 13),
                                  open=10.0, high=10.5, low=9.8, close=10.0, volume=1000))
        db_session.commit()

        ctx = build_context(db_session, "888002")
        assert ctx.forward_dyr is None

    def test_forward_dyr_none_when_no_price(self, db_session):
        db_session.add(Stock(code="888003", name="停牌"))
        db_session.add(DividendRecord(stock_code="888003", ex_date=date(2025, 6, 15),
                                      amount_per_share=0.50, quantity_held=0, total_received=0.0))
        db_session.commit()

        ctx = build_context(db_session, "888003")
        assert ctx.forward_dyr is None


class TestBuildScreeningContextsLeavesForwardDyrNone:
    """Lightweight screening intentionally skips deep-tier fields.

    forward_dyr requires dividend history + price klines (2 queries per
    stock), so it's deferred to pass 2 (build_context).
    """

    def test_screening_context_forward_dyr_is_none(self, db_session):
        db_session.add(Stock(code="888010", name="测试股"))
        db_session.add(DividendRecord(stock_code="888010", ex_date=date(2025, 6, 15),
                                      amount_per_share=0.50, quantity_held=0, total_received=0.0))
        db_session.add(PriceKline(stock_code="888010", date=date(2026, 6, 13),
                                  open=10.0, high=10.5, low=9.8, close=10.0, volume=1000))
        db_session.commit()

        result = build_screening_contexts(db_session, ["888010"])
        ctx = result.get("888010")
        assert ctx is not None
        assert ctx.forward_dyr is None  # intentionally not populated
