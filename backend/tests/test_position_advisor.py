"""Tests for position_advisor_service — 组合级仓位约束检查."""

import pytest
from unittest.mock import patch, MagicMock

from app.services.position_advisor_service import (
    TARGET_HOLDINGS_RANGE,
    MAX_INDUSTRY_WEIGHT,
    check_before_draft,
    PositionAdvice,
)


class TestPositionAdviceToDict:
    def test_to_dict(self):
        advice = PositionAdvice(
            holdings_count=3,
            target_range=(3, 4),
            can_open_new=False,
            blockers=["超过上限"],
            diversification_warnings=["接近行业上限"],
        )
        d = advice.to_dict()
        assert d["holdings_count"] == 3
        assert d["target_range"] == [3, 4]
        assert len(d["blockers"]) == 1
        assert not d["can_open_new"]


class TestCheckBeforeDraft:
    """Test portfolio constraint checking with mocked DB."""

    def _mock_db(self, holdings=None, pending_buys=None, stock_industry="银行"):
        db = MagicMock()
        # _open_holdings
        holdings = holdings or []
        db.execute.return_value.scalars.return_value.all.return_value = holdings
        # db.get for Stock
        mock_stock = MagicMock()
        mock_stock.industry = stock_industry
        db.get.return_value = mock_stock
        # _get_cached_price
        return db

    def _make_holding(self, code="600000", industry="银行"):
        """Mock holding in the dict shape produced by holding_view_service."""
        return {
            "stock_code": code,
            "total_quantity": 1000,
            "avg_cost_basis": 10.0,
            "first_buy_at": None,
            "last_trade_at": None,
            # "_industry" kept for any test that introspects it
            "_industry": industry,
        }

    def test_sell_always_allowed(self):
        """SELL drafts should never be blocked."""
        db = self._mock_db()
        advice = check_before_draft(db, "600000", "SELL")
        assert advice.can_open_new is True
        assert len(advice.blockers) == 0

    @patch("app.services.position_advisor_service._open_holdings")
    @patch("app.services.position_advisor_service._pending_buy_drafts")
    @patch("app.services.position_advisor_service._industry_weights")
    def test_buy_blocked_when_max_holdings(
        self, mock_ind, mock_pending, mock_holdings
    ):
        """BUY blocked when already at max holdings + pending."""
        holdings = [self._make_holding(f"60000{i}") for i in range(4)]
        mock_holdings.return_value = holdings
        mock_pending.return_value = [MagicMock()]  # 1 pending buy
        mock_ind.return_value = {"银行": 0.3}

        db = MagicMock()
        mock_stock = MagicMock()
        mock_stock.industry = "煤炭"
        db.get.return_value = mock_stock

        advice = check_before_draft(db, "601088", "BUY")
        assert advice.holdings_count == 4
        assert not advice.can_open_new
        assert any("超过上限" in b for b in advice.blockers)

    @patch("app.services.position_advisor_service._open_holdings")
    @patch("app.services.position_advisor_service._pending_buy_drafts")
    @patch("app.services.position_advisor_service._industry_weights")
    def test_buy_blocked_when_industry_concentrated(
        self, mock_ind, mock_pending, mock_holdings
    ):
        """BUY blocked when buying a NEW stock in an already-heavy industry."""
        mock_holdings.return_value = [self._make_holding(code="601398", industry="银行")]
        mock_pending.return_value = []
        mock_ind.return_value = {"银行": MAX_INDUSTRY_WEIGHT}

        db = MagicMock()
        mock_stock = MagicMock()
        mock_stock.industry = "银行"
        db.get.return_value = mock_stock

        # Trying to buy a DIFFERENT stock in the same industry
        advice = check_before_draft(db, "600000", "BUY")
        assert not advice.can_open_new
        assert any("行业" in b for b in advice.blockers)

    @patch("app.services.position_advisor_service._open_holdings")
    @patch("app.services.position_advisor_service._pending_buy_drafts")
    @patch("app.services.position_advisor_service._industry_weights")
    def test_buy_allowed_normal(
        self, mock_ind, mock_pending, mock_holdings
    ):
        """BUY allowed when constraints not violated."""
        mock_holdings.return_value = [self._make_holding()]
        mock_pending.return_value = []
        mock_ind.return_value = {"银行": 0.10}

        db = MagicMock()
        mock_stock = MagicMock()
        mock_stock.industry = "煤炭"
        db.get.return_value = mock_stock

        advice = check_before_draft(db, "601088", "BUY")
        assert advice.can_open_new
        assert len(advice.blockers) == 0

    @patch("app.services.position_advisor_service._open_holdings")
    @patch("app.services.position_advisor_service._pending_buy_drafts")
    @patch("app.services.position_advisor_service._industry_weights")
    def test_buy_adding_to_existing_position_allowed(
        self, mock_ind, mock_pending, mock_holdings
    ):
        """BUY allowed for same stock even if industry at 100% (adding to winner)."""
        mock_holdings.return_value = [self._make_holding(code="601398", industry="银行")]
        mock_pending.return_value = []
        mock_ind.return_value = {"银行": 1.0}  # 100% in banking

        db = MagicMock()
        mock_stock = MagicMock()
        mock_stock.industry = "银行"
        db.get.return_value = mock_stock

        advice = check_before_draft(db, "601398", "BUY")
        assert advice.can_open_new  # Adding to existing position is OK
        assert len(advice.blockers) == 0

    @patch("app.services.position_advisor_service._open_holdings")
    @patch("app.services.position_advisor_service._pending_buy_drafts")
    @patch("app.services.position_advisor_service._industry_weights")
    def test_buy_warns_in_high_cycle(
        self, mock_ind, mock_pending, mock_holdings
    ):
        """BUY warns but doesn't block when cycle is high."""
        mock_holdings.return_value = [self._make_holding()]
        mock_pending.return_value = []
        mock_ind.return_value = {"银行": 0.10}

        db = MagicMock()
        mock_stock = MagicMock()
        mock_stock.industry = "煤炭"
        db.get.return_value = mock_stock

        advice = check_before_draft(db, "601088", "BUY", cycle_position="high")
        assert advice.can_open_new  # Not blocked, just warned
        assert any("高" in w or "cycle" in w.lower() or "不建议" in w for w in advice.diversification_warnings)

    @patch("app.services.position_advisor_service._open_holdings")
    @patch("app.services.position_advisor_service._pending_buy_drafts")
    @patch("app.services.position_advisor_service._industry_weights")
    def test_industry_near_limit_warns(
        self, mock_ind, mock_pending, mock_holdings
    ):
        """Warning when buying a NEW stock and industry weight is >80% of limit."""
        mock_holdings.return_value = [self._make_holding(code="601398", industry="银行")]
        mock_pending.return_value = []
        mock_ind.return_value = {"银行": MAX_INDUSTRY_WEIGHT * 0.85}

        db = MagicMock()
        mock_stock = MagicMock()
        mock_stock.industry = "银行"
        db.get.return_value = mock_stock

        # Buying a different stock in same industry triggers warning
        advice = check_before_draft(db, "600000", "BUY")
        assert any("接近" in w for w in advice.diversification_warnings)
