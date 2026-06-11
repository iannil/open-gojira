"""Step 3A: cashflow_service + cockpit_service tests."""

from datetime import date

import pytest

from app.models.cashflow_goal import CashflowGoal
from app.models.holding import Holding
from app.models.stock import Stock
from app.models.valuation import ValuationSnapshot
from app.services import (
    cashflow_goal_service,
    cashflow_service,
    cockpit_service,
)
from tests.conftest import TestSessionLocal


@pytest.fixture(autouse=True)
def _no_realtime_price(monkeypatch):
    """holding_service caches realtime prices from Lixinger across the process;
    force a fresh None lookup so current_value = quantity × buy_price in tests."""
    from app.services import holding_service

    holding_service._price_cache.clear()
    monkeypatch.setattr(
        holding_service, "_get_cached_price", lambda code: None
    )


@pytest.fixture
def db():
    s = TestSessionLocal()
    try:
        yield s
    finally:
        s.close()


def _seed_holding(
    db,
    *,
    code: str,
    name: str,
    industry: str,
    quadrant: str | None,
    qty: int,
    buy_price: float,
    dyr: float | None = 0.05,
):
    db.add(
        Stock(code=code, name=name, industry=industry, quadrant=quadrant)
    )
    db.add(
        Holding(
            stock_code=code,
            buy_date=date(2025, 1, 1),
            buy_price=buy_price,
            quantity=qty,
            stop_profit_price=999.0,
        )
    )
    if dyr is not None:
        db.add(
            ValuationSnapshot(
                stock_code=code,
                date=date(2026, 6, 6),
                pe_ttm=5.0,
                pb=0.5,
                pe_percentile_10y=0.20,
                pb_percentile_10y=0.25,
                dividend_yield=dyr,
            )
        )


# ── cashflow_service.compute ──────────────────────────────────────────


def test_compute_empty_portfolio(db):
    m = cashflow_service.compute(db)
    assert m.annual_expense == 0.0
    assert m.goal_multiple == 15.0
    assert m.target_annual_cashflow == 0.0
    assert m.total_portfolio_value == 0.0
    assert m.weighted_dyr is None
    assert m.annual_passive_cashflow == 0.0
    assert m.goal_progress is None
    assert m.currency == "CNY"


def test_compute_with_holdings_and_goal(db):
    cashflow_goal_service.update(db, annual_expense=120_000, goal_multiple=15)
    _seed_holding(
        db, code="601398", name="工商银行", industry="银行",
        quadrant="financial", qty=10_000, buy_price=5.0, dyr=0.06,
    )
    db.commit()

    m = cashflow_service.compute(db)
    assert m.target_annual_cashflow == 1_800_000  # 120k × 15
    assert m.weighted_dyr == pytest.approx(0.06)
    # 10_000 × 5 == 50_000 portfolio; 50_000 × 0.06 == 3_000 annual cf
    assert m.annual_passive_cashflow == pytest.approx(3_000)
    assert m.goal_progress == pytest.approx(3_000 / 1_800_000)


def test_compute_goal_progress_none_when_target_is_zero(db):
    # Default goal has annual_expense=0 → target=0
    _seed_holding(
        db, code="601398", name="工商银行", industry="银行",
        quadrant="financial", qty=1000, buy_price=5.0, dyr=0.06,
    )
    db.commit()
    m = cashflow_service.compute(db)
    assert m.target_annual_cashflow == 0
    assert m.goal_progress is None


def test_compute_includes_cash_reserve_in_total(db):
    cashflow_goal_service.update(db, annual_expense=100_000, goal_multiple=10)
    _seed_holding(
        db, code="601398", name="工商银行", industry="银行",
        quadrant="financial", qty=1000, buy_price=5.0, dyr=0.06,
    )
    # Update existing CashflowGoal with portfolio settings (merged model)
    from app.models.cashflow_goal import CashflowGoal
    goal = db.query(CashflowGoal).filter(CashflowGoal.id == 1).first()
    goal.cash_reserve = 50_000
    goal.target_weighted_dyr = 0.045
    db.commit()
    m = cashflow_service.compute(db)
    # equity = 1000 × 5 = 5000; cash = 50000; total = 55000
    assert m.total_portfolio_value == pytest.approx(55_000)


# ── cashflow_service.quadrant_breakdown ───────────────────────────────


def test_quadrant_breakdown_empty(db):
    assert cashflow_service.quadrant_breakdown(db) == []


def test_quadrant_breakdown_groups_by_label(db):
    _seed_holding(
        db, code="A", name="工商银行", industry="银行",
        quadrant="financial", qty=10_000, buy_price=5.0,
    )
    _seed_holding(
        db, code="B", name="紫金矿业", industry="资源",
        quadrant="procyclical", qty=5_000, buy_price=10.0,
    )
    _seed_holding(
        db, code="C", name="某股", industry="未分", quadrant=None,
        qty=1_000, buy_price=20.0,
    )
    db.commit()
    buckets = cashflow_service.quadrant_breakdown(db)
    by_label = {b["quadrant"]: b for b in buckets}
    # 50k + 50k + 20k = 120k total
    assert by_label["financial"]["weight_pct"] == pytest.approx(50_000 / 120_000 * 100)
    assert by_label["procyclical"]["weight_pct"] == pytest.approx(50_000 / 120_000 * 100)
    assert by_label["unlabeled"]["weight_pct"] == pytest.approx(20_000 / 120_000 * 100)
    # Sorted descending by weight
    assert buckets[0]["weight_pct"] >= buckets[-1]["weight_pct"]


# ── cockpit_service.build ─────────────────────────────────────────────


def test_cockpit_build_has_all_top_level_keys(db):
    payload = cockpit_service.build(db)
    assert set(payload.keys()) >= {
        "as_of",
        "cashflow",
        "drafts",
        "holdings",
        "quadrant",
        "alerts",
        "plans",
        "errors",
    }


def test_cockpit_build_empty_session_has_no_errors(db):
    payload = cockpit_service.build(db)
    assert payload["errors"] == []
    assert payload["drafts"] == []
    assert payload["plans"] == []
    assert payload["holdings"]["items"] == []
    assert payload["alerts"]["unacked_count"] == 0


def test_cockpit_cashflow_reflects_goal_and_holdings(db):
    cashflow_goal_service.update(db, annual_expense=100_000, goal_multiple=10)
    _seed_holding(
        db, code="601398", name="工商银行", industry="银行",
        quadrant="financial", qty=10_000, buy_price=5.0, dyr=0.05,
    )
    db.commit()
    payload = cockpit_service.build(db)
    cf = payload["cashflow"]
    assert cf["target_annual_cashflow"] == 1_000_000
    assert cf["weighted_dyr"] == pytest.approx(0.05)
    assert cf["annual_passive_cashflow"] == pytest.approx(2_500)


def test_cockpit_quadrant_section_matches_breakdown(db):
    _seed_holding(
        db, code="601398", name="工商银行", industry="银行",
        quadrant="financial", qty=1000, buy_price=5.0,
    )
    db.commit()
    payload = cockpit_service.build(db)
    assert len(payload["quadrant"]) == 1
    assert payload["quadrant"][0]["quadrant"] == "financial"


def test_cockpit_isolates_section_failures(db, monkeypatch):
    """When a section raises, others still populate and `errors` lists it."""

    def boom(_db):
        raise RuntimeError("quadrant broken")

    monkeypatch.setattr(
        "app.services.cockpit_service.cashflow_service.quadrant_breakdown",
        boom,
    )
    payload = cockpit_service.build(db)
    assert payload["quadrant"] == []
    assert any("quadrant" in e for e in payload["errors"])
    # Other sections still populated
    assert "cashflow" in payload
