"""TDD for draft_generator (Phase 5, decision 9/10 + §7)."""
from datetime import date, timedelta

from app.core.datetime_utils import now
from app.db.session import SessionLocal
from app.models.cash_balance import CashBalance
from app.models.draft import Draft
from app.models.research_report import ResearchReport
from app.models.stock import Stock
from app.services import draft_generator


_RANGES = {
    "aggressive": {"min": 95.0, "max": 105.0},
    "steady": {"min": 80.0, "max": 90.0},
    "conservative": {"min": 60.0, "max": 70.0},
}


def _seed_report(db, code="600519", rec="BUY", source="quality_screen", ranges=_RANGES, cash=100000.0):
    # decision 9 requires cash ≥20% of portfolio → seed cash so drafts can generate
    db.add(CashBalance(id=1, balance=cash))
    db.add(Stock(code=code, name="测试", industry="non_financial", listed_date=date(2010, 1, 1)))
    db.add(ResearchReport(
        stock_code=code, pipeline_type="deep_research", recommendation=rec,
        status="completed", overall_score=4.2,
        json_output={
            "scoring": {"source": source},
            "synthesis": {"price_ranges": ranges, "mirror_test": {"statement": "卡点逻辑5句"}},
        },
    ))
    db.commit()


def _gen(db, price):
    return draft_generator.generate_buy_drafts(db, price_fn=lambda code: price)


def test_aggressive_tier_generates_draft(setup_db):
    db = SessionLocal()
    try:
        _seed_report(db)
        out = _gen(db, 100.0)  # in aggressive [95,105]
        assert out["generated"] == 1
        d = db.query(Draft).filter_by(side="BUY").one()
        assert d.strategy_tier == "aggressive"
        assert d.add_pct == 8.0
        assert d.research_report_id is not None
        assert d.expires_at is not None
        assert d.price_ranges_json["aggressive"]["max"] == 105.0
        assert d.thesis_status == "healthy"
        assert d.serenity_thesis is None  # quality_screen source
    finally:
        db.close()


def test_steady_tier_half_sizing(setup_db):
    db = SessionLocal()
    try:
        _seed_report(db)
        out = _gen(db, 85.0)  # in steady [80,90]
        assert out["generated"] == 1
        d = db.query(Draft).filter_by(side="BUY").one()
        assert d.strategy_tier == "steady"
        assert d.add_pct == 4.0
    finally:
        db.close()


def test_conservative_price_no_draft(setup_db):
    db = SessionLocal()
    try:
        _seed_report(db)
        out = _gen(db, 65.0)  # conservative range → 保守不生成
        assert out["generated"] == 0
        assert db.query(Draft).count() == 0
    finally:
        db.close()


def test_price_above_aggressive_no_draft(setup_db):
    db = SessionLocal()
    try:
        _seed_report(db)
        out = _gen(db, 120.0)  # too expensive
        assert out["generated"] == 0
    finally:
        db.close()


def test_pass_report_ignored(setup_db):
    db = SessionLocal()
    try:
        _seed_report(db, rec="PASS")
        out = _gen(db, 100.0)
        assert out["generated"] == 0
        assert out["scanned"] == 0  # PASS excluded from scan (not actionable)
    finally:
        db.close()


def test_hold_report_in_zone_generates(setup_db):
    """decision 9: trigger is price-in-zone + thesis healthy, not rec==BUY.
    A HOLD report whose price entered a buy tier still generates a draft."""
    db = SessionLocal()
    try:
        _seed_report(db, rec="HOLD")
        out = _gen(db, 100.0)  # in aggressive tier
        assert out["generated"] == 1
        assert db.query(Draft).filter_by(side="BUY").one().strategy_tier == "aggressive"
    finally:
        db.close()


def test_theme_source_sets_serenity_thesis(setup_db):
    db = SessionLocal()
    try:
        _seed_report(db, source="theme_scan")
        _gen(db, 100.0)
        d = db.query(Draft).filter_by(side="BUY").one()
        assert d.serenity_thesis == "卡点逻辑5句"
    finally:
        db.close()


def test_expired_draft_cancelled(setup_db):
    db = SessionLocal()
    try:
        _seed_report(db)
        db.add(Draft(code="600519", side="BUY", status="pending", step_kind="buy_ladder",
                     step_index=0, reason="old", source="draft_generator",
                     expires_at=now() - timedelta(days=1)))
        db.commit()
        out = _gen(db, 120.0)  # too expensive → no new draft, but expired cancelled
        assert out["expired_cancelled"] == 1
        assert db.query(Draft).filter_by(status="cancelled").count() == 1
    finally:
        db.close()


def test_supersede_replaces_prior_pending(setup_db):
    db = SessionLocal()
    try:
        _seed_report(db)
        _gen(db, 100.0)
        _gen(db, 100.0)  # second run supersedes the first
        assert db.query(Draft).filter_by(status="superseded").count() == 1
        assert db.query(Draft).filter_by(status="pending").count() == 1
    finally:
        db.close()
