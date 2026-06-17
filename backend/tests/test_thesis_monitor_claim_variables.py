"""Tests for thesis_monitor_service.check_claim_variables (Phase 2 #9 阶段 B v2)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.financial import FinancialStatement
from app.models.holding import Holding
from app.models.research_claim import ResearchClaim
from app.models.research_claim_variable import ResearchClaimVariable
from app.models.research_run import ResearchRun
from app.models.research_theme import ResearchTheme
from app.models.stock import Stock
from app.models.valuation import ValuationSnapshot
from app.services import thesis_monitor_service as svc


# ── Helpers ────────────────────────────────────────────────────────────


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_theme_run(db) -> ResearchRun:
    theme = ResearchTheme(name="t", market="A_SHARE")
    db.add(theme); db.flush()
    run = ResearchRun(
        research_theme_id=theme.id, status="completed",
        scope_market="A_SHARE", triggered_by="manual", llm_provider="test",
        started_at=_utcnow_naive(),
    )
    db.add(run); db.flush()
    return run


def _make_stock(db, code: str, name: str = "x") -> Stock:
    s = Stock(code=code, name=name)
    db.add(s); db.flush()
    return s


def _make_holding(db, code: str, *, sold: bool = False) -> Holding:
    h = Holding(
        stock_code=code, buy_date=date(2024, 1, 1),
        buy_price=10.0, quantity=100, stop_profit_price=12.0,
        sell_date=date(2024, 6, 1) if sold else None,
    )
    db.add(h); db.flush()
    return h


def _make_active_cv(
    db, *, claim_id: int, stock_code: str, source: str = "financial:NIM",
    threshold: float = 1.3, breach_when: str = "lt", window: int | None = None,
    variable_name: str = "净息差", last_alerted_at: datetime | None = None,
) -> ResearchClaimVariable:
    cv = ResearchClaimVariable(
        research_claim_id=claim_id, stock_code=stock_code,
        variable_name=variable_name, threshold_critical=threshold,
        breach_when=breach_when, source=source, unit="%",
        window_periods=window, status="active",
        last_alerted_at=last_alerted_at,
    )
    db.add(cv); db.flush()
    return cv


def _add_annual_financial(
    db, *, stock_code: str, year: int, nim: float | None = None,
    npl: float | None = None, revenue_growth: float | None = None,
    gross_margin: float | None = None,
) -> FinancialStatement:
    fs = FinancialStatement(
        stock_code=stock_code,
        report_date=datetime(year, 12, 31),
        report_type="annual",
        net_interest_margin=nim, npl_ratio=npl,
        revenue_growth=revenue_growth, gross_margin=gross_margin,
    )
    db.add(fs); db.flush()
    return fs


def _add_valuation(
    db, *, stock_code: str, pe_p10: float | None = None,
    pb_p10: float | None = None, days_ago: int = 0,
) -> ValuationSnapshot:
    vs = ValuationSnapshot(
        stock_code=stock_code,
        date=_utcnow_naive().date() - timedelta(days=days_ago),
        pe_percentile_10y=pe_p10, pb_percentile_10y=pb_p10,
    )
    db.add(vs); db.flush()
    return vs


# ── Source routing ─────────────────────────────────────────────────────


class TestSourceRouting:
    def test_financial_NIM(self, db_session):
        db = db_session
        run = _make_theme_run(db)
        db.add(ResearchClaim(
            research_run_id=run.id, type="failure_condition", position=0,
            subject="x", predicate="y", signal="NIM<1.3", outcome="z",
            stock_codes_json='["601398"]',
        ))
        db.flush()
        _make_stock(db, "601398", "工商银行")
        _make_holding(db, "601398")
        _add_annual_financial(db, stock_code="601398", year=2024, nim=1.2)
        _make_active_cv(
            db, claim_id=db.query(ResearchClaim).first().id,
            stock_code="601398", source="financial:NIM",
            threshold=1.3, breach_when="lt",
        )
        s = svc.check_claim_variables(db)
        assert s.checked == 1
        assert s.breached == 1
        assert s.alerts[0]["current_value"] == 1.2

    def test_financial_NPL(self, db_session):
        db = db_session
        run = _make_theme_run(db)
        c = ResearchClaim(
            research_run_id=run.id, type="failure_condition", position=0,
            subject="x", predicate="y", signal="NPL>2%", outcome="z",
            stock_codes_json='["601398"]',
        )
        db.add(c); db.flush()
        _make_stock(db, "601398")
        _make_holding(db, "601398")
        _add_annual_financial(db, stock_code="601398", year=2024, npl=2.5)
        _make_active_cv(
            db, claim_id=c.id, stock_code="601398", source="financial:NPL",
            threshold=2.0, breach_when="gt",
        )
        s = svc.check_claim_variables(db)
        assert s.breached == 1

    def test_valuation_PE_percentile(self, db_session):
        db = db_session
        run = _make_theme_run(db)
        c = ResearchClaim(
            research_run_id=run.id, type="failure_condition", position=0,
            subject="x", predicate="y", signal="PE>90%", outcome="z",
            stock_codes_json='["000001"]',
        )
        db.add(c); db.flush()
        _make_stock(db, "000001")
        _make_holding(db, "000001")
        _add_valuation(db, stock_code="000001", pe_p10=95.0)
        _make_active_cv(
            db, claim_id=c.id, stock_code="000001", source="valuation:PE_percentile",
            threshold=90.0, breach_when="gt",
        )
        s = svc.check_claim_variables(db)
        assert s.breached == 1

    def test_financial_revenue_growth(self, db_session):
        """v2 source routing: financial:revenue_growth → revenue_growth column."""
        db = db_session
        run = _make_theme_run(db)
        c = ResearchClaim(
            research_run_id=run.id, type="failure_condition", position=0,
            subject="x", predicate="y", signal="营收增长<-10%", outcome="z",
            stock_codes_json='["600519"]',
        )
        db.add(c); db.flush()
        _make_stock(db, "600519")
        _make_holding(db, "600519")
        _add_annual_financial(db, stock_code="600519", year=2024, revenue_growth=-15.0)
        _make_active_cv(
            db, claim_id=c.id, stock_code="600519", source="financial:revenue_growth",
            threshold=-10.0, breach_when="lt", variable_name="营收增长",
        )
        s = svc.check_claim_variables(db)
        assert s.breached == 1
        assert s.alerts[0]["current_value"] == -15.0

    def test_financial_margin(self, db_session):
        """v2 source routing: financial:margin → gross_margin column."""
        db = db_session
        run = _make_theme_run(db)
        c = ResearchClaim(
            research_run_id=run.id, type="failure_condition", position=0,
            subject="x", predicate="y", signal="毛利率<30%", outcome="z",
            stock_codes_json='["000651"]',
        )
        db.add(c); db.flush()
        _make_stock(db, "000651")
        _make_holding(db, "000651")
        _add_annual_financial(db, stock_code="000651", year=2024, gross_margin=25.0)
        _make_active_cv(
            db, claim_id=c.id, stock_code="000651", source="financial:margin",
            threshold=30.0, breach_when="lt", variable_name="毛利率",
        )
        s = svc.check_claim_variables(db)
        assert s.breached == 1

    def test_valuation_PB_percentile(self, db_session):
        """v2 source routing: valuation:PB_percentile → pb_percentile_10y column."""
        db = db_session
        run = _make_theme_run(db)
        c = ResearchClaim(
            research_run_id=run.id, type="failure_condition", position=0,
            subject="x", predicate="y", signal="PB>85%", outcome="z",
            stock_codes_json='["000001"]',
        )
        db.add(c); db.flush()
        _make_stock(db, "000001")
        _make_holding(db, "000001")
        _add_valuation(db, stock_code="000001", pb_p10=92.0)
        _make_active_cv(
            db, claim_id=c.id, stock_code="000001", source="valuation:PB_percentile",
            threshold=85.0, breach_when="gt", variable_name="PB 分位",
        )
        s = svc.check_claim_variables(db)
        assert s.breached == 1

    def test_kline_price_drop_52w(self, db_session):
        """v2 source routing: kline:price_drop_52w → computed from PriceKline."""
        from datetime import date as _date
        from app.models.price_kline import PriceKline
        db = db_session
        run = _make_theme_run(db)
        c = ResearchClaim(
            research_run_id=run.id, type="failure_condition", position=0,
            subject="x", predicate="y", signal="52周跌幅>40%", outcome="z",
            stock_codes_json='["000001"]',
        )
        db.add(c); db.flush()
        _make_stock(db, "000001")
        _make_holding(db, "000001")
        # Construct klines: peak high=15 in past, current close=8 → drop = 46.67%
        for i, (h, c_price) in enumerate([(15, 14), (14, 13), (12, 11), (10, 9), (8, 8)]):
            db.add(PriceKline(
                stock_code="000001",
                date=_date(2024, 1, 1 + i),
                freq="day", open=c_price, high=h, low=c_price - 0.5, close=c_price,
            ))
        db.flush()
        _make_active_cv(
            db, claim_id=c.id, stock_code="000001", source="kline:price_drop_52w",
            threshold=40.0, breach_when="gt", variable_name="52周跌幅",
        )
        s = svc.check_claim_variables(db)
        assert s.breached == 1
        # drop = (15 - 8) / 15 * 100 ≈ 46.67
        assert 46.0 < s.alerts[0]["current_value"] < 47.0


# ── Multi-period ───────────────────────────────────────────────────────


class TestMultiPeriod:
    def test_window_2_consecutive_breach(self, db_session):
        db = db_session
        run = _make_theme_run(db)
        c = ResearchClaim(
            research_run_id=run.id, type="failure_condition", position=0,
            subject="x", predicate="y", signal="NIM<1.3持续两季", outcome="z",
            stock_codes_json='["601398"]',
        )
        db.add(c); db.flush()
        _make_stock(db, "601398")
        _make_holding(db, "601398")
        _add_annual_financial(db, stock_code="601398", year=2024, nim=1.2)
        _add_annual_financial(db, stock_code="601398", year=2023, nim=1.25)
        _make_active_cv(
            db, claim_id=c.id, stock_code="601398", source="financial:NIM",
            threshold=1.3, breach_when="lt", window=2,
        )
        s = svc.check_claim_variables(db)
        assert s.breached == 1
        assert "连续 2 期" in s.alerts[0]["message"]

    def test_window_2_not_consecutive_no_breach(self, db_session):
        db = db_session
        run = _make_theme_run(db)
        c = ResearchClaim(
            research_run_id=run.id, type="failure_condition", position=0,
            subject="x", predicate="y", signal="NIM<1.3持续两季", outcome="z",
            stock_codes_json='["601398"]',
        )
        db.add(c); db.flush()
        _make_stock(db, "601398")
        _make_holding(db, "601398")
        # Only 2024 is below; 2023 was healthy
        _add_annual_financial(db, stock_code="601398", year=2024, nim=1.2)
        _add_annual_financial(db, stock_code="601398", year=2023, nim=1.5)
        _make_active_cv(
            db, claim_id=c.id, stock_code="601398", source="financial:NIM",
            threshold=1.3, breach_when="lt", window=2,
        )
        s = svc.check_claim_variables(db)
        assert s.breached == 0

    def test_window_2_insufficient_data(self, db_session):
        db = db_session
        run = _make_theme_run(db)
        c = ResearchClaim(
            research_run_id=run.id, type="failure_condition", position=0,
            subject="x", predicate="y", signal="NIM<1.3持续两季", outcome="z",
            stock_codes_json='["601398"]',
        )
        db.add(c); db.flush()
        _make_stock(db, "601398")
        _make_holding(db, "601398")
        _add_annual_financial(db, stock_code="601398", year=2024, nim=1.2)  # only 1 period
        _make_active_cv(
            db, claim_id=c.id, stock_code="601398", source="financial:NIM",
            threshold=1.3, breach_when="lt", window=2,
        )
        s = svc.check_claim_variables(db)
        assert s.breached == 0
        assert s.skipped_no_data == 1


# ── Holdings filter ────────────────────────────────────────────────────


class TestHoldingsFilter:
    def test_excludes_sold_stock(self, db_session):
        """v2 Q-new: INNER JOIN Holding WHERE sell_date IS NULL."""
        db = db_session
        run = _make_theme_run(db)
        c = ResearchClaim(
            research_run_id=run.id, type="failure_condition", position=0,
            subject="x", predicate="y", signal="NIM<1.3", outcome="z",
            stock_codes_json='["601398"]',
        )
        db.add(c); db.flush()
        _make_stock(db, "601398")
        _make_holding(db, "601398", sold=True)  # sold → not monitored
        _add_annual_financial(db, stock_code="601398", year=2024, nim=1.2)
        _make_active_cv(
            db, claim_id=c.id, stock_code="601398", source="financial:NIM",
            threshold=1.3, breach_when="lt",
        )
        s = svc.check_claim_variables(db)
        assert s.checked == 0
        assert s.breached == 0

    def test_excludes_no_holding_at_all(self, db_session):
        db = db_session
        run = _make_theme_run(db)
        c = ResearchClaim(
            research_run_id=run.id, type="failure_condition", position=0,
            subject="x", predicate="y", signal="NIM<1.3", outcome="z",
            stock_codes_json='["601398"]',
        )
        db.add(c); db.flush()
        _make_stock(db, "601398")
        # No holding at all
        _add_annual_financial(db, stock_code="601398", year=2024, nim=1.2)
        _make_active_cv(
            db, claim_id=c.id, stock_code="601398", source="financial:NIM",
            threshold=1.3, breach_when="lt",
        )
        s = svc.check_claim_variables(db)
        assert s.checked == 0


# ── Dedup ──────────────────────────────────────────────────────────────


class TestDedup:
    def test_recently_alerted_suppressed(self, db_session):
        """v2 Q6'-B1: 7-day dedup window."""
        db = db_session
        run = _make_theme_run(db)
        c = ResearchClaim(
            research_run_id=run.id, type="failure_condition", position=0,
            subject="x", predicate="y", signal="NIM<1.3", outcome="z",
            stock_codes_json='["601398"]',
        )
        db.add(c); db.flush()
        _make_stock(db, "601398")
        _make_holding(db, "601398")
        _add_annual_financial(db, stock_code="601398", year=2024, nim=1.2)
        recent = _utcnow_naive() - timedelta(hours=2)
        _make_active_cv(
            db, claim_id=c.id, stock_code="601398", source="financial:NIM",
            threshold=1.3, breach_when="lt",
            last_alerted_at=recent,
        )
        s = svc.check_claim_variables(db)
        assert s.breached == 0
        assert s.suppressed == 1

    def test_old_alert_re_fires(self, db_session):
        """>7 days since last alert → fires again."""
        db = db_session
        run = _make_theme_run(db)
        c = ResearchClaim(
            research_run_id=run.id, type="failure_condition", position=0,
            subject="x", predicate="y", signal="NIM<1.3", outcome="z",
            stock_codes_json='["601398"]',
        )
        db.add(c); db.flush()
        _make_stock(db, "601398")
        _make_holding(db, "601398")
        _add_annual_financial(db, stock_code="601398", year=2024, nim=1.2)
        old = _utcnow_naive() - timedelta(days=10)
        _make_active_cv(
            db, claim_id=c.id, stock_code="601398", source="financial:NIM",
            threshold=1.3, breach_when="lt",
            last_alerted_at=old,
        )
        s = svc.check_claim_variables(db)
        assert s.breached == 1


# ── _check_breach unit ─────────────────────────────────────────────────


class TestCheckBreachUnit:
    def test_lt_breach(self):
        assert svc._check_breach([1.2], 1.3, "lt", None) is True
        assert svc._check_breach([1.3], 1.3, "lt", None) is False

    def test_gt_breach(self):
        assert svc._check_breach([2.5], 2.0, "gt", None) is True
        assert svc._check_breach([2.0], 2.0, "gt", None) is False

    def test_multi_period_consecutive(self):
        assert svc._check_breach([1.2, 1.25], 1.3, "lt", 2) is True
        assert svc._check_breach([1.4, 1.25], 1.3, "lt", 2) is False


# ── EventBus emit (v2 Q-new) ──────────────────────────────────────────


class TestEventBusEmit:
    """v2: on fresh breach, check_claim_variables must emit ThesisAlertTriggered
    so the event_handlers.py notification chain can dispatch alerts."""

    def test_breach_emits_thesis_alert_triggered(self, db_session, monkeypatch):
        from app.core import events as events_mod
        from app.core.events import ThesisAlertTriggered

        db = db_session
        run = _make_theme_run(db)
        c = ResearchClaim(
            research_run_id=run.id, type="failure_condition", position=0,
            subject="x", predicate="y", signal="NIM<1.3", outcome="z",
            stock_codes_json='["601398"]',
        )
        db.add(c); db.flush()
        _make_stock(db, "601398", "工商银行")
        _make_holding(db, "601398")
        _add_annual_financial(db, stock_code="601398", year=2024, nim=1.2)
        _make_active_cv(
            db, claim_id=c.id, stock_code="601398", source="financial:NIM",
            threshold=1.3, breach_when="lt",
        )

        emitted: list[ThesisAlertTriggered] = []
        events_mod.bus.subscribe(ThesisAlertTriggered, emitted.append)
        try:
            svc.check_claim_variables(db)
        finally:
            events_mod.bus._handlers[ThesisAlertTriggered] = [
                h for h in events_mod.bus._handlers.get(ThesisAlertTriggered, [])
                if h is not emitted.append
            ]

        assert len(emitted) == 1
        ev = emitted[0]
        assert ev.claim_var_id is not None
        assert ev.code == "601398"
        assert ev.stock_name == "工商银行"
        assert ev.variable_name == "净息差"
        assert ev.current_value == 1.2
        assert ev.threshold_value == 1.3
        assert ev.breach_when == "lt"

    def test_no_breach_no_emit(self, db_session, monkeypatch):
        from app.core import events as events_mod
        from app.core.events import ThesisAlertTriggered

        db = db_session
        run = _make_theme_run(db)
        c = ResearchClaim(
            research_run_id=run.id, type="failure_condition", position=0,
            subject="x", predicate="y", signal="NIM<1.3", outcome="z",
            stock_codes_json='["601398"]',
        )
        db.add(c); db.flush()
        _make_stock(db, "601398")
        _make_holding(db, "601398")
        _add_annual_financial(db, stock_code="601398", year=2024, nim=1.5)  # healthy
        _make_active_cv(
            db, claim_id=c.id, stock_code="601398", source="financial:NIM",
            threshold=1.3, breach_when="lt",
        )

        emitted: list[ThesisAlertTriggered] = []
        events_mod.bus.subscribe(ThesisAlertTriggered, emitted.append)
        try:
            svc.check_claim_variables(db)
        finally:
            events_mod.bus._handlers[ThesisAlertTriggered] = [
                h for h in events_mod.bus._handlers.get(ThesisAlertTriggered, [])
                if h is not emitted.append
            ]

        assert len(emitted) == 0

    def test_dedup_blocks_second_emit(self, db_session):
        """7-day dedup window: second consecutive check does NOT re-emit."""
        from app.core import events as events_mod
        from app.core.events import ThesisAlertTriggered

        db = db_session
        run = _make_theme_run(db)
        c = ResearchClaim(
            research_run_id=run.id, type="failure_condition", position=0,
            subject="x", predicate="y", signal="NIM<1.3", outcome="z",
            stock_codes_json='["601398"]',
        )
        db.add(c); db.flush()
        _make_stock(db, "601398")
        _make_holding(db, "601398")
        _add_annual_financial(db, stock_code="601398", year=2024, nim=1.2)
        cv = _make_active_cv(
            db, claim_id=c.id, stock_code="601398", source="financial:NIM",
            threshold=1.3, breach_when="lt",
        )

        emitted: list[ThesisAlertTriggered] = []
        events_mod.bus.subscribe(ThesisAlertTriggered, emitted.append)
        try:
            s1 = svc.check_claim_variables(db)
            s2 = svc.check_claim_variables(db)
        finally:
            events_mod.bus._handlers[ThesisAlertTriggered] = [
                h for h in events_mod.bus._handlers.get(ThesisAlertTriggered, [])
                if h is not emitted.append
            ]

        assert s1.breached == 1
        assert s2.breached == 0
        assert s2.suppressed == 1
        assert len(emitted) == 1  # only first run emits
