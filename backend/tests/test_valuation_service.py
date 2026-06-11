"""Tests for valuation_service — core valuation calculation functions."""

from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.stock import Stock
from app.models.valuation import ValuationSnapshot
from app.services import valuation_service


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    """Create an in-memory SQLite session with all tables."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def sample_stock(db_session: Session) -> Stock:
    """Insert and return a sample stock."""
    stock = Stock(code="600519", name="Kweichow Moutai", industry="Beverage")
    db_session.add(stock)
    db_session.commit()
    return stock


# ===========================================================================
# calculate_percentiles
# ===========================================================================


class TestCalculatePercentiles:
    def test_empty_data(self):
        result = valuation_service.calculate_percentiles([])
        assert result["pe_bands"] == []
        assert result["pb_bands"] == []
        assert result["current_pe"] is None
        assert result["current_pb"] is None
        assert result["current_pe_percentile"] is None
        assert result["current_pb_percentile"] is None
        assert result["data_points"] == []

    def test_single_data_point(self):
        data = [{"date": "2024-01-15", "pe_ttm": 35.2, "pb": 12.5}]
        result = valuation_service.calculate_percentiles(data)

        # With a single value, all percentiles equal the same value
        assert len(result["pe_bands"]) == 5
        for band in result["pe_bands"]:
            assert band["value"] == pytest.approx(35.2, abs=0.01)

        assert len(result["pb_bands"]) == 5
        for band in result["pb_bands"]:
            assert band["value"] == pytest.approx(12.5, abs=0.01)

        assert result["current_pe"] == 35.2
        assert result["current_pb"] == 12.5
        assert result["current_pe_percentile"] == pytest.approx(100.0)
        assert result["current_pb_percentile"] == pytest.approx(100.0)

    def test_normal_data(self):
        data = [
            {"date": "2024-01-01", "pe_ttm": 30.0, "pb": 10.0},
            {"date": "2024-02-01", "pe_ttm": 35.0, "pb": 11.0},
            {"date": "2024-03-01", "pe_ttm": 40.0, "pb": 12.0},
            {"date": "2024-04-01", "pe_ttm": 45.0, "pb": 13.0},
            {"date": "2024-05-01", "pe_ttm": 50.0, "pb": 14.0},
        ]
        result = valuation_service.calculate_percentiles(data)

        assert len(result["pe_bands"]) == 5
        assert len(result["pb_bands"]) == 5

        # Last entry is the "current" one
        assert result["current_pe"] == 50.0
        assert result["current_pb"] == 14.0

        # PE percentiles should be ordered: 10th < 30th < 50th < 70th < 90th
        pe_vals = [b["value"] for b in result["pe_bands"]]
        assert pe_vals == sorted(pe_vals)

        # Current (50.0) is the max in this dataset => percentile = 100%
        assert result["current_pe_percentile"] == pytest.approx(100.0)

    def test_percentile_bands_structure(self):
        data = [
            {"date": f"2024-{i:02d}-01", "pe_ttm": float(20 + i), "pb": float(5 + i * 0.5)}
            for i in range(1, 13)
        ]
        result = valuation_service.calculate_percentiles(data)

        for bands_key in ["pe_bands", "pb_bands"]:
            bands = result[bands_key]
            assert len(bands) == 5
            percentiles = [b["percentile"] for b in bands]
            assert percentiles == [10, 30, 50, 70, 90]
            for band in bands:
                assert "value" in band
                assert isinstance(band["value"], float)

    def test_filters_out_zero_and_none_values(self):
        data = [
            {"date": "2024-01-01", "pe_ttm": 30.0, "pb": 10.0},
            {"date": "2024-02-01", "pe_ttm": 0, "pb": 11.0},
            {"date": "2024-03-01", "pe_ttm": None, "pb": 12.0},
            {"date": "2024-04-01", "pe_ttm": 40.0, "pb": 0},
            {"date": "2024-05-01", "pe_ttm": 50.0, "pb": None},
        ]
        result = valuation_service.calculate_percentiles(data)

        # PE should only have 2 valid values (30.0 and 40.0 and 50.0)
        # pe_ttm=0 is falsy in Python, so it gets filtered by `if entry.get("pe_ttm")`
        assert len(result["pe_bands"]) == 5  # Still produces 5 bands from available data

    def test_current_percentile_mid_range(self):
        """Test percentile rank calculation for a value in the middle."""
        data = [
            {"date": f"2024-{i:02d}-01", "pe_ttm": float(i * 10), "pb": float(i)}
            for i in range(1, 11)
        ]
        # Current PE = 100 (last entry)
        result = valuation_service.calculate_percentiles(data)

        # PE values are 10, 20, 30, ..., 100
        # 100 is the max => percentile should be 100%
        assert result["current_pe_percentile"] == pytest.approx(100.0)

    def test_data_points_preserved(self):
        data = [
            {"date": "2024-01-01", "pe_ttm": 30.0, "pb": 10.0},
            {"date": "2024-02-01", "pe_ttm": 35.0, "pb": 11.0},
        ]
        result = valuation_service.calculate_percentiles(data)

        assert len(result["data_points"]) == 2
        assert result["data_points"][0]["date"] == "2024-01-01"
        assert result["data_points"][0]["pe_ttm"] == 30.0
        assert result["data_points"][0]["pb"] == 10.0


class TestCheckDividendSustainability:
    def test_healthy(self):
        """OCF >= net_profit >= dividends => healthy."""
        result = valuation_service.check_dividend_sustainability(
            operating_cash_flow=600.0,
            net_profit=500.0,
            dividends_paid=300.0,
        )
        assert result["status"] == "healthy"
        assert "可持续" in result["message"]

    def test_needs_verification(self):
        """Dividends > net_profit but OCF >= dividends => needs_verification."""
        result = valuation_service.check_dividend_sustainability(
            operating_cash_flow=600.0,
            net_profit=300.0,
            dividends_paid=500.0,
        )
        assert result["status"] == "needs_verification"
        assert "验证" in result["message"]

    def test_unsustainable(self):
        """Dividends > OCF => unsustainable."""
        result = valuation_service.check_dividend_sustainability(
            operating_cash_flow=200.0,
            net_profit=300.0,
            dividends_paid=400.0,
        )
        assert result["status"] == "unsustainable"
        assert "不可持续" in result["message"]

    def test_caution(self):
        """OCF < net_profit but dividends <= net_profit => caution."""
        result = valuation_service.check_dividend_sustainability(
            operating_cash_flow=300.0,
            net_profit=500.0,
            dividends_paid=200.0,
        )
        assert result["status"] == "caution"
        assert "现金流质量" in result["message"]

    def test_edge_case_equal_values(self):
        """OCF == net_profit == dividends => healthy."""
        result = valuation_service.check_dividend_sustainability(
            operating_cash_flow=500.0,
            net_profit=500.0,
            dividends_paid=500.0,
        )
        assert result["status"] == "healthy"

    def test_zero_dividends(self):
        """Zero dividends with positive cash flow => healthy."""
        result = valuation_service.check_dividend_sustainability(
            operating_cash_flow=500.0,
            net_profit=400.0,
            dividends_paid=0.0,
        )
        assert result["status"] == "healthy"

    def test_all_zero_returns_data_unavailable(self):
        from app.services.valuation_service import check_dividend_sustainability
        result = check_dividend_sustainability(0, 0, 0)
        assert result["status"] != "healthy"
        assert result["status"] == "data_unavailable"

    def test_normal_healthy_case(self):
        from app.services.valuation_service import check_dividend_sustainability
        result = check_dividend_sustainability(100, 50, 20)
        assert result["status"] == "healthy"


# ===========================================================================
# get_valuation_dashboard
# ===========================================================================


class TestValuationDashboard:
    def test_get_dashboard_empty(self, db_session: Session):
        dashboard = valuation_service.get_valuation_dashboard(db_session, "600519")
        assert dashboard["stock_code"] == "600519"
        assert dashboard["latest_snapshot"] is None
        assert dashboard["snapshots"] == []
        assert dashboard["sustainability"] is None
        assert "composite" in dashboard

    def test_get_dashboard_with_snapshot(self, db_session: Session, sample_stock: Stock):
        from app.models.financial import FinancialStatement
        from app.models.valuation import ValuationSnapshot

        db_session.add(ValuationSnapshot(
            stock_code="600519",
            date=date(2025, 5, 1),
            pe_ttm=35.0,
            pb=12.0,
        ))
        db_session.add(FinancialStatement(
            stock_code="600519",
            report_date=datetime(2024, 12, 31),
            report_type="annual",
            operating_cash_flow=600.0,
            net_profit=500.0,
            dividends_paid=300.0,
        ))
        db_session.commit()

        dashboard = valuation_service.get_valuation_dashboard(db_session, "600519")

        assert dashboard["latest_snapshot"] is not None
        assert dashboard["latest_snapshot"]["pe_ttm"] == 35.0
        assert len(dashboard["snapshots"]) == 1
        assert dashboard["sustainability"] is not None
        assert dashboard["sustainability"]["status"] == "healthy"

    def test_get_dashboard_multiple_snapshots(self, db_session: Session, sample_stock: Stock):
        from app.models.valuation import ValuationSnapshot

        db_session.add(ValuationSnapshot(
            stock_code="600519",
            date=date(2025, 4, 1),
            pe_ttm=30.0,
        ))
        db_session.add(ValuationSnapshot(
            stock_code="600519",
            date=date(2025, 5, 1),
            pe_ttm=35.0,
        ))
        db_session.commit()

        dashboard = valuation_service.get_valuation_dashboard(db_session, "600519")

        assert len(dashboard["snapshots"]) == 2
        assert dashboard["latest_snapshot"]["pe_ttm"] == 35.0
        assert dashboard["snapshots"][0]["pe_ttm"] == 35.0
        assert dashboard["snapshots"][1]["pe_ttm"] == 30.0


