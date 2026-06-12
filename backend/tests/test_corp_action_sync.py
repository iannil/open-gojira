"""Test corp_action_sync_service — sync from Lixinger + delist detection."""
from datetime import date
import pytest

from app.models.corp_action import CorpAction
from app.models.stock import Stock
from app.services.corp_action_sync_service import (
    sync_dividends_for_stock, sync_dividends_batch,
    detect_delistings, _parse_dividend_record,
)


@pytest.fixture
def setup(db_session):
    db_session.add(Stock(code="600519", name="贵州茅台", exchange="sh"))
    db_session.flush()


def test_parse_cash_dividend():
    record = {
        "date": "2026-07-15",
        "exDate": "2026-07-15",
        "dividend": 25.0,  # 每股派 25 元
        "bonusSharesFromProfit": 0,
        "bonusSharesFromCapitalReserve": 0,
    }
    parsed = _parse_dividend_record("600519", record)
    assert parsed is not None
    assert parsed[0]["action_type"] == "cash_dividend"
    assert parsed[0]["ex_date"] == date(2026, 7, 15)
    assert parsed[0]["params_json"]["per_share"] == 25.0


def test_parse_stock_dividend():
    record = {
        "exDate": "2026-07-15",
        "dividend": 0,
        "bonusSharesFromProfit": 5.0,  # 10 送 5
        "bonusSharesFromCapitalReserve": 0,
    }
    parsed = _parse_dividend_record("600519", record)
    assert parsed[0]["action_type"] == "stock_dividend"
    assert parsed[0]["params_json"]["per_10_shares"] == 5.0


def test_parse_capitalization():
    record = {
        "exDate": "2026-07-15",
        "dividend": 0,
        "bonusSharesFromProfit": 0,
        "bonusSharesFromCapitalReserve": 10.0,  # 10 转 10
    }
    parsed = _parse_dividend_record("600519", record)
    assert parsed[0]["action_type"] == "capitalization"
    assert parsed[0]["params_json"]["per_10_shares"] == 10.0


def test_parse_mixed_cash_and_stock():
    """A 股常见:10送5派25(送股 + 现金)."""
    record = {
        "exDate": "2026-07-15",
        "dividend": 25.0,
        "bonusSharesFromProfit": 5.0,
        "bonusSharesFromCapitalReserve": 0,
    }
    parsed = _parse_dividend_record("600519", record)
    # 应该生成 2 条 corp_action(cash + stock)
    assert isinstance(parsed, list)
    types = [p["action_type"] for p in parsed]
    assert "cash_dividend" in types
    assert "stock_dividend" in types


def test_parse_skips_zero_action():
    """All-zero record should be skipped (no actual distribution)."""
    record = {
        "exDate": "2026-07-15",
        "dividend": 0,
        "bonusSharesFromProfit": 0,
        "bonusSharesFromCapitalReserve": 0,
    }
    parsed = _parse_dividend_record("600519", record)
    assert parsed is None or parsed == []


def test_sync_dividends_for_stock(db_session, setup, monkeypatch):
    """Sync 3 records for one stock."""
    fake_records = [
        {"exDate": "2024-07-15", "dividend": 25.0,
         "bonusSharesFromProfit": 0, "bonusSharesFromCapitalReserve": 0},
        {"exDate": "2025-07-15", "dividend": 25.0,
         "bonusSharesFromProfit": 0, "bonusSharesFromCapitalReserve": 0},
        {"exDate": "2026-07-15", "dividend": 30.0,
         "bonusSharesFromProfit": 0, "bonusSharesFromCapitalReserve": 0},
    ]
    from app.services import corp_action_sync_service as svc
    class FakeClient:
        def get_dividend_full(self, code, start, end):
            return fake_records
    monkeypatch.setattr(svc, "get_lixinger_client", lambda: FakeClient())

    count = sync_dividends_for_stock(db_session, "600519")
    db_session.commit()
    assert count == 3
    assert db_session.query(CorpAction).count() == 3


def test_sync_idempotent(db_session, setup, monkeypatch):
    """Re-running sync should not duplicate."""
    fake_records = [
        {"exDate": "2026-07-15", "dividend": 25.0,
         "bonusSharesFromProfit": 0, "bonusSharesFromCapitalReserve": 0},
    ]
    from app.services import corp_action_sync_service as svc
    class FakeClient:
        def get_dividend_full(self, code, start, end):
            return fake_records
    monkeypatch.setattr(svc, "get_lixinger_client", lambda: FakeClient())

    sync_dividends_for_stock(db_session, "600519")
    db_session.commit()
    count2 = sync_dividends_for_stock(db_session, "600519")
    db_session.commit()
    assert count2 == 0
    assert db_session.query(CorpAction).count() == 1


def test_sync_dividends_batch(db_session, setup, monkeypatch):
    """Batch sync multiple stocks."""
    db_session.add(Stock(code="000001", name="平安银行", exchange="sz"))
    db_session.flush()
    fake = {
        "600519": [{"exDate": "2026-07-15", "dividend": 25.0,
                    "bonusSharesFromProfit": 0, "bonusSharesFromCapitalReserve": 0}],
        "000001": [{"exDate": "2026-07-20", "dividend": 2.5,
                    "bonusSharesFromProfit": 0, "bonusSharesFromCapitalReserve": 0}],
    }
    from app.services import corp_action_sync_service as svc
    class FakeClient:
        def get_dividend_full(self, code, start, end):
            return fake.get(code, [])
    monkeypatch.setattr(svc, "get_lixinger_client", lambda: FakeClient())

    count = sync_dividends_batch(db_session, ["600519", "000001"])
    db_session.commit()
    assert count == 2


def test_detect_delistings_finds_missing(db_session, monkeypatch):
    """If a stock in DB is missing from Lixinger's list, flag as delisted."""
    db_session.add(Stock(code="600432", name="吉恩镍业", exchange="sh"))
    db_session.flush()
    # Lixinger returns list WITHOUT 600432
    from app.services import corp_action_sync_service as svc
    class FakeClient:
        def get_company_list_all(self):
            return [{"stockCode": "600519"}, {"stockCode": "000001"}]
        def get_company_profile(self, code):
            return {
                "historyStockNames": [
                    {"name": "吉恩镍业", "date": "2010-01-01"},
                    {"name": "退市吉恩", "date": "2018-07-11"},
                ],
            }
    monkeypatch.setattr(svc, "get_lixinger_client", lambda: FakeClient())

    detected = detect_delistings(db_session)
    db_session.commit()
    assert len(detected) == 1
    assert detected[0].stock_code == "600432"
    assert detected[0].action_type == "delist"
    # ex_date 应该从 historyStockNames 推断
    assert detected[0].ex_date == date(2018, 7, 11)
    assert "退市" in detected[0].params_json.get("new_name", "")


def test_detect_delistings_ignores_already_present(db_session, monkeypatch):
    db_session.add(Stock(code="600519", name="贵州茅台", exchange="sh"))
    db_session.flush()
    from app.services import corp_action_sync_service as svc
    class FakeClient:
        def get_company_list_all(self):
            return [{"stockCode": "600519"}]  # 600519 still listed
    monkeypatch.setattr(svc, "get_lixinger_client", lambda: FakeClient())
    detected = detect_delistings(db_session)
    assert len(detected) == 0


def test_detect_delistings_idempotent(db_session, monkeypatch):
    """If corp_action already exists, don't duplicate."""
    from datetime import date as d
    db_session.add(Stock(code="600432", name="吉恩镍业", exchange="sh"))
    db_session.add(CorpAction(
        stock_code="600432", ex_date=d(2018, 7, 11),
        action_type="delist", params_json={"new_name": "退市吉恩"},
        source="heuristic",
    ))
    db_session.flush()
    from app.services import corp_action_sync_service as svc
    class FakeClient:
        def get_company_list_all(self):
            return [{"stockCode": "600519"}]
        def get_company_profile(self, code):
            return {"historyStockNames": [
                {"name": "吉恩镍业", "date": "2010-01-01"},
                {"name": "退市吉恩", "date": "2018-07-11"},
            ]}
    monkeypatch.setattr(svc, "get_lixinger_client", lambda: FakeClient())
    detected = detect_delistings(db_session)
    assert len(detected) == 0  # already exists
