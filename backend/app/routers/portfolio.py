"""Portfolio endpoints — read-only views derived from the Trade ledger.

Q2-A (2026-06-26): positions are derived from trades (position_service); there
is no Holding write path. Entry/exit happens by recording trades (CSV import /
Draft confirm / manual /trades), so the old create/update/delete/sell endpoints
are gone. What remains are read views (list / summary) and T+1 availability.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.datetime_utils import now
from app.db.session import get_db
from app.models.stock import Stock
from app.models.trade import Trade
from app.schemas.holding import (
    AvailableQuantityResponse,
    HoldingResponse,
    PortfolioSummary,
)
from app.services import position_service
from app.services.holding_service import get_portfolio_summary, list_holdings
from app.services.evaluation_service import full_evaluation

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/summary", response_model=PortfolioSummary)
def summary(db: Session = Depends(get_db)):
    return get_portfolio_summary(db)


@router.get("", response_model=list[HoldingResponse])
def list_all(active_only: bool = False, db: Session = Depends(get_db)):
    return list_holdings(db, active_only=active_only)


@router.get("/{code}/available", response_model=AvailableQuantityResponse)
def get_available_quantity(code: str, db: Session = Depends(get_db)):
    """T+1 share counts for a stock, derived from the trade ledger:
    - total:     current open position size (net of buys/sells)
    - available: sellable today (excludes shares bought today)
    - frozen:    shares bought today (T+1, not yet settled)
    """
    if not db.query(Stock).filter(Stock.code == code).first():
        raise HTTPException(status_code=404, detail=f"Stock {code} not found")
    today: date = now().date()
    available = position_service.available_quantity(db, code, today)
    pos = position_service.position_for(db, code, price_lookup=lambda _c: None)
    total = pos.quantity if pos else 0
    frozen = max(0, total - available)
    return AvailableQuantityResponse(
        code=code,
        available=available,
        frozen=frozen,
        total=total,
    )


@router.get("/evaluation")
def evaluate(db: Session = Depends(get_db)):
    """P1 评价系统: 基准对比 + 夏普 + 交易统计 + 双引擎归因 + 信号质量.`"""
    return full_evaluation(db)
