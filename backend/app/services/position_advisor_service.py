"""Position advisor service — 组合级仓位约束检查.

Implements invest3 "仓位控制高于一切":
  - 持仓 3-4 只上限
  - 单只 10-50% 区间
  - 行业分散度 15% 上限
  - 与周期联动：低位允许超配，高位强制减配
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.draft import Draft
from app.models.stock import Stock
from app.services.holding_view_service import get_holding_view

logger = logging.getLogger(__name__)

# invest3 投资体系约束
TARGET_HOLDINGS_RANGE = (3, 4)
MAX_SINGLE_POSITION = 0.50   # 50%
MIN_SINGLE_POSITION = 0.10   # 10%
MAX_INDUSTRY_WEIGHT = 0.15   # 15%

# M5 (Batch 5 2026-06-17): tier-aware position caps (Core-Satellite Model).
# invest2 §1.3 / invest3 第四层 "对待投机: 懂投机但视为'邪修', 可小仓位玩预期差,
# 但绝不把别人出高价的理由, 当成自己重仓高位接盘的理由".
MAX_SINGLE_BY_TIER: dict[str | None, float] = {
    "core": 0.50,        # 核心仓位单只上限 50%
    "satellite": 0.10,   # 卫星仓位单只上限 10% (invest2 §1.3 "小仓位")
    "focus": 0.50,       # 重点按 core 处理
    None: 0.50,          # 未分类按 core 处理
}
TOTAL_SATELLITE_MAX = 0.20  # 组合内 satellite 总仓位 ≤ 20% (invest2 §1.3 "绝不重仓接盘")


@dataclass
class PositionAdvice:
    holdings_count: int
    target_range: tuple[int, int]
    diversification_warnings: list[str] = field(default_factory=list)
    can_open_new: bool = True
    blockers: list[str] = field(default_factory=list)
    position_suggestions: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "holdings_count": self.holdings_count,
            "target_range": list(self.target_range),
            "diversification_warnings": self.diversification_warnings,
            "can_open_new": self.can_open_new,
            "blockers": self.blockers,
            "position_suggestions": self.position_suggestions,
        }


def _open_holdings(db: Session) -> list[dict]:
    """Current open positions, derived from trades via holding_view_service.

    Returns list of dicts (not ORM Holding rows):
        { stock_code, total_quantity, avg_cost_basis, first_buy_at, last_trade_at }
    """
    return get_holding_view(db)


def _pending_buy_drafts(db: Session) -> list[Draft]:
    return list(
        db.execute(
            select(Draft).where(
                Draft.status == "pending",
                Draft.side == "BUY",
            )
        ).scalars().all()
    )


def _pending_sell_drafts(db: Session) -> list[Draft]:
    return list(
        db.execute(
            select(Draft).where(
                Draft.status == "pending",
                Draft.side == "SELL",
            )
        ).scalars().all()
    )


def _industry_weights(holdings: list[dict], db: Session) -> dict[str, float]:
    """Calculate industry concentration from open holdings (dicts)."""
    if not holdings:
        return {}

    # Batch-load all stocks to avoid N+1
    codes = [h["stock_code"] for h in holdings]
    stocks_map = {
        s.code: s
        for s in db.execute(select(Stock).where(Stock.code.in_(codes))).scalars().all()
    }

    total_value = 0.0
    by_industry: dict[str, float] = {}

    for h in holdings:
        stock = stocks_map.get(h["stock_code"])
        if not stock:
            continue
        price = _latest_price_for_code(h["stock_code"], h, db)
        value = price * h["total_quantity"]
        total_value += value
        ind = stock.industry or "unknown"
        by_industry[ind] = by_industry.get(ind, 0.0) + value

    if total_value == 0:
        return {}

    return {ind: v / total_value for ind, v in by_industry.items()}


def _current_satellite_weight(holdings: list[dict], db: Session) -> float:
    """M5: sum of portfolio weight held in tier='satellite' stocks.

    Used for TOTAL_SATELLITE_MAX check (invest2 §1.3 组合级卫星仓位上限).
    Returns 0.0 if no holdings or no satellite stocks held.
    """
    if not holdings:
        return 0.0
    codes = [h["stock_code"] for h in holdings]
    stocks_map = {
        s.code: s
        for s in db.execute(select(Stock).where(Stock.code.in_(codes))).scalars().all()
    }
    total_value = 0.0
    satellite_value = 0.0
    for h in holdings:
        stock = stocks_map.get(h["stock_code"])
        if not stock:
            continue
        price = _latest_price_for_code(h["stock_code"], h, db)
        value = price * h["total_quantity"]
        total_value += value
        if stock.tier == "satellite":
            satellite_value += value
    if total_value == 0:
        return 0.0
    return satellite_value / total_value


def _latest_price_for_code(
    stock_code: str, holding: dict | None, db: Session
) -> float:
    """Best-effort current price for a stock code.

    Order of preference:
        1. cached live price from data_service
        2. avg_cost_basis from the holding dict (fallback for tests/offline)
    """
    from app.services.holding_service import _get_cached_price
    try:
        price = _get_cached_price(stock_code)
        if price:
            return price
    except Exception:
        pass
    if holding is not None:
        return float(holding.get("avg_cost_basis", 0.0) or 0.0)
    return 0.0


def check_before_draft(
    db: Session,
    stock_code: str,
    side: str,
    cycle_position: str | None = None,
) -> PositionAdvice:
    """Check portfolio constraints before generating a new draft.

    Args:
        db: Database session
        stock_code: Target stock code
        side: "BUY" or "SELL"
        cycle_position: Current market cycle position from cycle_assessment

    Returns:
        PositionAdvice with constraint check results
    """
    holdings = _open_holdings(db)
    pending_buys = _pending_buy_drafts(db)
    pending_sells = _pending_sell_drafts(db)
    ind_weights = _industry_weights(holdings, db)
    min_holdings, max_holdings = TARGET_HOLDINGS_RANGE

    warnings: list[str] = []
    blockers: list[str] = []

    # Effective holdings = current + pending buys - pending sells
    effective_count = max(0, len(holdings) + len(pending_buys) - len(pending_sells))

    # --- SELL: no constraints, always allowed ---
    if side == "SELL":
        return PositionAdvice(
            holdings_count=len(holdings),
            target_range=TARGET_HOLDINGS_RANGE,
            can_open_new=True,
            diversification_warnings=warnings,
        )

    # --- BUY constraints ---

    # 1. Holdings count check
    if effective_count >= max_holdings:
        blockers.append(
            f"已有 {len(holdings)} 只持仓 + {len(pending_buys)} 只待执行买入，"
            f"超过上限 {max_holdings} 只"
        )

    # 2. Industry concentration check
    # Skip if adding to an existing position (invest system allows adding to winners)
    already_held = any(h["stock_code"] == stock_code for h in holdings)
    stock = db.get(Stock, stock_code)
    if not already_held and stock and stock.industry:
        current_ind_weight = ind_weights.get(stock.industry, 0.0)
        if current_ind_weight >= MAX_INDUSTRY_WEIGHT:
            blockers.append(
                f"行业 '{stock.industry}' 当前权重 {current_ind_weight:.0%}，"
                f"已达到 {MAX_INDUSTRY_WEIGHT:.0%} 上限"
            )
        elif current_ind_weight > MAX_INDUSTRY_WEIGHT * 0.8:
            warnings.append(
                f"行业 '{stock.industry}' 当前权重 {current_ind_weight:.0%}，"
                f"接近 {MAX_INDUSTRY_WEIGHT:.0%} 上限"
            )

    # 2b. M5 (Batch 5): tier-aware position caps.
    # invest2 §1.3 + invest3 第四层: satellite 标的"小仓位玩预期差".
    if stock and stock.tier == "satellite":
        # Single satellite position hard cap 10%
        # (We don't know the proposed weight at this stage — the caller will
        # surface this constraint when computing suggested_quantity. The
        # blocker here fires conservatively if any satellite already held.)
        current_sat = _current_satellite_weight(holdings, db)
        if not already_held and current_sat >= TOTAL_SATELLITE_MAX:
            blockers.append(
                f"卫星仓位 (satellite tier) 当前总权重 {current_sat:.0%}，"
                f"已达到组合上限 {TOTAL_SATELLITE_MAX:.0%} "
                f"(invest2 §1.3 '绝不重仓接盘')"
            )
        elif not already_held and current_sat > TOTAL_SATELLITE_MAX * 0.8:
            warnings.append(
                f"卫星仓位当前总权重 {current_sat:.0%}，"
                f"接近组合上限 {TOTAL_SATELLITE_MAX:.0%} (invest2 §1.3)"
            )

    # 3. Cycle-based position check (invest2 §5 硬纪律)
    # D5 (2026-06-17 invest-alignment): extreme_high 升级为 blocker,
    # 但保留加仓赢家通道 (invest1 §二 "去弱留强"在任何位置都应保留强者)。
    # high 仍 warning,留给用户判断。
    if cycle_position == "extreme_high":
        if already_held:
            warnings.append(
                f"市场周期处于 '{cycle_position}',新信号保留加仓赢家通道 "
                f"(invest1 §二 去弱留强)"
            )
        else:
            blockers.append(
                f"市场极度高估 (cycle='{cycle_position}'),不开新仓 "
                f"(invest2 §5 '极高高位尽量空仓' 硬纪律)"
            )
    elif cycle_position == "high":
        warnings.append(
            f"市场周期处于 '{cycle_position}'，不建议开新仓"
        )

    can_open = len(blockers) == 0

    return PositionAdvice(
        holdings_count=len(holdings),
        target_range=TARGET_HOLDINGS_RANGE,
        can_open_new=can_open,
        blockers=blockers,
        diversification_warnings=warnings,
    )
