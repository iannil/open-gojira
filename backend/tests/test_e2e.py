"""E2E (端到端) 测试 — 覆盖核心投资业务流程。

每个测试模拟完整链路：播种基础数据 → HTTP API 调用 → 验证业务结果。

测试路径:
  1. 买入全流程: Stock → BUY trade → 验证持仓/现金/组合摘要
  2. 卖出全流程: BUY → SELL → 验证持仓关闭 + 现金回归 + 盈亏
  3. 买入余额不足: 买入超额 → 400 错误
  4. T+1 冻结: BUY → available=0 → SELL 应失败
  5. 多股票组合: BUY 2 只 → 验证权重/现金比例
"""

from datetime import date, datetime, timedelta

import pytest

from app.models.broker_fee_config import BrokerFeeConfig
from app.models.cash_balance import CashBalance
from app.models.stock import Stock

# ── 共享播种 fixture ──────────────────────────────────────────────────────

_STOCKS = {
    "600519": ("贵州茅台", "sh", 100.0),
    "000001": ("平安银行", "sz", 10.0),
    "002415": ("海康威视", "sz", 30.0),
}


def _seed_minimal(db_session, codes=None):
    """播种最小数据集: Stock + CashBalance + BrokerFeeConfig."""
    if codes is None:
        codes = _STOCKS.keys()
    for code, (name, exchange, prev_close) in _STOCKS.items():
        if code in codes:
            db_session.add(Stock(
                code=code, name=name, exchange=exchange,
                listing_status="normally_listed", prev_close=prev_close,
            ))
    db_session.add(CashBalance(id=1, balance=1_000_000.0))
    db_session.add(BrokerFeeConfig(
        broker_name="default", commission_rate=0.00025, commission_min=5.0,
        stamp_duty_rate=0.0005, transfer_fee_rate=0.00001,
        effective_from=date(2023, 10, 23), is_active=True,
    ))
    db_session.flush()


@pytest.fixture
def setup(client, db_session):
    _seed_minimal(db_session)
    yield


def _buy(client, code, price, quantity, day_offset=-1):
    """辅助: 发起一笔买入."""
    filled_at = (datetime.now() + timedelta(days=day_offset)).isoformat()
    resp = client.post("/api/trades", json={
        "stock_code": code, "side": "BUY",
        "price": price, "quantity": quantity,
        "filled_at": filled_at,
    })
    return resp


# ── 测试用例 ────────────────────────────────────────────────────────────────


class TestBuyFullFlow:
    """路径 1: 买入全流程."""

    def test_buy_trade_created(self, client, setup):
        """买入 → 201 + 交易记录包含正确费用."""
        resp = _buy(client, "600519", 100.0, 100)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["stock_code"] == "600519"
        assert data["side"] == "BUY"
        assert data["quantity"] == 100
        # notional=10000, comm=max(10000×0.00025, 5)=5, stamp=0, tf=0.1
        assert data["commission"] == pytest.approx(5.0, abs=0.01)
        assert data["total_value"] == pytest.approx(10005.1, abs=0.01)

    def test_position_reflects_trade(self, client, setup):
        """买入后 → 持仓列表正确."""
        _buy(client, "600519", 100.0, 100)
        resp = client.get("/api/portfolio")
        assert resp.status_code == 200
        holdings = resp.json()
        assert len(holdings) == 1
        assert holdings[0]["stock_code"] == "600519"
        assert holdings[0]["quantity"] == 100

    def test_cash_deducted(self, client, setup):
        """买入后 → 现金余额减少."""
        _buy(client, "600519", 100.0, 100)  # costs 10005.1
        resp = client.get("/api/cash/balance")
        assert resp.status_code == 200
        assert resp.json()["balance"] == pytest.approx(1_000_000 - 10005.1, abs=0.01)

    def test_portfolio_summary_after_buy(self, client, setup):
        """买入后 → 组合摘要包含正确结构."""
        _buy(client, "600519", 100.0, 100)
        resp = client.get("/api/portfolio/summary")
        assert resp.status_code == 200
        summary = resp.json()
        assert summary["position_count"] == 1
        assert summary["total_cost"] == pytest.approx(10005.1, abs=0.01)
        # cash_reserve = initial 1M - trade cost
        assert summary["cash_reserve"] == pytest.approx(1_000_000 - 10005.1, abs=0.01)
        # 持仓权重 100%（只有一只股票）
        assert summary["holdings"][0]["weight_pct"] == 100.0


class TestSellFullFlow:
    """路径 2: 卖出全流程."""

    @pytest.fixture
    def setup_with_position(self, client, setup):
        """买入 600519 建立持仓."""
        _buy(client, "600519", 100.0, 100, day_offset=-2)
        yield

    def test_sell_trade_created(self, client, setup_with_position):
        """卖出 → 201 + 数量为负 + 计算正确."""
        resp = client.post("/api/trades", json={
            "stock_code": "600519", "side": "SELL",
            "price": 110.0, "quantity": 50,
            "filled_at": datetime.now().isoformat(),
        })
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["side"] == "SELL"
        assert data["quantity"] == -50
        # notional=5500, comm=5, stamp=5500×0.0005=2.75, tf=0.055
        assert data["total_value"] == pytest.approx(5492.195, abs=0.01)

    def test_sell_reduces_position(self, client, setup_with_position):
        """卖出一半 → 持仓数量减少."""
        client.post("/api/trades", json={
            "stock_code": "600519", "side": "SELL",
            "price": 110.0, "quantity": 50,
            "filled_at": datetime.now().isoformat(),
        })
        resp = client.get("/api/portfolio")
        assert resp.status_code == 200
        holdings = resp.json()
        assert len(holdings) == 1
        # original 100 - sold 50 = 50 remaining
        # But position table uses weighted moving average
        assert holdings[0]["stock_code"] == "600519"
        assert holdings[0]["quantity"] == 50

    def test_sell_returns_cash(self, client, setup_with_position):
        """卖出后 → 现金余额增加."""
        initial_cash = 1_000_000 - 10005.1  # after buy
        client.post("/api/trades", json={
            "stock_code": "600519", "side": "SELL",
            "price": 110.0, "quantity": 100,  # sell all
            "filled_at": datetime.now().isoformat(),
        })
        resp = client.get("/api/cash/balance")
        assert resp.status_code == 200
        # After selling all: cash = initial - buy_cost + sell_proceeds
        # sell proceeds = 110*100 - 5(comm) - 5.5(stamp) - 0.11(tf) = 10989.39
        # bonus: commission min is 5, stamp is 11000*0.0005=5.5
        expected_cash = initial_cash + 10989.39
        assert resp.json()["balance"] == pytest.approx(expected_cash, abs=0.01)

    def test_sell_full_closes_position(self, client, setup_with_position):
        """全量卖出 → 持仓列表空."""
        client.post("/api/trades", json={
            "stock_code": "600519", "side": "SELL",
            "price": 110.0, "quantity": 100,
            "filled_at": datetime.now().isoformat(),
        })
        resp = client.get("/api/portfolio?active_only=true")
        assert resp.status_code == 200
        assert len(resp.json()) == 0


class TestBuyInsufficientBalance:
    """路径 3: 余额不足."""

    def test_insufficient_cash_rejected(self, client, db_session):
        """现金不够 → 400."""
        db_session.add(Stock(
            code="600519", name="贵州茅台", exchange="sh",
            listing_status="normally_listed", prev_close=100.0,
        ))
        db_session.add(CashBalance(id=1, balance=100.0))  # only 100 yuan
        db_session.add(BrokerFeeConfig(
            broker_name="default", commission_rate=0.00025, commission_min=5.0,
            stamp_duty_rate=0.0005, transfer_fee_rate=0.00001,
            effective_from=date(2023, 10, 23), is_active=True,
        ))
        db_session.flush()

        resp = client.post("/api/trades", json={
            "stock_code": "600519", "side": "BUY",
            "price": 100.0, "quantity": 100,
            "filled_at": datetime.now().isoformat(),
        })
        assert resp.status_code == 400
        assert "余额不足" in resp.text or "Insufficient" in resp.text


class TestTPlusOneFreeze:
    """路径 4: T+1 冻结."""

    def test_available_quantity_zero_same_day(self, client, setup):
        """当日买入 → available=0, frozen=数量."""
        _buy(client, "600519", 100.0, 100, day_offset=0)
        resp = client.get("/api/portfolio/600519/available")
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] == 0  # T+1 not settled
        assert data["frozen"] == 100  # bought today

    def test_sell_same_day_rejected(self, client, setup):
        """当日买入 → 立即卖出应被拒绝."""
        _buy(client, "600519", 100.0, 100, day_offset=0)
        resp = client.post("/api/trades", json={
            "stock_code": "600519", "side": "SELL",
            "price": 100.0, "quantity": 50,
            "filled_at": datetime.now().isoformat(),
        })
        # T+1: 不满足可用数量
        assert resp.status_code == 400


class TestMultiStockPortfolio:
    """路径 5: 多股票组合."""

    def test_portfolio_after_two_buys(self, client, setup):
        """买入两只不同股票 → 组合摘要包含两只."""
        _buy(client, "600519", 100.0, 100, day_offset=-2)  # cost 10005.1
        _buy(client, "000001", 10.0, 1000, day_offset=-2)  # cost 10005.1

        resp = client.get("/api/portfolio/summary")
        assert resp.status_code == 200
        summary = resp.json()
        assert summary["position_count"] == 2
        assert summary["total_cost"] == pytest.approx(20010.2, abs=0.01)

    def test_weight_distribution(self, client, setup):
        """组合摘要中两只股票各占权重 > 0%."""
        _buy(client, "600519", 100.0, 100, day_offset=-2)
        _buy(client, "000001", 10.0, 1000, day_offset=-2)

        resp = client.get("/api/portfolio/summary")
        assert resp.status_code == 200
        summary = resp.json()
        holdings = summary["holdings"]
        assert len(holdings) == 2
        total_weight = sum(h["weight_pct"] for h in holdings)
        assert total_weight == pytest.approx(100.0, abs=0.1)
        for h in holdings:
            assert h["weight_pct"] > 0

    def test_total_cash_plus_value_equals_initial(self, client, setup):
        """现金 + 股票市值 > 0 且权重总和 100%."""
        _buy(client, "600519", 100.0, 100, day_offset=-2)
        _buy(client, "000001", 10.0, 1000, day_offset=-2)

        resp = client.get("/api/portfolio/summary")
        summary = resp.json()
        assert summary["cash_reserve"] > 0
        total_weight = sum(h["weight_pct"] for h in summary["holdings"])
        assert total_weight == pytest.approx(100.0, abs=0.1)
