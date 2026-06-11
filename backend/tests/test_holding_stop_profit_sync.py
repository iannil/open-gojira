"""Stop-profit AlertRule auto-sync from open holdings.

Verifies that mutating a Holding (create / update / sell / delete) keeps the
[auto-holding] stop_profit rule set in sync — so the user never has to manage
stop_profit alert rules by hand.
"""

from datetime import date

from app.models.alert import AlertRule
from app.models.holding import Holding
from app.models.stock import Stock
from app.services import alert_service, holding_service
from tests.conftest import TestSessionLocal


def _seed_stock(db, code, name, industry=None):
    s = Stock(code=code, name=name, industry=industry)
    db.add(s)
    db.commit()
    return s


def _auto_rules(db):
    return (
        db.query(AlertRule)
        .filter(
            AlertRule.rule_type == "stop_profit",
            AlertRule.note.like(f"{alert_service.AUTO_HOLDING_NOTE_PREFIX}%"),
        )
        .all()
    )


def test_create_holding_syncs_stop_profit_rule():
    db = TestSessionLocal()
    try:
        _seed_stock(db, "600519", "贵州茅台")
        holding_service.create_holding(
            db,
            {
                "stock_code": "600519",
                "buy_date": date(2025, 1, 10),
                "buy_price": 1500.0,
                "quantity": 100,
                "stop_profit_price": 2000.0,
            },
        )
        rules = _auto_rules(db)
        assert len(rules) == 1
        assert rules[0].stock_code == "600519"
        assert rules[0].params == {"stop_price": 2000.0}
        assert rules[0].enabled is True
    finally:
        db.close()


def test_update_stop_profit_updates_rule_params():
    db = TestSessionLocal()
    try:
        _seed_stock(db, "600519", "贵州茅台")
        h = holding_service.create_holding(
            db,
            {
                "stock_code": "600519",
                "buy_date": date(2025, 1, 10),
                "buy_price": 1500.0,
                "quantity": 100,
                "stop_profit_price": 2000.0,
            },
        )
        holding_service.update_holding(db, h.id, {"stop_profit_price": 1800.0})
        rules = _auto_rules(db)
        assert len(rules) == 1
        assert rules[0].params == {"stop_price": 1800.0}
    finally:
        db.close()


def test_two_lots_same_stock_use_minimum_stop_price():
    db = TestSessionLocal()
    try:
        _seed_stock(db, "600519", "贵州茅台")
        holding_service.create_holding(
            db,
            {
                "stock_code": "600519",
                "buy_date": date(2025, 1, 10),
                "buy_price": 1500.0,
                "quantity": 100,
                "stop_profit_price": 2200.0,
            },
        )
        holding_service.create_holding(
            db,
            {
                "stock_code": "600519",
                "buy_date": date(2025, 3, 10),
                "buy_price": 1700.0,
                "quantity": 100,
                "stop_profit_price": 1900.0,
            },
        )
        rules = _auto_rules(db)
        assert len(rules) == 1
        # earliest take-profit wins so the alert fires on the lower threshold
        assert rules[0].params == {"stop_price": 1900.0}
    finally:
        db.close()


def test_sell_holding_removes_auto_rule():
    db = TestSessionLocal()
    try:
        _seed_stock(db, "600519", "贵州茅台")
        h = holding_service.create_holding(
            db,
            {
                "stock_code": "600519",
                "buy_date": date(2025, 1, 10),
                "buy_price": 1500.0,
                "quantity": 100,
                "stop_profit_price": 2000.0,
            },
        )
        assert len(_auto_rules(db)) == 1
        holding_service.sell_holding(
            db, h.id, sell_date=date(2025, 6, 1), sell_price=1950.0
        )
        assert _auto_rules(db) == []
    finally:
        db.close()


def test_delete_holding_removes_auto_rule():
    db = TestSessionLocal()
    try:
        _seed_stock(db, "600519", "贵州茅台")
        h = holding_service.create_holding(
            db,
            {
                "stock_code": "600519",
                "buy_date": date(2025, 1, 10),
                "buy_price": 1500.0,
                "quantity": 100,
                "stop_profit_price": 2000.0,
            },
        )
        assert len(_auto_rules(db)) == 1
        holding_service.delete_holding(db, h.id)
        assert _auto_rules(db) == []
    finally:
        db.close()


def test_zero_stop_profit_creates_no_rule():
    db = TestSessionLocal()
    try:
        _seed_stock(db, "600519", "贵州茅台")
        # bypass create_holding service to avoid industry cap; direct insert
        db.add(
            Holding(
                stock_code="600519",
                buy_date=date(2025, 1, 10),
                buy_price=1500.0,
                quantity=100,
                stop_profit_price=0.0,
            )
        )
        db.commit()
        alert_service.sync_stop_profit_rules_from_holdings(db)
        assert _auto_rules(db) == []
    finally:
        db.close()
