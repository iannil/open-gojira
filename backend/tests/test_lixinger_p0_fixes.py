"""P0-4 regressions: dashboard cross-endpoint fallback + FS unique constraint."""

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.financial import FinancialStatement
from app.models.stock import Stock
from app.services import data_service
from app.services import lixinger_client as lixinger_module
from app.services import valuation_service
from tests.conftest import TestSessionLocal


# ── D1/D2: cross-endpoint fallback ─────────────────────────────────────────


class _FakeClient:
    """Returns the next queued response per call; raises if exhausted."""

    def __init__(self, scripted):
        self._scripted = scripted
        self.calls: list[str] = []

    def get_fundamentals_at_endpoint(self, endpoint_kind, stock_codes, metrics):
        self.calls.append(endpoint_kind)
        try:
            payload = self._scripted.pop(0)
        except IndexError:
            return []
        if isinstance(payload, Exception):
            raise payload
        return payload


def _patch_dashboard_deps(monkeypatch, client, *, percentiles=None):
    # get_lixinger_client is imported lazily inside the function — patch the
    # source module so the late import sees our fake.
    monkeypatch.setattr(lixinger_module, "get_lixinger_client", lambda: client)

    def _no_history(*args, **kwargs):
        return []

    monkeypatch.setattr(data_service, "fetch_pe_pb_history", _no_history)
    if percentiles is not None:
        monkeypatch.setattr(
            valuation_service, "calculate_percentiles", lambda h: percentiles
        )


def test_dashboard_resolves_via_fallback_when_primary_returns_allnone(monkeypatch):
    """Blue-chip case: stock industry says non_financial but primary returns
    an all-None row; bank endpoint then resolves it."""
    db = TestSessionLocal()
    try:
        db.add(Stock(code="600028", name="中国石化", industry="石油石化"))
        db.commit()

        scripted = [
            [{"stockCode": "600028", "pe_ttm": None, "pb": None, "sp": None}],
            [{"stockCode": "600028", "pe_ttm": 8.5, "pb": 0.9, "sp": 7.20}],
        ]
        client = _FakeClient(scripted)
        _patch_dashboard_deps(monkeypatch, client)

        result = valuation_service.get_valuation_dashboard(db, "600028")
        assert result["current_pe"] == 8.5
        assert result["current_pb"] == 0.9
        assert result["current_price"] == 7.20
        # Tried non_financial first, then the next kind in the fallback list
        assert client.calls[0] == "non_financial"
        assert len(client.calls) >= 2
    finally:
        db.close()


def test_dashboard_uses_primary_when_it_returns_data(monkeypatch):
    """No fallback triggered when primary endpoint succeeds."""
    db = TestSessionLocal()
    try:
        db.add(Stock(code="600036", name="招商银行", industry="银行"))
        db.commit()

        scripted = [
            [{"stockCode": "600036", "pe_ttm": 6.1, "pb": 0.95, "sp": 42.5}],
        ]
        client = _FakeClient(scripted)
        _patch_dashboard_deps(monkeypatch, client)

        result = valuation_service.get_valuation_dashboard(db, "600036")
        assert result["current_pe"] == 6.1
        assert client.calls == ["bank"]
    finally:
        db.close()


def test_dashboard_returns_none_when_all_endpoints_fail(monkeypatch):
    """Every fallback is empty → result has no realtime fields populated."""
    db = TestSessionLocal()
    try:
        db.add(Stock(code="000001", name="平安银行", industry="银行"))
        db.commit()

        client = _FakeClient([[], [], [], [], []])
        _patch_dashboard_deps(monkeypatch, client)

        result = valuation_service.get_valuation_dashboard(db, "000001")
        assert result.get("current_pe") is None
        assert result.get("current_price") is None
    finally:
        db.close()


# ── D3: FinancialStatement unique constraint ───────────────────────────────


def test_financial_statement_unique_constraint_rejects_duplicates():
    db = TestSessionLocal()
    try:
        d = datetime(2024, 12, 31)
        db.add(FinancialStatement(stock_code="600519", report_date=d, report_type="annual"))
        db.commit()
        db.add(FinancialStatement(stock_code="600519", report_date=d, report_type="annual"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.close()


def test_financial_statement_allows_distinct_report_type():
    """Annual and quarterly with the same date are different rows."""
    db = TestSessionLocal()
    try:
        d = datetime(2024, 12, 31)
        db.add(FinancialStatement(stock_code="600519", report_date=d, report_type="annual"))
        db.add(FinancialStatement(stock_code="600519", report_date=d, report_type="quarterly"))
        db.commit()
        assert db.query(FinancialStatement).count() == 2
    finally:
        db.close()
