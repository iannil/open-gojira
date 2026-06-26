"""Evaluation service — P1 评价系统: 基准对比 + 夏普 + 归因 + 信号质量。

Tier 1 (组合层): 现有 holding_service.get_portfolio_summary()
Tier 2 (基准层):  vs 沪深300 同期收益对比
Tier 3 (质量层):  夏普 / 交易次数 / 双引擎归因
Tier 4 (信号层):  建议价 vs 实际价滑点 / 信号质量统计
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.datetime_utils import now
from app.models.decision_audit import DecisionAudit
from app.models.draft import Draft
from app.models.trade import Trade
from app.services import holding_service, index_service, position_service

# ── Tier 2: Benchmark comparison ──────────────────────────────────────────


def benchmark_comparison(
    db: Session,
    *,
    index_code: str = index_service.DEFAULT_BENCHMARK,
    days: int = 365,
) -> dict:
    """Compare portfolio return vs benchmark over the last N days.

    Returns:
        {
            "benchmark_code": "000300",
            "benchmark_name": "沪深300",
            "period_days": 365,
            "portfolio_return_pct": float | None,
            "benchmark_return_pct": float | None,
            "excess_return_pct": float | None,
            "start_date": "2025-06-26",
            "end_date": "2026-06-26",
        }
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    # Portfolio return: use holding_service's portfolio return calculation
    summary = holding_service.get_portfolio_summary(db)
    portfolio_return = summary.get("total_pnl_pct")

    # Benchmark return
    benchmark_return = index_service.compute_benchmark_return(
        db, index_code, start_date=start_date, end_date=end_date,
    )
    benchmark_return_pct = (
        round(benchmark_return * 100, 2) if benchmark_return is not None else None
    )

    excess = None
    if portfolio_return is not None and benchmark_return_pct is not None:
        excess = round(portfolio_return - benchmark_return_pct, 2)

    return {
        "benchmark_code": index_code,
        "benchmark_name": index_service.BENCHMARK_CODES.get(index_code, index_code),
        "period_days": days,
        "portfolio_return_pct": (
            round(float(portfolio_return), 2) if portfolio_return is not None else None
        ),
        "benchmark_return_pct": benchmark_return_pct,
        "excess_return_pct": excess,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }


# ── Tier 3: Quality metrics ──────────────────────────────────────────────


def trade_statistics(db: Session) -> dict:
    """Compute trade-level statistics.

    Returns:
        {
            "total_trades": int,
            "winning_trades": int,
            "losing_trades": int,
            "win_rate_pct": float,
            "avg_win_pct": float,
            "avg_loss_pct": float,
            "profit_factor": float,  # gross win / gross loss
        }
    """
    trades = db.query(Trade).filter(
        Trade.side.in_(["BUY", "SELL"]),
    ).order_by(Trade.filled_at).all()

    if not trades:
        return {
            "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
            "win_rate_pct": 0.0, "avg_win_pct": 0.0, "avg_loss_pct": 0.0,
            "profit_factor": 0.0,
        }

    # Group trades by stock to compute realized P&L per round-trip
    # For simplicity, use position_service which already folds trades
    codes = {t.stock_code for t in trades}
    wins = 0
    losses = 0
    total_win_pct = 0.0
    total_loss_pct = 0.0

    for code in codes:
        pos = position_service.position_for(db, code, price_lookup=lambda _c: None)
        if pos and pos.realized_pnl != 0:
            # Estimate return from realized P&L
            pnl_pct = (
                (pos.realized_pnl / abs(pos.cost_basis - pos.realized_pnl)) * 100
                if abs(pos.cost_basis - pos.realized_pnl) > 0
                else 0
            )
            if pnl_pct > 0:
                wins += 1
                total_win_pct += pnl_pct
            else:
                losses += 1
                total_loss_pct += abs(pnl_pct)

    total = wins + losses
    win_rate = round(wins / total * 100, 1) if total > 0 else 0.0
    avg_win = round(total_win_pct / wins, 2) if wins > 0 else 0.0
    avg_loss = round(total_loss_pct / losses, 2) if losses > 0 else 0.0
    profit_factor = round(total_win_pct / total_loss_pct, 2) if total_loss_pct > 0 else float("inf") if total_win_pct > 0 else 0.0

    return {
        "total_trades": len(trades),
        "winning_trades": wins,
        "losing_trades": losses,
        "win_rate_pct": win_rate,
        "avg_win_pct": avg_win,
        "avg_loss_pct": avg_loss,
        "profit_factor": profit_factor,
    }


def estimate_sharpe_ratio(db: Session, *, annualized: bool = True) -> Optional[float]:
    """Estimate Sharpe ratio from portfolio's annualized return and volatility.

    Uses portfolio_annualized_pct from holding_service as return proxy.
    For a proper Sharpe, we'd need daily return series — this is a simplified
    estimate suitable for the current data granularity.

    Returns:
        Sharpe ratio (float) or None if insufficient data.
    """
    summary = holding_service.get_portfolio_summary(db)
    annual_return = summary.get("portfolio_annualized_pct")
    if annual_return is None:
        return None

    # Use a conservative volatility estimate for A-shares (~25% annualized)
    # In production this would come from daily return std dev
    estimated_volatility = 25.0  # 25% annualized vol (typical for A-shares)
    risk_free_rate = 2.0  # ~2% Chinese gov bond yield

    sharpe = (float(annual_return) - risk_free_rate) / estimated_volatility
    return round(sharpe, 3)


def dual_engine_attribution(db: Session) -> dict:
    """Attribute trades/decisions to each engine (quality_screen vs theme_scan).

    Uses Draft.source to attribute:
      - "draft_generator" → quality_screen (ai-berkshire)
      - "evaluator" → theme_scan (serenity)

    Returns:
        {
            "quality_screen": {"drafts": int, "executed": int, "total_value": float},
            "theme_scan": {"drafts": int, "executed": int, "total_value": float},
            "unknown": {"drafts": int, "executed": int},
        }
    """
    drafts = db.query(Draft).all()
    attribution: dict[str, dict] = {
        "quality_screen": {"drafts": 0, "executed": 0, "total_value": 0.0},
        "theme_scan": {"drafts": 0, "executed": 0, "total_value": 0.0},
        "unknown": {"drafts": 0, "executed": 0, "total_value": 0.0},
    }

    for d in drafts:
        source = d.source or "unknown"
        if source == "draft_generator":
            engine = "quality_screen"
        elif source == "evaluator":
            engine = "theme_scan"
        else:
            engine = "unknown"

        attribution[engine]["drafts"] += 1
        if d.status == "executed":
            attribution[engine]["executed"] += 1
            # Look up the associated trade value
            trade = (
                db.query(Trade)
                .filter(Trade.source_ref == str(d.id))
                .first()
            )
            if trade:
                attribution[engine]["total_value"] += float(trade.total_value or 0)

    return attribution


# ── Tier 4: Signal quality ───────────────────────────────────────────────


def signal_quality(db: Session) -> dict:
    """Compute slippage between suggested (draft target) and actual fill prices.

    Returns:
        {
            "total_executed": int,
            "with_slippage_data": int,
            "avg_slippage_pct": float,
            "max_slippage_pct": float,
            "by_side": {
                "BUY": {"count": int, "avg_slippage_pct": float},
                "SELL": {"count": int, "avg_slippage_pct": float},
            }
        }
    """
    decisions = (
        db.query(DecisionAudit)
        .filter(
            DecisionAudit.executed_price.isnot(None),
            DecisionAudit.target_price.isnot(None),
            DecisionAudit.target_price > 0,
        )
        .all()
    )

    if not decisions:
        return {
            "total_executed": 0, "with_slippage_data": 0,
            "avg_slippage_pct": 0.0, "max_slippage_pct": 0.0,
            "by_side": {"BUY": {"count": 0, "avg_slippage_pct": 0.0},
                        "SELL": {"count": 0, "avg_slippage_pct": 0.0}},
        }

    total_slippage = 0.0
    max_slippage = 0.0
    by_side: dict[str, list[float]] = {"BUY": [], "SELL": []}

    for d in decisions:
        slippage = abs(d.executed_price - d.target_price) / d.target_price * 100  # type: ignore[operator]
        total_slippage += slippage
        max_slippage = max(max_slippage, slippage)
        side = d.action
        if side in by_side:
            by_side[side].append(slippage)

    count = len(decisions)
    avg_slippage = round(total_slippage / count, 3) if count > 0 else 0.0

    return {
        "total_executed": db.query(DecisionAudit).count(),
        "with_slippage_data": count,
        "avg_slippage_pct": avg_slippage,
        "max_slippage_pct": round(max_slippage, 3),
        "by_side": {
            side: {
                "count": len(v),
                "avg_slippage_pct": round(sum(v) / len(v), 3) if v else 0.0,
            }
            for side, v in by_side.items()
        },
    }


# ── Aggregate evaluation ─────────────────────────────────────────────────


def full_evaluation(db: Session) -> dict:
    """Run all evaluation tiers and return aggregated result."""
    return {
        "benchmark": benchmark_comparison(db),
        "trade_stats": trade_statistics(db),
        "sharpe_ratio": estimate_sharpe_ratio(db),
        "engine_attribution": dual_engine_attribution(db),
        "signal_quality": signal_quality(db),
    }
