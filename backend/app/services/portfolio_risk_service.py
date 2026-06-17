"""Portfolio risk service — invest2 §7 平方差魔咒实时指标.

魔咒: 涨跌 10% 无法回本, 波动是复利杀手。
本服务从 historical_klines 推算当前持仓的组合级风险指标,
让用户在 Cockpit 上用 invest2 §7 视角自我评估。

输出:
  - annual_volatility: 年化波动率 (std × √252)
  - max_drawdown_30d: 过去 30 日最大回撤 (负数)
  - max_drawdown_90d: 过去 90 日最大回撤 (负数)
  - sharpe_proxy: 年化夏普比率代理 (risk_free=2%)

不做硬约束: 不触发 SystemAlert, 不阻塞 plan_runner。
invest2 §7 是"为什么买这类资产"的理由, 不是机械交易规则。
"""
from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.historical_kline import HistoricalKline
from app.services.backtest_metrics import compute_max_drawdown, compute_sharpe
from app.services.holding_view_service import get_holding_view

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE = 0.02  # invest2 假设: 无风险利率 2% (10年国债)


@dataclass(frozen=True)
class PortfolioRisk:
    """组合级风险指标 (invest2 §7)."""
    has_holdings: bool
    """是否有持仓 (无持仓时其他字段为 None)."""
    holdings_count: int
    window_days: int
    """实际计算的窗口天数 (可能少于 90, 若数据不足)."""
    annual_volatility: float | None = None
    max_drawdown_30d: float | None = None
    max_drawdown_90d: float | None = None
    sharpe_proxy: float | None = None
    errors: list[str] = field(default_factory=list)
    """Per-stock kline 缺失等非阻塞警告."""

    def to_dict(self) -> dict:
        return {
            "has_holdings": self.has_holdings,
            "holdings_count": self.holdings_count,
            "window_days": self.window_days,
            "annual_volatility": self.annual_volatility,
            "max_drawdown_30d": self.max_drawdown_30d,
            "max_drawdown_90d": self.max_drawdown_90d,
            "sharpe_proxy": self.sharpe_proxy,
            "errors": self.errors,
        }


def _fetch_klines(
    db: Session, stock_code: str, start_date: date, end_date: date
) -> list[HistoricalKline]:
    """Fetch daily klines for a stock in [start, end] sorted by date."""
    return list(
        db.execute(
            select(HistoricalKline)
            .where(
                HistoricalKline.stock_code == stock_code,
                HistoricalKline.date >= start_date,
                HistoricalKline.date <= end_date,
            )
            .order_by(HistoricalKline.date.asc())
        ).scalars().all()
    )


def _build_portfolio_series(
    db: Session,
    holdings: list[dict],
    window_days: int,
) -> tuple[list[tuple[date, float]], list[str]]:
    """Build (date, total_value) series by summing quantity × close across holdings.

    Returns empty list if no klines available for any holding.
    Errors are collected but non-fatal (we use what we have).
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=window_days)
    errors: list[str] = []

    # Per-stock kline maps: {stock_code: {date: close}}
    per_stock: dict[str, dict[date, float]] = {}
    for h in holdings:
        code = h["stock_code"]
        qty = h.get("total_quantity") or 0
        if qty <= 0:
            continue
        klines = _fetch_klines(db, code, start_date, end_date)
        if not klines:
            errors.append(f"{code}: 无 historical_klines 数据")
            continue
        per_stock[code] = {k.date: k.close * qty for k in klines}

    if not per_stock:
        return [], errors

    # Union of all dates; for each date, sum close×qty across stocks present that day
    all_dates: set[date] = set()
    for dmap in per_stock.values():
        all_dates.update(dmap.keys())
    sorted_dates = sorted(all_dates)

    series: list[tuple[date, float]] = []
    for d in sorted_dates:
        total = 0.0
        for code, dmap in per_stock.items():
            if d in dmap:
                total += dmap[d]
        # Only include dates where at least one stock has data
        if total > 0:
            series.append((d, total))

    return series, errors


def _daily_returns(series: list[tuple[date, float]]) -> list[float]:
    """Compute daily returns from (date, value) series."""
    if len(series) < 2:
        return []
    returns: list[float] = []
    for i in range(1, len(series)):
        prev = series[i - 1][1]
        curr = series[i][1]
        if prev > 0:
            returns.append((curr - prev) / prev)
    return returns


def _annual_volatility(daily_returns: list[float]) -> float | None:
    """Annualized volatility = std × √252."""
    if len(daily_returns) < 2:
        return None
    std = statistics.stdev(daily_returns)
    return std * math.sqrt(TRADING_DAYS_PER_YEAR)


def _max_drawdown_in_window(
    series: list[tuple[date, float]], last_n_days: int
) -> float | None:
    """Max drawdown over the last N calendar days of the series."""
    if not series:
        return None
    cutoff = date.today() - timedelta(days=last_n_days)
    window = [v for d, v in series if d >= cutoff]
    if len(window) < 2:
        return None
    return compute_max_drawdown(window)


def compute_portfolio_risk(db: Session, window_days: int = 90) -> PortfolioRisk:
    """Compute current portfolio risk metrics from historical_klines.

    Args:
        db: SQLAlchemy session.
        window_days: Lookback window in calendar days (default 90).

    Returns:
        PortfolioRisk dataclass. If no holdings, has_holdings=False and metrics None.
    """
    holdings = get_holding_view(db)
    if not holdings:
        return PortfolioRisk(
            has_holdings=False,
            holdings_count=0,
            window_days=0,
        )

    series, errors = _build_portfolio_series(db, holdings, window_days)
    if not series:
        return PortfolioRisk(
            has_holdings=True,
            holdings_count=len(holdings),
            window_days=0,
            errors=errors,
        )

    returns = _daily_returns(series)
    annual_vol = _annual_volatility(returns)
    mdd_30 = _max_drawdown_in_window(series, 30)
    mdd_90 = _max_drawdown_in_window(series, 90)
    sharpe = (
        compute_sharpe(returns, RISK_FREE_RATE)
        if len(returns) >= 2 else None
    )

    return PortfolioRisk(
        has_holdings=True,
        holdings_count=len(holdings),
        window_days=len(series),
        annual_volatility=annual_vol,
        max_drawdown_30d=mdd_30,
        max_drawdown_90d=mdd_90,
        sharpe_proxy=sharpe,
        errors=errors,
    )
