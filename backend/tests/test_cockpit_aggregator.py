"""Cockpit aggregator tests — _safe() failure isolation and build() contract."""

import pytest

from app.models.cashflow_goal import CashflowGoal
from app.services import cockpit_service
from tests.conftest import TestSessionLocal


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    from app.services import holding_service

    holding_service._price_cache.clear()
    monkeypatch.setattr(holding_service, "_get_cached_price", lambda code: None)
    # Clear rebalance cache between tests
    cockpit_service._rebalance_cache = None


@pytest.fixture
def db():
    s = TestSessionLocal()
    try:
        yield s
    finally:
        s.close()


def _seed_goal(db):
    goal = CashflowGoal(
        id=1,
        annual_expense=100000,
        goal_multiple=10,
        cash_reserve=50000,
        target_weighted_dyr=0.045,
    )
    db.add(goal)
    db.commit()


class TestSafeIsolation:
    """_safe() must catch exceptions and append to errors list."""

    def test_safe_returns_fn_result_on_success(self):
        errors: list[str] = []
        result = cockpit_service._safe("ok", lambda: 42, 0, errors)
        assert result == 42
        assert not errors

    def test_safe_returns_default_on_exception(self):
        errors: list[str] = []
        result = cockpit_service._safe(
            "boom", lambda: (_ for _ in ()).throw(ValueError("oops")), [], errors
        )
        assert result == []
        assert len(errors) == 1
        assert "boom" in errors[0]
        assert "ValueError" in errors[0]

    def test_safe_multiple_failures(self):
        errors: list[str] = []
        cockpit_service._safe("a", lambda: 1 / 0, None, errors)
        cockpit_service._safe("b", lambda: [][0], None, errors)
        assert len(errors) == 2
        assert "a" in errors[0]
        assert "b" in errors[1]


class TestBuildContract:
    """build() must return a dict with all required sections."""

    def test_build_returns_all_sections(self, db):
        _seed_goal(db)
        result = cockpit_service.build(db)

        required_keys = [
            "as_of", "cashflow", "drafts", "holdings", "quadrant",
            "alerts", "plans", "theme_exposure", "rebalance_suggestions", "errors",
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

    def test_build_with_empty_db(self, db):
        _seed_goal(db)
        result = cockpit_service.build(db)

        assert isinstance(result["drafts"], list)
        assert isinstance(result["holdings"], dict)
        assert isinstance(result["alerts"], dict)
        assert isinstance(result["plans"], list)
        assert isinstance(result["errors"], list)

    def test_build_holdings_structure(self, db):
        _seed_goal(db)
        result = cockpit_service.build(db)
        holdings = result["holdings"]

        assert "items" in holdings
        assert "warnings" in holdings
        assert isinstance(holdings["items"], list)

    def test_build_includes_portfolio_risk(self, db):
        """D4 (2026-06-17): Cockpit 必须暴露 portfolio_risk 字段 (invest2 §7)."""
        _seed_goal(db)
        result = cockpit_service.build(db)
        assert "portfolio_risk" in result
        pr = result["portfolio_risk"]
        # Empty DB → no holdings → has_holdings=False
        assert pr["has_holdings"] is False
        assert pr["holdings_count"] == 0
        assert pr["annual_volatility"] is None

    def test_build_alerts_structure(self, db):
        _seed_goal(db)
        result = cockpit_service.build(db)
        alerts = result["alerts"]

        assert "items" in alerts
        assert "unacked_count" in alerts
