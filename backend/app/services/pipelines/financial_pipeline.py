"""Financial pipeline — sync financial statements from Lixinger with industry routing."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.datetime_utils import utcnow
from app.models.financial import FinancialStatement
from app.models.stock import Stock
from app.services.pipelines.base import BasePipeline, PipelineContext
from app.services.pipelines.manager import register_pipeline

logger = logging.getLogger(__name__)


def _get_nested(data: dict, path: str) -> Optional[float]:
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


def _route_fetch(client, kind: str, stock_code: str, metrics, granularity: str):
    if kind == "bank":
        return client.get_financials_for_bank(stock_code=stock_code, metrics=metrics, granularity=granularity)
    if kind == "insurance":
        return client.get_financials_for_insurance(stock_code=stock_code, metrics=metrics, granularity=granularity)
    if kind == "security":
        return client.get_financials_for_security(stock_code=stock_code, metrics=metrics, granularity=granularity)
    if kind == "other_financial":
        return client.get_financials_for_other_financial(stock_code=stock_code, metrics=metrics, granularity=granularity)
    return client.get_financials(stock_code=stock_code, metrics=metrics, granularity=granularity)


@register_pipeline
class FinancialPipeline(BasePipeline):
    """Sync financial statements with industry-specific API routing.

    Supports both annual and quarterly granularity. Uses upsert via
    unique constraint (stock_code, report_date, report_type).
    """

    pipeline_type = "financials"

    def extract(self, stock_code: str, ctx: PipelineContext) -> list[dict]:
        from app.services.lixinger_client import get_lixinger_client

        client = get_lixinger_client()
        granularity = ctx.extra.get("granularity", "y")
        g = granularity if granularity in ("y", "q") else "y"

        metrics = self._build_metrics(g)
        stock = self.db.query(Stock).filter(Stock.code == stock_code).first()
        from app.core.industry_registry import industry_kind
        kind = industry_kind(stock.industry if stock else None)

        data = _route_fetch(client, kind, stock_code, metrics, g)

        limit = ctx.years if g == "y" else ctx.years * 4
        return data[:limit]

    def _build_metrics(self, g: str) -> list[str]:
        return [
            f"{g}.ps.toi.t", f"{g}.ps.toi.c_y2y",
            f"{g}.ps.np.t", f"{g}.ps.np.c_y2y",
            f"{g}.ps.gp_m.t", f"{g}.ps.np_s_r.t", f"{g}.ps.beps.t",
            f"{g}.bs.ta.t", f"{g}.bs.tl.t", f"{g}.bs.toe.t",
            f"{g}.bs.tl_ta_r.t", f"{g}.bs.gw.t", f"{g}.bs.tsc.t",
            f"{g}.cfs.ncffoa.t", f"{g}.cfs.ncffia.t", f"{g}.cfs.ncfffa.t",
            f"{g}.m.wroe.t", f"{g}.m.roa.t", f"{g}.m.fcf.t",
            f"{g}.m.ncffoa_np_r.t",
            f"{g}.ps.da.t", f"{g}.ps.d_np_r.t",
        ]

    def transform(self, stock_code: str, raw: list[dict], ctx: PipelineContext) -> list[dict]:
        granularity = ctx.extra.get("granularity", "y")
        g = granularity if granularity in ("y", "q") else "y"
        report_type = "annual" if g == "y" else "quarterly"

        results = []
        for item in raw:
            y = item.get(g, {})
            ps = y.get("ps", {})
            bs = y.get("bs", {})
            cfs = y.get("cfs", {})
            m = y.get("m", {})

            report_date_str = item.get("date", "")[:10]
            try:
                parts = report_date_str.split("-")
                rd = date(int(parts[0]), int(parts[1]), int(parts[2]))
            except (ValueError, IndexError):
                continue

            results.append({
                "report_date": datetime(rd.year, rd.month, rd.day),
                "report_type": report_type,
                "revenue": _get_nested(ps, "toi.t"),
                "revenue_growth": _get_nested(ps, "toi.c_y2y"),
                "net_profit": _get_nested(ps, "np.t"),
                "net_profit_growth": _get_nested(ps, "np.c_y2y"),
                "gross_margin": _get_nested(ps, "gp_m.t"),
                "net_margin": _get_nested(ps, "np_s_r.t"),
                "eps_basic": _get_nested(ps, "beps.t"),
                "total_assets": _get_nested(bs, "ta.t"),
                "total_liabilities": _get_nested(bs, "tl.t"),
                "shareholders_equity": _get_nested(bs, "toe.t"),
                "current_ratio": _get_nested(bs, "c_r.t"),
                "debt_ratio": _get_nested(bs, "tl_ta_r.t"),
                "goodwill": _get_nested(bs, "gw.t"),
                "total_shares": _get_nested(bs, "tsc.t"),
                "operating_cash_flow": _get_nested(cfs, "ncffoa.t"),
                "investing_cash_flow": _get_nested(cfs, "ncffia.t"),
                "financing_cash_flow": _get_nested(cfs, "ncfffa.t"),
                "free_cash_flow": _get_nested(m, "fcf.t"),
                "ocf_to_profit_ratio": _get_nested(m, "ncffoa_np_r.t"),
                "roe": _get_nested(m, "wroe.t"),
                "roa": _get_nested(m, "roa.t"),
                "dividend_payout_ratio": _get_nested(ps, "d_np_r.t"),
                "dividends_paid": _get_nested(ps, "da.t"),
                "npl_ratio": _get_nested(bs, "npl_r.t"),
                "provision_coverage_ratio": _get_nested(m, "pcr.t"),
                "net_interest_margin": _get_nested(m, "nim.t"),
                "core_tier1_car": _get_nested(m, "ct1c_r.t"),
                "raw_data": item,
            })
        return results

    def validate(self, stock_code: str, data: list[dict], ctx: PipelineContext) -> list[dict]:
        return [d for d in data if d.get("report_date") is not None]

    def load(self, stock_code: str, data: list[dict], ctx: PipelineContext) -> int:
        if not data:
            return 0

        updatable_cols = [
            "revenue", "revenue_growth", "net_profit", "net_profit_growth",
            "gross_margin", "net_margin", "eps_basic", "total_assets",
            "total_liabilities", "shareholders_equity", "current_ratio",
            "debt_ratio", "goodwill", "total_shares", "operating_cash_flow",
            "investing_cash_flow", "financing_cash_flow", "free_cash_flow",
            "ocf_to_profit_ratio", "roe", "roa", "dividend_payout_ratio",
            "dividends_paid", "npl_ratio", "provision_coverage_ratio",
            "net_interest_margin", "core_tier1_car", "raw_data",
        ]

        count = 0
        for item in data:
            existing = (
                self.db.query(FinancialStatement)
                .filter(
                    FinancialStatement.stock_code == stock_code,
                    FinancialStatement.report_date == item["report_date"],
                    FinancialStatement.report_type == item["report_type"],
                )
                .first()
            )
            if existing:
                for col in updatable_cols:
                    setattr(existing, col, item.get(col))
            else:
                self.db.add(FinancialStatement(
                    stock_code=stock_code,
                    **{k: v for k, v in item.items() if k in updatable_cols or k in ("report_date", "report_type")},
                ))
            count += 1

        self.db.commit()
        return count

    def verify(self, stock_code: str, ctx: PipelineContext) -> bool:
        latest = (
            self.db.query(FinancialStatement.report_date)
            .filter(FinancialStatement.stock_code == stock_code)
            .order_by(FinancialStatement.report_date.desc())
            .first()
        )
        if not latest:
            return False
        days_old = (utcnow().date() - latest[0].date()).days
        return days_old <= 120
