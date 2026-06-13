"""Test corp_actions API endpoints (S4A.4)."""
from datetime import date, datetime

from app.models.broker_fee_config import BrokerFeeConfig
from app.models.cash_balance import CashBalance
from app.models.corp_action import CorpAction
from app.models.stock import Stock
from app.services.trade_service import record_trade


def _setup_market(db_session):
    """Seed a single stock + cash balance + fee config needed for trades."""
    db_session.add(Stock(
        code="600519", name="贵州茅台", exchange="sh",
        listing_status="normally_listed", prev_close=100.0,
    ))
    db_session.add(CashBalance(id=1, balance=100000.0))
    db_session.add(BrokerFeeConfig(
        broker_name="default", commission_rate=0.00025, commission_min=5.0,
        stamp_duty_rate=0.0005, transfer_fee_rate=0.00001,
        effective_from=date(2023, 10, 23), is_active=True,
    ))
    db_session.flush()


def test_list_corp_actions(client, db_session):
    _setup_market(db_session)
    db_session.add(CorpAction(
        stock_code="600519", ex_date=date(2026, 7, 15),
        action_type="cash_dividend", params_json={"per_share": 5.0},
        source="lixinger",
    ))
    db_session.flush()

    resp = client.get("/api/corp-actions")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["stock_code"] == "600519"
    assert data[0]["action_type"] == "cash_dividend"
    assert data[0]["params_json"] == {"per_share": 5.0}
    assert data[0]["source"] == "lixinger"


def test_list_pending(client, db_session):
    _setup_market(db_session)
    # 1 pending + 1 processed
    db_session.add(CorpAction(
        stock_code="600519", ex_date=date(2026, 7, 15),
        action_type="cash_dividend", params_json={"per_share": 5.0},
        source="lixinger",
    ))
    db_session.add(CorpAction(
        stock_code="600519", ex_date=date(2026, 6, 15),
        action_type="cash_dividend", params_json={"per_share": 4.0},
        source="lixinger", processed_at=datetime(2026, 6, 16, 9, 0),
    ))
    db_session.flush()

    resp = client.get("/api/corp-actions/pending")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["ex_date"] == "2026-07-15"


def test_filter_by_action_type(client, db_session):
    _setup_market(db_session)
    db_session.add(CorpAction(
        stock_code="600519", ex_date=date(2026, 7, 15),
        action_type="cash_dividend", params_json={"per_share": 5.0},
        source="lixinger",
    ))
    db_session.add(CorpAction(
        stock_code="600519", ex_date=date(2026, 7, 20),
        action_type="stock_dividend", params_json={"per_10_shares": 5.0},
        source="lixinger",
    ))
    db_session.flush()

    resp = client.get("/api/corp-actions?action_type=cash_dividend")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["action_type"] == "cash_dividend"


def test_filter_by_status(client, db_session):
    _setup_market(db_session)
    db_session.add(CorpAction(
        stock_code="600519", ex_date=date(2026, 7, 15),
        action_type="cash_dividend", params_json={"per_share": 5.0},
        source="lixinger",
    ))
    db_session.add(CorpAction(
        stock_code="600519", ex_date=date(2026, 6, 15),
        action_type="cash_dividend", params_json={"per_share": 4.0},
        source="lixinger", processed_at=datetime(2026, 6, 16, 9, 0),
    ))
    db_session.flush()

    pending = client.get("/api/corp-actions?status=pending").json()
    assert len(pending) == 1
    assert pending[0]["ex_date"] == "2026-07-15"

    processed = client.get("/api/corp-actions?status=processed").json()
    assert len(processed) == 1
    assert processed[0]["ex_date"] == "2026-06-15"


def test_filter_by_stock_code(client, db_session):
    _setup_market(db_session)
    db_session.add(Stock(
        code="000001", name="平安银行", exchange="sz",
        listing_status="normally_listed", prev_close=10.0,
    ))
    db_session.flush()
    db_session.add(CorpAction(
        stock_code="600519", ex_date=date(2026, 7, 15),
        action_type="cash_dividend", params_json={"per_share": 5.0},
        source="lixinger",
    ))
    db_session.add(CorpAction(
        stock_code="000001", ex_date=date(2026, 7, 15),
        action_type="cash_dividend", params_json={"per_share": 0.2},
        source="lixinger",
    ))
    db_session.flush()

    resp = client.get("/api/corp-actions?stock_code=600519")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["stock_code"] == "600519"


def test_get_corp_action_not_found(client, db_session):
    _setup_market(db_session)
    resp = client.get("/api/corp-actions/99999")
    assert resp.status_code == 404


def test_process_one_endpoint(client, db_session):
    _setup_market(db_session)
    record_trade(
        db_session, stock_code="600519", side="BUY",
        price=100.0, quantity=100,
        filled_at=datetime(2026, 1, 15, 10, 0), source="manual",
    )
    ca = CorpAction(
        stock_code="600519", ex_date=date(2026, 7, 15),
        action_type="cash_dividend", params_json={"per_share": 5.0},
        source="lixinger",
    )
    db_session.add(ca)
    db_session.flush()

    resp = client.post(f"/api/corp-actions/{ca.id}/process")
    assert resp.status_code == 200
    data = resp.json()
    assert data["processed_at"] is not None
    assert data["applied_trade_id"] is not None


def test_process_one_not_found(client, db_session):
    _setup_market(db_session)
    resp = client.post("/api/corp-actions/99999/process")
    assert resp.status_code == 404


def test_process_pending_endpoint(client, db_session):
    _setup_market(db_session)
    record_trade(
        db_session, stock_code="600519", side="BUY",
        price=100.0, quantity=100,
        filled_at=datetime(2026, 1, 15, 10, 0), source="manual",
    )
    db_session.add(CorpAction(
        stock_code="600519", ex_date=date(2026, 7, 15),
        action_type="cash_dividend", params_json={"per_share": 5.0},
        source="lixinger",
    ))
    db_session.add(CorpAction(
        stock_code="600519", ex_date=date(2026, 6, 15),
        action_type="cash_dividend", params_json={"per_share": 4.0},
        source="lixinger",
    ))
    db_session.flush()

    resp = client.post("/api/corp-actions/process-pending")
    assert resp.status_code == 200
    assert resp.json()["processed_count"] == 2


def test_sync_dividends_endpoint(client, db_session, monkeypatch):
    """Manual trigger of dividend sync."""
    _setup_market(db_session)
    fake_records = [
        {
            "exDate": "2026-07-15", "dividend": 25.0,
            "bonusSharesFromProfit": 0, "bonusSharesFromCapitalReserve": 0,
        },
    ]
    from app.services import corp_action_sync_service as svc

    class FakeClient:
        def get_dividend_full(self, code, start, end):
            return fake_records

    monkeypatch.setattr(svc, "get_lixinger_client", lambda: FakeClient())

    resp = client.post(
        "/api/corp-actions/sync-dividends",
        json={"stock_codes": ["600519"]},
    )
    assert resp.status_code == 200
    assert resp.json()["new_count"] == 1
