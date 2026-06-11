"""Tests for portfolio rebalancing service.

Position-level rebalancing removed (was based on per-stock Plans).
Only quadrant and theme levels are tested.
"""

import json
from datetime import date

import pytest

from app.models.cashflow_goal import CashflowGoal
from app.models.holding import Holding
from app.models.stock import Stock
from app.models.theme import Theme
from app.services import rebalance_service
from tests.conftest import TestSessionLocal


@pytest.fixture
def db():
    s = TestSessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def sample_stock(db):
    stock = Stock(code="600000", name="浦发银行", industry="银行", quadrant="金融", security_theme="金融")
    db.add(stock)
    db.commit()
    return stock


@pytest.fixture
def tech_stock(db):
    stock = Stock(code="300750", name="宁德时代", industry="电池", quadrant="科技", security_theme="新能源")
    db.add(stock)
    db.commit()
    return stock


def test_no_suggestions_for_empty_portfolio(db):
    suggestions = rebalance_service.compute_rebalancing_suggestions(db, drift_threshold=0.05)
    assert len(suggestions) == 0


def test_quadrant_level_rebalancing(db, sample_stock, tech_stock):
    from unittest.mock import patch

    goal = CashflowGoal(
        id=1, annual_expense=100000.0, goal_multiple=15.0,
        quadrant_targets_json=json.dumps({"金融": 0.30, "科技": 0.25, "消费": 0.25, "周期": 0.20}),
    )
    db.add(goal)
    db.commit()

    def mock_quadrant_breakdown(db_session):
        return [
            {"quadrant": "金融", "weight_pct": 40.0, "value": 40000.0, "count": 1, "stock_codes": [sample_stock.code]},
            {"quadrant": "科技", "weight_pct": 60.0, "value": 60000.0, "count": 1, "stock_codes": [tech_stock.code]},
        ]

    def mock_summary(db_session):
        return {"holdings": [], "total_value": 100000.0}

    with patch("app.services.rebalance_service.cashflow_service.quadrant_breakdown", mock_quadrant_breakdown), \
         patch("app.services.rebalance_service.holding_service.get_portfolio_summary", mock_summary):
        suggestions = rebalance_service.compute_rebalancing_suggestions(db, drift_threshold=0.05)

    quadrant_sugs = [s for s in suggestions if s.level == "quadrant"]
    assert len(quadrant_sugs) >= 1

    finance_sug = next((s for s in quadrant_sugs if s.quadrant == "金融"), None)
    assert finance_sug is not None
    assert finance_sug.current_pct == 0.40
    assert finance_sug.target_pct == 0.30
    assert finance_sug.drift_pct == pytest.approx(0.10, abs=0.01)
    assert finance_sug.action == "减持"
    assert finance_sug.priority == "high"


def test_theme_level_rebalancing(db, sample_stock):
    from unittest.mock import patch

    theme = Theme(name="金融", description="金融行业", target_weight_pct=30.0)
    db.add(theme)
    db.commit()

    def mock_theme_targets(db_session):
        return [{"theme": "金融", "target_pct": 30.0, "actual_pct": 40.0, "drift_pct": 10.0, "warning": "超配 10.0%"}]

    def mock_summary(db_session):
        return {"holdings": [], "total_value": 100000.0}

    with patch("app.services.rebalance_service.theme_service.get_theme_targets", mock_theme_targets), \
         patch("app.services.rebalance_service.holding_service.get_portfolio_summary", mock_summary):
        suggestions = rebalance_service.compute_rebalancing_suggestions(db, drift_threshold=0.05)

    theme_sugs = [s for s in suggestions if s.level == "theme"]
    assert len(theme_sugs) >= 1

    sug = theme_sugs[0]
    assert sug.theme == "金融"
    assert sug.current_pct == 0.40
    assert sug.target_pct == 0.30
    assert sug.priority == "high"


def test_suggestions_sorted_by_drift_magnitude(db):
    from unittest.mock import patch

    def mock_summary(db_session):
        return {"holdings": [], "total_value": 100000.0}

    def mock_quadrant_breakdown(db_session):
        return []

    def mock_theme_targets(db_session):
        return [
            {"theme": "A", "target_pct": 10.0, "actual_pct": 30.0, "drift_pct": 20.0, "warning": None},
            {"theme": "B", "target_pct": 20.0, "actual_pct": 15.0, "drift_pct": -5.0, "warning": None},
            {"theme": "C", "target_pct": 15.0, "actual_pct": 35.0, "drift_pct": 20.0, "warning": None},
        ]

    with patch("app.services.rebalance_service.holding_service.get_portfolio_summary", mock_summary), \
         patch("app.services.rebalance_service.cashflow_service.quadrant_breakdown", mock_quadrant_breakdown), \
         patch("app.services.rebalance_service.theme_service.get_theme_targets", mock_theme_targets):
        suggestions = rebalance_service.compute_rebalancing_suggestions(db, drift_threshold=0.01)

    if len(suggestions) >= 2:
        assert abs(suggestions[0].drift_pct) >= abs(suggestions[1].drift_pct)


def test_priority_levels(db):
    from unittest.mock import patch

    def mock_summary(db_session):
        return {"holdings": [], "total_value": 100000.0}

    def mock_quadrant_breakdown(db_session):
        return []

    def mock_theme_targets(db_session):
        return [
            {"theme": "High", "target_pct": 10.0, "actual_pct": 26.0, "drift_pct": 16.0, "warning": None},
            {"theme": "Medium", "target_pct": 20.0, "actual_pct": 26.0, "drift_pct": 6.0, "warning": None},
            {"theme": "Low", "target_pct": 30.0, "actual_pct": 32.0, "drift_pct": 2.0, "warning": None},
        ]

    with patch("app.services.rebalance_service.holding_service.get_portfolio_summary", mock_summary), \
         patch("app.services.rebalance_service.cashflow_service.quadrant_breakdown", mock_quadrant_breakdown), \
         patch("app.services.rebalance_service.theme_service.get_theme_targets", mock_theme_targets):
        suggestions = rebalance_service.compute_rebalancing_suggestions(db, drift_threshold=0.01)

    high_sug = next((s for s in suggestions if s.theme == "High"), None)
    medium_sug = next((s for s in suggestions if s.theme == "Medium"), None)
    low_sug = next((s for s in suggestions if s.theme == "Low"), None)

    assert high_sug is not None
    assert medium_sug is not None
    assert low_sug is not None

    assert high_sug.priority == "high"
    assert medium_sug.priority == "medium"
    assert low_sug.priority == "low"


def test_generate_rebalancing_alerts(db):
    from unittest.mock import patch

    def mock_summary(db_session):
        return {"holdings": [], "total_value": 100000.0}

    def mock_quadrant_breakdown(db_session):
        return []

    def mock_theme_targets(db_session):
        return []

    with patch("app.services.rebalance_service.holding_service.get_portfolio_summary", mock_summary), \
         patch("app.services.rebalance_service.cashflow_service.quadrant_breakdown", mock_quadrant_breakdown), \
         patch("app.services.rebalance_service.theme_service.get_theme_targets", mock_theme_targets):
        result = rebalance_service.generate_rebalancing_alerts(db, drift_threshold=0.05)

    assert "total_suggestions" in result
    assert "high_priority" in result
    assert "medium_priority" in result
    assert "suggestions" in result
    assert isinstance(result["suggestions"], list)
