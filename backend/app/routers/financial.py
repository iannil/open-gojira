"""Financial analysis endpoints — statements, ratios, peers, anomalies.

Legacy DCF + IntrinsicValue endpoints removed (MR Dang: DCF is "精确的错误").
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.financial import (
    AnomalyResponse,
    FinancialStatementResponse,
    PeerComparisonResponse,
    RatioTrendResponse,
)
from app.services.financial_service import (
    detect_anomalies,
    fetch_and_store_financials,
    get_financial_statements,
    get_peer_comparison,
    get_ratio_trends,
)

router = APIRouter(prefix="/api/financial", tags=["financial"])


@router.get("/{code}/statements", response_model=list[FinancialStatementResponse])
def api_get_statements(code: str, limit: int = 20, db: Session = Depends(get_db)):
    stmts = get_financial_statements(db, code, limit=limit)
    return [_stmt_to_response(s) for s in stmts]


@router.post("/{code}/fetch", response_model=dict)
def api_fetch_financials(
    code: str,
    years: int = 5,
    granularity: str = "y",
    db: Session = Depends(get_db),
):
    count = fetch_and_store_financials(db, code, years=years, granularity=granularity)
    return {"imported": count, "granularity": granularity}


@router.get("/{code}/ratios", response_model=RatioTrendResponse)
def api_get_ratio_trends(code: str, db: Session = Depends(get_db)):
    return get_ratio_trends(db, code)


@router.get("/{code}/peer-comparison", response_model=PeerComparisonResponse)
def api_get_peer_comparison(code: str, db: Session = Depends(get_db)):
    return get_peer_comparison(db, code)


@router.get("/{code}/anomalies", response_model=AnomalyResponse)
def api_get_anomalies(code: str, db: Session = Depends(get_db)):
    return detect_anomalies(db, code)


def _stmt_to_response(s) -> FinancialStatementResponse:
    return FinancialStatementResponse(
        id=s.id,
        stock_code=s.stock_code,
        report_date=str(s.report_date)[:10] if s.report_date else "",
        report_type=s.report_type,
        revenue=s.revenue,
        revenue_growth=s.revenue_growth,
        net_profit=s.net_profit,
        net_profit_growth=s.net_profit_growth,
        gross_margin=s.gross_margin,
        net_margin=s.net_margin,
        eps_basic=s.eps_basic,
        total_assets=s.total_assets,
        total_liabilities=s.total_liabilities,
        shareholders_equity=s.shareholders_equity,
        current_ratio=s.current_ratio,
        debt_ratio=s.debt_ratio,
        goodwill=s.goodwill,
        total_shares=s.total_shares,
        operating_cash_flow=s.operating_cash_flow,
        investing_cash_flow=s.investing_cash_flow,
        financing_cash_flow=s.financing_cash_flow,
        free_cash_flow=s.free_cash_flow,
        ocf_to_profit_ratio=s.ocf_to_profit_ratio,
        roe=s.roe,
        roa=s.roa,
        dividend_payout_ratio=s.dividend_payout_ratio,
        dividends_paid=s.dividends_paid,
    )
