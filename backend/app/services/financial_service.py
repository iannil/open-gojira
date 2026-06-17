"""Financial analysis service — deep analysis using Lixinger financial data."""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.financial import FinancialStatement
from app.models.stock import Stock
from app.models.valuation import ValuationSnapshot
from app.schemas.financial import (
    AnomalyItem,
    AnomalyResponse,
    PeerComparisonResponse,
    PeerData,
    RatioDataPoint,
    RatioTrendResponse,
)
from app.services.lixinger_client import get_lixinger_client

logger = logging.getLogger(__name__)


# ── Industry → financial endpoint routing ───────────────────────────────────
# Mapping itself lives in app.core.industry_registry — re-exported here so the
# many existing callers (`from app.services.financial_service import
# industry_kind`) keep working without a churn pass.
from app.core.industry_registry import industry_kind  # noqa: F401, E402


def _route_financials_fetch(client, kind: str, stock_code: str, metrics, granularity: str):
    """Dispatch get_financials* by industry kind."""
    if kind == "bank":
        return client.get_financials_for_bank(stock_code=stock_code, metrics=metrics, granularity=granularity)
    if kind == "insurance":
        return client.get_financials_for_insurance(stock_code=stock_code, metrics=metrics, granularity=granularity)
    if kind == "security":
        return client.get_financials_for_security(stock_code=stock_code, metrics=metrics, granularity=granularity)
    if kind == "other_financial":
        return client.get_financials_for_other_financial(stock_code=stock_code, metrics=metrics, granularity=granularity)
    return client.get_financials(stock_code=stock_code, metrics=metrics, granularity=granularity)


def fetch_and_store_financials(
    db: Session,
    stock_code: str,
    years: int = 5,
    granularity: str = "y",
    store_raw: bool = False,
) -> int:
    """Fetch multi-period financial data from Lixinger and store in DB.

    Args:
        granularity: "y" annual or "q" quarterly. Defaults to annual.
        store_raw: if False (default) the bulky raw_data payload is dropped to keep
            the DB small. Set True only for debugging.
    """
    client = get_lixinger_client()

    g = granularity if granularity in ("y", "q") else "y"
    metrics = [
        f"{g}.ps.toi.t", f"{g}.ps.toi.c_y2y",
        f"{g}.ps.np.t", f"{g}.ps.np.c_y2y",
        f"{g}.ps.gp_m.t", f"{g}.ps.np_s_r.t", f"{g}.ps.beps.t",
        f"{g}.bs.ta.t", f"{g}.bs.tl.t", f"{g}.bs.toe.t",
        f"{g}.bs.tl_ta_r.t", f"{g}.bs.gw.t", f"{g}.bs.tsc.t",
        f"{g}.bs.ar.t",  # Batch 3 (2026-06-17 spike): 应收账款 for ar_growth red flag
        f"{g}.cfs.ncffoa.t", f"{g}.cfs.ncffia.t", f"{g}.cfs.ncfffa.t",
        f"{g}.m.wroe.t", f"{g}.m.roa.t", f"{g}.m.fcf.t",
        f"{g}.m.ncffoa_np_r.t",
        f"{g}.m.i_tor.t",  # Batch 3 (2026-06-17 spike): 存货周转率 for inventory_turnover_drop red flag
        f"{g}.ps.da.t", f"{g}.ps.d_np_r.t",
    ]
    stock = db.query(Stock).filter(Stock.code == stock_code).first()
    kind = industry_kind(stock.industry if stock else None)

    # Bank-specific metric: nim (net interest margin) is the only one
    # accepted by Lixinger's /cn/company/fs/bank endpoint.
    # npl_r, pcr, ct1c_r, gp_m are NOT valid for the bank endpoint.
    bank_metrics = [f"{g}.m.nim.t"]

    if kind == "bank":
        bank_base = [
            f"{g}.ps.toi.t", f"{g}.ps.np.t", f"{g}.ps.np.c_y2y",
            f"{g}.ps.np_s_r.t", f"{g}.ps.beps.t",
            f"{g}.ps.da.t", f"{g}.ps.d_np_r.t",
            f"{g}.bs.ta.t", f"{g}.bs.tl.t", f"{g}.bs.toe.t",
            f"{g}.bs.tl_ta_r.t", f"{g}.bs.gw.t", f"{g}.bs.tsc.t",
            f"{g}.cfs.ncffoa.t", f"{g}.cfs.ncffia.t", f"{g}.cfs.ncfffa.t",
            f"{g}.m.wroe.t", f"{g}.m.roa.t", f"{g}.m.fcf.t",
            f"{g}.m.ncffoa_np_r.t",
        ]
        data_y = _route_financials_fetch(
            client, kind, stock_code, bank_base + bank_metrics, g,
        )
    elif kind != "non_financial":
        data_y = _route_financials_fetch(client, kind, stock_code, None, g)
    else:
        data_y = client.get_financials(stock_code=stock_code, metrics=metrics, granularity=g)
    # Limit to recent N annual reports (quarterly: N*4)
    limit = years if g == "y" else years * 4
    data_y = data_y[:limit]

    report_type = "annual" if g == "y" else "quarterly"

    count = 0
    for item in data_y:
        y = item.get(g, {})
        ps = y.get("ps", {})
        bs = y.get("bs", {})
        cfs = y.get("cfs", {})
        m = y.get("m", {})

        report_date_str = item.get("date", "")[:10]
        from datetime import date as date_type
        try:
            parts = report_date_str.split("-")
            report_date = date_type(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, IndexError):
            report_date = None

        # Convert to datetime for DB compatibility (column type is DateTime)
        if report_date:
            from datetime import datetime as dt
            report_date = dt(report_date.year, report_date.month, report_date.day)
        revenue = _get_nested(ps, "toi.t")
        ocf = _get_nested(cfs, "ncffoa.t")
        icf = _get_nested(cfs, "ncffia.t")
        fcf = _get_nested(cfs, "ncfffa.t")
        np_val = _get_nested(ps, "np.t")

        stmt = FinancialStatement(
            stock_code=stock_code,
            report_date=report_date,
            report_type=report_type,
            revenue=revenue,
            revenue_growth=_get_nested(ps, "toi.c_y2y"),
            net_profit=np_val,
            net_profit_growth=_get_nested(ps, "np.c_y2y"),
            gross_margin=_get_nested(ps, "gp_m.t"),
            net_margin=_get_nested(ps, "np_s_r.t"),
            eps_basic=_get_nested(ps, "beps.t"),
            total_assets=_get_nested(bs, "ta.t"),
            total_liabilities=_get_nested(bs, "tl.t"),
            shareholders_equity=_get_nested(bs, "toe.t"),
            current_ratio=_get_nested(bs, "c_r.t"),
            debt_ratio=_get_nested(bs, "tl_ta_r.t"),
            goodwill=_get_nested(bs, "gw.t"),
            total_shares=_get_nested(bs, "tsc.t"),
            operating_cash_flow=ocf,
            investing_cash_flow=icf,
            financing_cash_flow=fcf,
            free_cash_flow=_get_nested(m, "fcf.t"),
            ocf_to_profit_ratio=_get_nested(m, "ncffoa_np_r.t"),
            roe=_get_nested(m, "wroe.t"),
            roa=_get_nested(m, "roa.t"),
            dividend_payout_ratio=_get_nested(ps, "d_np_r.t"),
            dividends_paid=_get_nested(ps, "da.t"),
            npl_ratio=_get_nested(bs, "npl_r.t"),
            provision_coverage_ratio=_get_nested(m, "pcr.t"),
            net_interest_margin=_get_nested(m, "nim.t"),
            core_tier1_car=_get_nested(m, "ct1c_r.t"),
            # Batch 3 (2026-06-17 spike): red flag fields (invest1 §三 + invest2 §10)
            accounts_receivable=_get_nested(bs, "ar.t"),
            inventory_turnover_ratio=_get_nested(m, "i_tor.t"),
            audit_opinion=item.get("auditOpinionType"),
            raw_data=item if (store_raw or kind == "bank") else None,
        )
        # Upsert: query existing record to avoid duplicates
        existing = (
            db.query(FinancialStatement)
            .filter(
                FinancialStatement.stock_code == stock_code,
                FinancialStatement.report_date == report_date,
                FinancialStatement.report_type == report_type,
            )
            .first()
        )
        if existing:
            for col in [
                "revenue", "revenue_growth", "net_profit", "net_profit_growth",
                "gross_margin", "net_margin", "eps_basic", "total_assets",
                "total_liabilities", "shareholders_equity", "current_ratio",
                "debt_ratio", "goodwill", "total_shares", "operating_cash_flow",
                "investing_cash_flow", "financing_cash_flow", "free_cash_flow",
                "ocf_to_profit_ratio", "roe", "roa", "dividend_payout_ratio",
                "dividends_paid", "npl_ratio", "provision_coverage_ratio",
                "net_interest_margin", "core_tier1_car",
                "accounts_receivable", "inventory_turnover_ratio", "audit_opinion",
                "raw_data",
            ]:
                setattr(existing, col, getattr(stmt, col))
        else:
            db.add(stmt)
        count += 1

    db.commit()
    return count


def get_financial_statements(
    db: Session, stock_code: str, limit: int = 20
) -> list[FinancialStatement]:
    return (
        db.query(FinancialStatement)
        .filter(FinancialStatement.stock_code == stock_code)
        .order_by(FinancialStatement.report_date.desc())
        .limit(limit)
        .all()
    )


def get_ratio_trends(db: Session, stock_code: str) -> RatioTrendResponse:
    """Get financial ratio trends from stored statements.

    Quarterly output is TTM-rolled (revenue/net_profit summed over trailing 4
    quarters, growth = current_ttm / prior_ttm - 1). Point-in-time ratios
    (ROE, gross_margin, etc.) are taken from the quarter itself.
    """
    stmts = (
        db.query(FinancialStatement)
        .filter(FinancialStatement.stock_code == stock_code)
        .order_by(FinancialStatement.report_date.asc())
        .all()
    )

    annual = []
    for s in stmts:
        if s.report_type == "annual":
            annual.append(RatioDataPoint(
                date=str(s.report_date)[:10] if s.report_date else "",
                roe=s.roe,
                roa=s.roa,
                gross_margin=s.gross_margin,
                net_margin=s.net_margin,
                debt_ratio=s.debt_ratio,
                ocf_to_profit_ratio=s.ocf_to_profit_ratio,
                revenue_growth=s.revenue_growth,
                net_profit_growth=s.net_profit_growth,
            ))

    quarterly = compute_ttm_series([s for s in stmts if s.report_type == "quarterly"])

    return RatioTrendResponse(stock_code=stock_code, annual=annual, quarterly=quarterly)


def compute_ttm_series(quarterly_stmts: list[FinancialStatement]) -> list[RatioDataPoint]:
    """Roll quarterly statements into TTM (trailing 4 quarters) data points.

    Input must be sorted ascending by report_date. A TTM point requires the
    current quarter + 3 prior quarters; earlier points yield None for
    flow-based fields (revenue/net_profit) but keep point-in-time ratios.
    """
    out: list[RatioDataPoint] = []
    for i, s in enumerate(quarterly_stmts):
        window = quarterly_stmts[max(0, i - 3): i + 1]
        revenue_ttm: Optional[float] = None
        np_ttm: Optional[float] = None
        if len(window) == 4 and all(w.revenue is not None for w in window):
            revenue_ttm = sum(w.revenue for w in window)
        if len(window) == 4 and all(w.net_profit is not None for w in window):
            np_ttm = sum(w.net_profit for w in window)

        # TTM growth vs same TTM one year ago (4 quarters back)
        revenue_growth_ttm: Optional[float] = None
        np_growth_ttm: Optional[float] = None
        if i >= 4 and revenue_ttm is not None:
            prior_window = quarterly_stmts[max(0, i - 7): i - 3]
            if len(prior_window) == 4 and all(w.revenue is not None for w in prior_window):
                prior_rev = sum(w.revenue for w in prior_window)
                if prior_rev:
                    revenue_growth_ttm = (revenue_ttm - prior_rev) / abs(prior_rev) * 100
        if i >= 4 and np_ttm is not None:
            prior_window = quarterly_stmts[max(0, i - 7): i - 3]
            if len(prior_window) == 4 and all(w.net_profit is not None for w in prior_window):
                prior_np = sum(w.net_profit for w in prior_window)
                if prior_np:
                    np_growth_ttm = (np_ttm - prior_np) / abs(prior_np) * 100

        out.append(RatioDataPoint(
            date=str(s.report_date)[:10] if s.report_date else "",
            roe=s.roe,
            roa=s.roa,
            gross_margin=s.gross_margin,
            net_margin=s.net_margin,
            debt_ratio=s.debt_ratio,
            ocf_to_profit_ratio=s.ocf_to_profit_ratio,
            revenue_growth=revenue_growth_ttm if revenue_growth_ttm is not None else s.revenue_growth,
            net_profit_growth=np_growth_ttm if np_growth_ttm is not None else s.net_profit_growth,
        ))
    return out


def get_peer_comparison(db: Session, stock_code: str) -> PeerComparisonResponse:
    """Industry-peer comparison — delegates to valuation_service.compare_stocks
    after resolving the industry peer codes locally.
    """
    from app.services.valuation_service import compare_stocks

    stock = db.query(Stock).filter(Stock.code == stock_code).first()
    industry = stock.industry if stock else None

    peer_codes: list[str] = []
    if industry:
        local_peers = (
            db.query(Stock.code)
            .filter(Stock.industry == industry, Stock.code != stock_code)
            .limit(10)
            .all()
        )
        peer_codes = [row[0] for row in local_peers]

    peers_data: list[PeerData] = []
    if peer_codes:
        result = compare_stocks(db, [stock_code, *peer_codes])
        for s in result["stocks"]:
            if s["stock_code"] == stock_code:
                continue
            peers_data.append(PeerData(
                stock_code=s["stock_code"],
                stock_name=s["stock_name"],
                roe=s.get("roe"),
                roa=s.get("roa"),
                gross_margin=s.get("gross_margin"),
                debt_ratio=s.get("debt_ratio"),
                pe_ttm=s.get("pe_ttm"),
                pb=s.get("pb"),
            ))

    return PeerComparisonResponse(stock_code=stock_code, industry=industry, peers=peers_data)


def detect_anomalies(db: Session, stock_code: str) -> AnomalyResponse:
    """Detect financial anomalies from stored statements."""
    stmts = (
        db.query(FinancialStatement)
        .filter(FinancialStatement.stock_code == stock_code, FinancialStatement.report_type == "annual")
        .order_by(FinancialStatement.report_date.desc())
        .limit(5)
        .all()
    )

    anomalies: list[AnomalyItem] = []

    if len(stmts) < 2:
        return AnomalyResponse(stock_code=stock_code, anomalies=anomalies)

    latest = stmts[0]
    prev = stmts[1]

    # 1. Revenue grows but net profit shrinks
    if latest.revenue_growth and latest.net_profit_growth:
        if latest.revenue_growth > 0 and latest.net_profit_growth < 0:
            anomalies.append(AnomalyItem(
                severity="high",
                title="增收不增利",
                detail=f"营收增长 {latest.revenue_growth:.1f}% 但净利润下降 {latest.net_profit_growth:.1f}%，利润率压缩",
                metric="revenue_growth vs net_profit_growth",
            ))

    # 2. OCF/profit ratio low for consecutive years
    low_ocf_years = sum(1 for s in stmts[:3] if s.ocf_to_profit_ratio is not None and s.ocf_to_profit_ratio < 0.5)
    if low_ocf_years >= 2:
        anomalies.append(AnomalyItem(
            severity="high",
            title="经营现金流质量差",
            detail=f"近 {low_ocf_years} 年 OCF/净利润比低于 0.5，盈利质量存疑",
            metric="ocf_to_profit_ratio",
        ))

    # 3. Debt ratio increases while ROE decreases
    if latest.debt_ratio and prev.debt_ratio and latest.roe and prev.roe:
        debt_increase = latest.debt_ratio - prev.debt_ratio
        if debt_increase > 0.1 and latest.roe < prev.roe:
            anomalies.append(AnomalyItem(
                severity="medium",
                title="杠杆上升但ROE下降",
                detail=f"负债率增加 {debt_increase:.1%}，但 ROE 从 {prev.roe:.2f}% 降至 {latest.roe:.2f}%",
                metric="debt_ratio vs roe",
            ))

    # 4. Dividend payout > 100%
    if latest.dividend_payout_ratio and latest.dividend_payout_ratio > 1.0:
        anomalies.append(AnomalyItem(
            severity="medium",
            title="分红率超过100%",
            detail=f"分红率 {latest.dividend_payout_ratio:.1%}，超过净利润，不可持续",
            metric="dividend_payout_ratio",
        ))

    # 5. Goodwill to equity ratio high
    if latest.goodwill and latest.shareholders_equity and latest.shareholders_equity > 0:
        gw_ratio = latest.goodwill / latest.shareholders_equity
        if gw_ratio > 0.3:
            anomalies.append(AnomalyItem(
                severity="medium",
                title="商誉占净资产比例过高",
                detail=f"商誉/净资产 = {gw_ratio:.1%}，存在减值风险",
                metric="goodwill/equity",
            ))

    # 6. Static PB trap — low PB but net assets shrinking
    # Methodology: 地产/银行账面 PB 低，不代表真便宜，因为净资产还会继续减值。
    latest_pb = (
        db.query(ValuationSnapshot)
        .filter(ValuationSnapshot.stock_code == stock_code)
        .order_by(ValuationSnapshot.date.desc())
        .first()
    )
    if latest_pb and latest_pb.pb is not None and latest_pb.pb <= 0.7 and len(stmts) >= 3:
        equity_now = stmts[0].shareholders_equity
        equity_3y_ago = stmts[2].shareholders_equity
        if equity_now and equity_3y_ago and equity_3y_ago > 0:
            equity_change = (equity_now - equity_3y_ago) / equity_3y_ago
            # Threshold: equity shrank or grew less than inflation (≈ <3% over 3y total)
            if equity_change < 0.03:
                anomalies.append(AnomalyItem(
                    severity="high",
                    title="静态 PB 陷阱",
                    detail=(
                        f"PB={latest_pb.pb:.2f} 看似低估，但近 3 年净资产仅变动 {equity_change:+.1%}，"
                        f"账面价值在缩水/停滞——动态低估并不成立"
                    ),
                    metric="pb vs equity_3y_change",
                ))

    return AnomalyResponse(stock_code=stock_code, anomalies=anomalies)


def _get_nested(data: dict, path: str) -> Optional[float]:
    """Get a nested value from a dict using dot-separated path like 'ps.toi.t'."""
    keys = path.split(".")
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current is None:
            return None
    try:
        return float(current)
    except (TypeError, ValueError):
        return None
