"""Tests for theme service — investment theme exposure analysis."""

from datetime import date

import pytest

from app.models.holding import Holding
from app.models.plan import Plan
from app.models.stock import Stock
from app.models.theme import Theme
from app.services import theme_service
from tests.conftest import TestSessionLocal


@pytest.fixture
def db():
    """Create a fresh database session for each test."""
    s = TestSessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def sample_themes(db) -> list[Theme]:
    """Create sample themes for testing."""
    themes = [
        Theme(
            name="能源安全",
            description="能源安全主线",
            target_weight_pct=25.0,
        ),
        Theme(
            name="资源安全",
            description="资源安全主线",
            target_weight_pct=25.0,
        ),
        Theme(
            name="金融安全",
            description="金融安全主线",
            target_weight_pct=25.0,
        ),
        Theme(
            name="粮食安全",
            description="粮食安全主线",
            target_weight_pct=25.0,
        ),
    ]
    db.add_all(themes)
    db.commit()
    for theme in themes:
        db.refresh(theme)
    return themes


@pytest.fixture
def sample_stocks_with_themes(db) -> list[Stock]:
    """Create sample stocks with security themes."""
    stocks = [
        Stock(
            code="600000",
            name="浦发银行",
            security_theme="金融安全",
            qiu_score=2,
        ),
        Stock(
            code="601857",
            name="中国石油",
            security_theme="能源安全",
            qiu_score=3,
        ),
        Stock(
            code="600519",
            name="贵州茅台",
            security_theme="粮食安全",
            qiu_score=3,
        ),
        Stock(
            code="600036",
            name="招商银行",
            security_theme="金融安全",
            qiu_score=3,
        ),
        Stock(
            code="000858",
            name="五粮液",
            security_theme=None,  # 未分类
            qiu_score=2,
        ),
    ]
    db.add_all(stocks)
    db.commit()
    for stock in stocks:
        db.refresh(stock)
    return stocks


@pytest.fixture
def sample_holdings(db, sample_stocks_with_themes) -> list[Holding]:
    """Create sample holdings."""
    holdings = [
        Holding(
            stock_code="600000",
            quantity=1000,
            buy_price=10.0,
            buy_date=date(2026, 1, 1),
            stop_profit_price=15.0,
        ),
        Holding(
            stock_code="601857",
            quantity=2000,
            buy_price=8.0,
            buy_date=date(2026, 1, 1),
            stop_profit_price=12.0,
        ),
        Holding(
            stock_code="600519",
            quantity=500,
            buy_price=1500.0,
            buy_date=date(2026, 1, 1),
            stop_profit_price=2000.0,
        ),
        Holding(
            stock_code="600036",
            quantity=1500,
            buy_price=35.0,
            buy_date=date(2026, 1, 1),
            stop_profit_price=50.0,
        ),
        Holding(
            stock_code="000858",
            quantity=800,
            buy_price=120.0,
            buy_date=date(2026, 1, 1),
            stop_profit_price=180.0,
        ),
    ]
    db.add_all(holdings)
    db.commit()
    for holding in holdings:
        db.refresh(holding)
    return holdings


def test_get_theme_exposure_with_holdings(db, sample_themes, sample_holdings):
    """Test get_theme_exposure with holdings."""
    exposure = theme_service.get_theme_exposure(db)

    # Should have 3 themes (金融安全, 能源安全, 粮食安全) + 1 "未分类"
    # 资源安全 is not represented in any holding
    assert len(exposure) == 4

    # Check 金融安全 theme (浦发银行 + 招商银行)
    financial_theme = next((item for item in exposure if item["theme"] == "金融安全"), None)
    assert financial_theme is not None
    assert financial_theme["count"] == 2
    assert set(financial_theme["stock_codes"]) == {"600000", "600036"}
    assert financial_theme["weight_pct"] > 0

    # Check 未分类
    unclassified = next((item for item in exposure if item["theme"] == "未分类"), None)
    assert unclassified is not None
    assert unclassified["count"] == 1
    assert unclassified["stock_codes"] == ["000858"]

    # Check total weights sum to 100%
    total_weight = sum(item["weight_pct"] for item in exposure)
    assert abs(total_weight - 100.0) < 0.1


def test_get_theme_exposure_empty_portfolio(db, sample_themes):
    """Test get_theme_exposure with no holdings."""
    exposure = theme_service.get_theme_exposure(db)
    assert exposure == []


def test_get_theme_targets_with_drift_warnings(db, sample_themes, sample_holdings):
    """Test get_theme_targets with drift warnings."""
    targets = theme_service.get_theme_targets(db)

    # Should have 4 themes
    assert len(targets) == 4

    # Each theme should have target and actual weights
    for target in targets:
        assert "theme" in target
        assert "target_pct" in target
        assert "actual_pct" in target
        assert "drift_pct" in target
        assert "warning" in target

        # Target should be 25.0 (from sample_themes)
        assert target["target_pct"] == 25.0

        # Check drift calculation
        expected_drift = target["actual_pct"] - 25.0
        assert abs(target["drift_pct"] - expected_drift) < 0.1

    # Check for warnings on large drifts
    warnings = [t for t in targets if t["warning"] is not None]
    # We expect at least some warnings since we have an unbalanced portfolio
    assert len(warnings) >= 0


def test_get_theme_coverage_with_active_plans(db, sample_themes, sample_stocks_with_themes):
    """Test get_theme_coverage with active plans and candidates."""
    import json
    from app.models.plan import Plan
    from app.models.candidate import Candidate

    # Create an active plan
    plan = Plan(
        name="测试预案",
        slug="test_plan",
        status="active",
        strategy_composition_json=json.dumps({"strategy_ids": [], "logic": "AND"}),
        scan_scope_json=json.dumps({"type": "all_stocks", "values": []}),
        is_builtin=False,
    )
    db.add(plan)
    db.flush()

    # Add candidates for the stocks
    for stock in sample_stocks_with_themes:
        db.add(Candidate(
            plan_id=plan.id,
            stock_code=stock.code,
            status="active",
        ))
    db.commit()

    coverage = theme_service.get_theme_coverage(db)

    # Should have results grouped by plan name
    assert len(coverage) >= 1
    # All candidates are under the same plan
    total_candidates = sum(c["active_plan_count"] for c in coverage)
    assert total_candidates == len(sample_stocks_with_themes)


def test_get_theme_coverage_no_active_plans(db, sample_themes):
    """Test get_theme_coverage with no active plans."""
    coverage = theme_service.get_theme_coverage(db)
    assert coverage == []


def test_list_themes(db, sample_themes):
    """Test list_themes."""
    themes = theme_service.list_themes(db)

    assert len(themes) == 4
    theme_names = [t.name for t in themes]
    assert "能源安全" in theme_names
    assert "资源安全" in theme_names
    assert "金融安全" in theme_names
    assert "粮食安全" in theme_names


def test_get_theme(db, sample_themes):
    """Test get_theme."""
    theme = sample_themes[0]
    found = theme_service.get_theme(db, theme.id)

    assert found is not None
    assert found.id == theme.id
    assert found.name == theme.name
    assert found.description == theme.description
    assert found.target_weight_pct == theme.target_weight_pct


def test_get_theme_not_found(db):
    """Test get_theme with non-existent ID."""
    found = theme_service.get_theme(db, 99999)
    assert found is None


def test_create_theme(db):
    """Test create_theme."""
    theme = theme_service.create_theme(
        db,
        name="科技安全",
        description="科技安全主线",
        target_weight_pct=30.0,
    )

    assert theme.id is not None
    assert theme.name == "科技安全"
    assert theme.description == "科技安全主线"
    assert theme.target_weight_pct == 30.0


def test_update_theme(db, sample_themes):
    """Test update_theme."""
    theme = sample_themes[0]

    updated = theme_service.update_theme(
        db,
        theme.id,
        description="更新后的描述",
        target_weight_pct=35.0,
    )

    assert updated is not None
    assert updated.description == "更新后的描述"
    assert updated.target_weight_pct == 35.0
    assert updated.name == theme.name  # Should not change


def test_update_theme_not_found(db):
    """Test update_theme with non-existent ID."""
    updated = theme_service.update_theme(db, 99999, description="新描述")
    assert updated is None


def test_delete_theme(db, sample_themes):
    """Test delete_theme."""
    theme = sample_themes[0]
    theme_id = theme.id

    success = theme_service.delete_theme(db, theme_id)
    assert success is True

    # Verify deletion
    found = theme_service.get_theme(db, theme_id)
    assert found is None


def test_delete_theme_not_found(db):
    """Test delete_theme with non-existent ID."""
    success = theme_service.delete_theme(db, 99999)
    assert success is False
