"""Valuation service — core calculation functions for multi-method valuation.

Implements the theory's valuation methodology from 天阶功法卷二:
"PE为主，PB为辅，股息为先，增速为次" — PE primary, PB secondary,
dividend first, growth second.

The "遛狗" (dog-walking) metaphor: value is the person, price is the dog,
valuation is the leash.
"""

import logging
from datetime import date, datetime
from typing import Optional

import numpy as np
from sqlalchemy.orm import Session

from app.models.financial import FinancialStatement
from app.models.stock import Stock
from app.models.valuation import ValuationSnapshot

logger = logging.getLogger(__name__)


def calculate_percentiles(pe_pb_history: list[dict]) -> dict:
    """Calculate percentile bands for PE and PB from historical data.

    Args:
        pe_pb_history: Array of {date, pe_ttm, pb} entries (10 years daily).

    Returns:
        Dict with pe_bands, pb_bands, current values, current percentiles,
        and the original data_points.
    """
    if not pe_pb_history:
        return {
            "pe_bands": [],
            "pb_bands": [],
            "current_pe": None,
            "current_pb": None,
            "current_pe_percentile": None,
            "current_pb_percentile": None,
            "data_points": [],
        }

    # Extract PE and PB arrays, filtering out zeros/None
    pe_values = np.array(
        [entry["pe_ttm"] for entry in pe_pb_history if entry.get("pe_ttm")],
        dtype=float,
    )
    pb_values = np.array(
        [entry["pb"] for entry in pe_pb_history if entry.get("pb")],
        dtype=float,
    )

    percentiles = [10, 30, 50, 70, 90]

    pe_bands = []
    if len(pe_values) > 0:
        for p in percentiles:
            pe_bands.append({"percentile": p, "value": round(float(np.percentile(pe_values, p)), 4)})

    pb_bands = []
    if len(pb_values) > 0:
        for p in percentiles:
            pb_bands.append({"percentile": p, "value": round(float(np.percentile(pb_values, p)), 4)})

    # Current values are from the latest entry
    current_entry = pe_pb_history[-1]
    current_pe = current_entry.get("pe_ttm")
    current_pb = current_entry.get("pb")

    # Calculate current percentile rank
    current_pe_percentile = None
    if current_pe and len(pe_values) > 0:
        current_pe_percentile = round(
            float(np.sum(pe_values <= current_pe) / len(pe_values) * 100), 2
        )

    current_pb_percentile = None
    if current_pb and len(pb_values) > 0:
        current_pb_percentile = round(
            float(np.sum(pb_values <= current_pb) / len(pb_values) * 100), 2
        )

    # Data points for charting
    data_points = [
        {
            "date": entry["date"],
            "pe_ttm": entry.get("pe_ttm"),
            "pb": entry.get("pb"),
        }
        for entry in pe_pb_history
    ]

    return {
        "pe_bands": pe_bands,
        "pb_bands": pb_bands,
        "current_pe": current_pe,
        "current_pb": current_pb,
        "current_pe_percentile": current_pe_percentile,
        "current_pb_percentile": current_pb_percentile,
        "data_points": data_points,
    }


def calculate_forward_dyr(
    db: Session, stock_code: str, current_price: Optional[float] = None,
) -> dict:
    """Forward (predicted) dividend yield.

    Methodology (invest3 §八): 预期股息率 > 过去股息率. 该模型用近 3 年实际
    分红率的均值 × 最新 EPS / 现价，作为对下一年股息率的近似预估。

    Returns dict with: forward_dyr, payout_ratio_avg_3y, eps, current_price,
    trailing_dyr, basis_note. None values when inputs are missing.
    """
    stmts = (
        db.query(FinancialStatement)
        .filter(
            FinancialStatement.stock_code == stock_code,
            FinancialStatement.report_type == "annual",
        )
        .order_by(FinancialStatement.report_date.desc())
        .limit(3)
        .all()
    )

    payouts = [s.dividend_payout_ratio for s in stmts if s.dividend_payout_ratio is not None]
    payout_avg = sum(payouts) / len(payouts) if payouts else None

    latest_eps = stmts[0].eps_basic if stmts and stmts[0].eps_basic is not None else None

    # Try live price; fall back to ValuationSnapshot-derived if unavailable.
    if current_price is None:
        try:
            from app.services.data_service import fetch_current_price
            current_price = fetch_current_price(stock_code)
        except Exception:  # noqa: BLE001
            current_price = None

    # Cap payout at 1.0 (100%) to avoid unrealistic forward DYR
    payout_capped = max(0.0, min(payout_avg, 1.0)) if payout_avg is not None else None

    forward_dyr = None
    if payout_capped is not None and latest_eps is not None and current_price and current_price > 0:
        forward_dyr = (payout_capped * latest_eps) / current_price

    # Trailing yield for comparison
    latest_snap = (
        db.query(ValuationSnapshot)
        .filter(ValuationSnapshot.stock_code == stock_code)
        .order_by(ValuationSnapshot.date.desc())
        .first()
    )
    trailing_dyr = latest_snap.dividend_yield if latest_snap else None

    return {
        "stock_code": stock_code,
        "forward_dyr": forward_dyr,
        "payout_ratio_avg_3y": payout_avg,
        "eps": latest_eps,
        "current_price": current_price,
        "trailing_dyr": trailing_dyr,
        "basis_note": (
            (
                f"按近 {len(payouts)} 年均值 {payout_avg:.1%} 的分红率（截断至 {payout_capped:.1%}） × EPS {latest_eps:.2f} / 现价 {current_price:.2f}"
                if payout_avg != payout_capped
                else f"按近 {len(payouts)} 年均值 {payout_avg:.1%} 的分红率 × EPS {latest_eps:.2f} / 现价 {current_price:.2f}"
            )
            if forward_dyr is not None and current_price else "数据不全无法估算"
        ),
    }


def check_dividend_sustainability(
    operating_cash_flow: float,
    net_profit: float,
    dividends_paid: float,
) -> dict:
    """Check whether dividends are sustainable based on cash flow analysis.

    Args:
        operating_cash_flow: Operating cash flow (经营现金流).
        net_profit: Net profit attributable to shareholders (归母净利润).
        dividends_paid: Total dividends paid (分红金额).

    Returns:
        Dict with {status, message} indicating sustainability level.
    """
    if operating_cash_flow == 0 and net_profit == 0 and dividends_paid == 0:
        return {
            "status": "data_unavailable",
            "message": "三项指标均为 0，数据不可用",
        }
    if operating_cash_flow >= net_profit >= dividends_paid:
        return {
            "status": "healthy",
            "message": "经营现金流≥归母净利润≥分红，分红可持续",
        }
    elif dividends_paid > net_profit and operating_cash_flow >= dividends_paid:
        return {
            "status": "needs_verification",
            "message": "分红>净利润但经营现金流支持，需进一步验证",
        }
    elif dividends_paid > operating_cash_flow:
        return {
            "status": "unsustainable",
            "message": "分红>经营现金流，分红可能不可持续",
        }
    else:
        # OCF < net_profit but dividends <= net_profit
        return {
            "status": "caution",
            "message": "经营现金流<净利润，需关注现金流质量",
        }


def get_valuation_dashboard(db: Session, stock_code: str) -> dict:
    """Aggregate all valuation data for a stock's dashboard.

    Args:
        db: SQLAlchemy session.
        stock_code: Stock code.

    Returns:
        Dict with latest snapshot, real-time data, sustainability check,
        and an inline composite valuation (signal/floor/fair/ceiling).
    """
    from app.services.data_service import fetch_pe_pb_history
    from app.services.lixinger_client import get_lixinger_client, LixingerError

    # Get the latest snapshot
    latest_snapshot = (
        db.query(ValuationSnapshot)
        .filter(ValuationSnapshot.stock_code == stock_code)
        .order_by(ValuationSnapshot.date.desc())
        .first()
    )

    # Get all snapshots for history
    all_snapshots = (
        db.query(ValuationSnapshot)
        .filter(ValuationSnapshot.stock_code == stock_code)
        .order_by(ValuationSnapshot.date.desc())
        .all()
    )

    # Fetch real-time PE/PB/price from Lixinger, dispatching to the matching
    # industry endpoint. /non_financial returns empty for banks/insurance/
    # securities — that was the long-standing cause of None on the dashboard.
    from app.services.financial_service import industry_kind

    realtime: dict = {}
    stock = db.query(Stock).filter(Stock.code == stock_code).first()
    primary_kind = industry_kind(stock.industry if stock else None)

    # Try the primary endpoint first, then fall back through other industry
    # endpoints. Two failure modes this guards against:
    #   1. Stock has no industry → kind defaults to non_financial → banks
    #      / insurance / securities return empty.
    #   2. Batch endpoint occasionally returns rows with all-None metrics
    #      for blue chips; a single-stock retry on another endpoint often
    #      resolves it.
    # Stops as soon as pe_ttm (the most decision-relevant metric) is found.
    fallback_order = [primary_kind] + [
        k for k in ("non_financial", "bank", "insurance", "security", "other_financial")
        if k != primary_kind
    ]
    realtime_metrics = ["pe_ttm", "pb", "sp", "dyr", "mc"]
    client = get_lixinger_client()
    for kind in fallback_order:
        try:
            data = client.get_fundamentals_at_endpoint(
                endpoint_kind=kind,
                stock_codes=[stock_code],
                metrics=realtime_metrics,
            )
        except LixingerError:
            logger.warning(
                "dashboard fetch failed kind=%s code=%s", kind, stock_code
            )
            continue
        if not data:
            continue
        item = data[0]
        if item.get("pe_ttm") is None and item.get("sp") is None:
            continue
        realtime = {
            "current_pe": item.get("pe_ttm"),
            "current_pb": item.get("pb"),
            "current_price": item.get("sp"),
            "dividend_yield": item.get("dyr"),
            "market_cap": item.get("mc"),
            "_realtime_source": kind,
        }
        if kind != primary_kind:
            logger.info(
                "dashboard fallback: %s resolved via %s (primary=%s)",
                stock_code, kind, primary_kind,
            )
        break

    result: dict = {
        "stock_code": stock_code,
        "latest_snapshot": None,
        "snapshots": [],
        "sustainability": None,
        "composite": None,
    }

    if latest_snapshot:
        result["latest_snapshot"] = snapshot_to_response(latest_snapshot)

    # Sustainability + projected EPS now come from the latest annual
    # FinancialStatement (the same source as /valuation/{code}/prefill),
    # not from snapshot columns that were never populated.
    latest_fs = (
        db.query(FinancialStatement)
        .filter(
            FinancialStatement.stock_code == stock_code,
            FinancialStatement.report_type == "annual",
        )
        .order_by(FinancialStatement.report_date.desc())
        .first()
    )
    if latest_fs and all([
        latest_fs.operating_cash_flow,
        latest_fs.net_profit,
        latest_fs.dividends_paid,
    ]):
        result["sustainability"] = check_dividend_sustainability(
            operating_cash_flow=latest_fs.operating_cash_flow,
            net_profit=latest_fs.net_profit,
            dividends_paid=latest_fs.dividends_paid,
        )

    result["snapshots"] = [snapshot_to_response(s) for s in all_snapshots]
    result.update(realtime)

    # Composite valuation removed: investment system rejects precise valuation ("精算")
    result["composite"] = None

    return result


def snapshot_to_response(snapshot: ValuationSnapshot) -> dict:
    """Convert a ValuationSnapshot ORM object to a plain dict."""
    return {
        "id": snapshot.id,
        "stock_code": snapshot.stock_code,
        "date": str(snapshot.date) if snapshot.date else None,
        "pe_ttm": snapshot.pe_ttm,
        "pb": snapshot.pb,
        "pe_percentile_10y": snapshot.pe_percentile_10y,
        "pb_percentile_10y": snapshot.pb_percentile_10y,
        "dividend_yield": snapshot.dividend_yield,
        "created_at": str(snapshot.created_at) if snapshot.created_at else None,
    }



# compare_stocks removed: investment system opposes mechanical peer comparison.
# Selection follows top-down design (宏观→商业模式→估值), not bottom-up screening.

