"""Tests for thesis_monitor_service — 论点变量阈值越界检测."""

import json
import pytest
from datetime import date

from tests.conftest import TestSessionLocal
from app.models.holding import Holding
from app.models.stock import Stock
from app.services.thesis_monitor_service import (
    parse_thesis_variables,
    check_variable,
    check_held_stocks,
)


@pytest.fixture
def db():
    session = TestSessionLocal()
    yield session
    session.close()


class TestParseThesisVariables:
    def test_none_returns_empty(self):
        assert parse_thesis_variables(None) == []

    def test_empty_string_returns_empty(self):
        assert parse_thesis_variables("") == []

    def test_invalid_json_returns_empty(self):
        assert parse_thesis_variables("not json") == []

    def test_dict_with_variables_key(self):
        raw = json.dumps({
            "variables": [{"name": "煤油比", "value": 3.5}]
        })
        result = parse_thesis_variables(raw)
        assert len(result) == 1
        assert result[0]["name"] == "煤油比"

    def test_list_format(self):
        raw = json.dumps([{"name": "x", "value": 1.0}])
        result = parse_thesis_variables(raw)
        assert len(result) == 1


class TestCheckVariable:
    def test_no_thresholds_returns_none(self):
        assert check_variable({"value": 3.5, "direction": "above"}) is None

    def test_above_direction_warning(self):
        var = {"value": 2.5, "direction": "above", "threshold_low": 3.0}
        assert check_variable(var) == "warning"

    def test_above_direction_critical(self):
        var = {"value": 1.4, "direction": "above", "threshold_low": 2.0, "threshold_critical": 1.5}
        assert check_variable(var) == "critical"

    def test_above_direction_ok(self):
        var = {"value": 3.5, "direction": "above", "threshold_low": 2.0, "threshold_critical": 1.5}
        assert check_variable(var) is None

    def test_below_direction_warning(self):
        var = {"value": 8.0, "direction": "below", "threshold_high": 7.0}
        assert check_variable(var) == "warning"

    def test_below_direction_critical(self):
        var = {"value": 10.0, "direction": "below", "threshold_critical": 9.0}
        assert check_variable(var) == "critical"

    def test_below_direction_ok(self):
        var = {"value": 5.0, "direction": "below", "threshold_high": 7.0, "threshold_critical": 9.0}
        assert check_variable(var) is None

    def test_none_value_returns_none(self):
        assert check_variable({"value": None}) is None


class TestCheckHeldStocks:
    def test_no_alerts_when_within_range(self, db):
        db.add(Stock(code="601398", name="工商银行", industry="银行",
                     thesis_variables_json=json.dumps({
                         "variables": [{"name": "煤油比", "value": 3.5, "direction": "above",
                                        "threshold_low": 2.0, "threshold_critical": 1.5}]
                     })))
        db.add(Holding(stock_code="601398", buy_date=date(2025, 1, 1),
                       buy_price=5.0, quantity=1000, stop_profit_price=999.0))
        db.commit()

        alerts = check_held_stocks(db)
        assert len(alerts) == 0

    def test_alerts_when_breach_warning(self, db):
        db.add(Stock(code="601398", name="工商银行", industry="银行",
                     thesis_variables_json=json.dumps({
                         "variables": [{"name": "煤油比", "value": 1.8, "direction": "above",
                                        "threshold_low": 2.0, "threshold_critical": 1.5}]
                     })))
        db.add(Holding(stock_code="601398", buy_date=date(2025, 1, 1),
                       buy_price=5.0, quantity=1000, stop_profit_price=999.0))
        db.commit()

        alerts = check_held_stocks(db)
        assert len(alerts) == 1
        assert alerts[0].threshold_type == "warning"
        assert alerts[0].code == "601398"

    def test_alerts_when_breach_critical(self, db):
        db.add(Stock(code="601398", name="工商银行", industry="银行",
                     thesis_variables_json=json.dumps({
                         "variables": [{"name": "煤油比", "value": 1.2, "direction": "above",
                                        "threshold_low": 2.0, "threshold_critical": 1.5}]
                     })))
        db.add(Holding(stock_code="601398", buy_date=date(2025, 1, 1),
                       buy_price=5.0, quantity=1000, stop_profit_price=999.0))
        db.commit()

        alerts = check_held_stocks(db)
        assert len(alerts) == 1
        assert alerts[0].threshold_type == "critical"

    def test_no_alerts_for_non_held_stocks(self, db):
        db.add(Stock(code="601398", name="工商银行", industry="银行",
                     thesis_variables_json=json.dumps({
                         "variables": [{"name": "煤油比", "value": 1.0, "direction": "above",
                                        "threshold_low": 2.0, "threshold_critical": 1.5}]
                     })))
        # No holding for this stock
        db.commit()

        alerts = check_held_stocks(db)
        assert len(alerts) == 0

    def test_multiple_variables_multiple_alerts(self, db):
        db.add(Stock(code="601398", name="工商银行", industry="银行",
                     thesis_variables_json=json.dumps({
                         "variables": [
                             {"name": "煤油比", "value": 1.2, "direction": "above",
                              "threshold_low": 2.0, "threshold_critical": 1.5},
                             {"name": "PE", "value": 20.0, "direction": "below",
                              "threshold_high": 15.0, "threshold_critical": 18.0},
                         ]
                     })))
        db.add(Holding(stock_code="601398", buy_date=date(2025, 1, 1),
                       buy_price=5.0, quantity=1000, stop_profit_price=999.0))
        db.commit()

        alerts = check_held_stocks(db)
        assert len(alerts) == 2
