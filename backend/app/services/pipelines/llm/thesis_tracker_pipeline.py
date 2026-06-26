"""Thesis tracker pipeline — periodic re-validation of holdings' theses.

Per decision 5: weekly cron on holdings. Outputs VALID / WARNING / INVALIDATED.
INVALIDATED → triggers SELL Draft (Phase 5 will hook in).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import ResearchReport
from app.models.financial import FinancialStatement
from app.services import holding_service
from app.models.price_kline import PriceKline
from app.models.research_report import (
    PIPELINE_THESIS_TRACKER,
    STATUS_COMPLETED,
    STATUS_REJECTED,
    ResearchReport,
)
from app.services.llm.client import GLMTier, LLMClient, LLMClientError, get_llm_client
from app.services.llm.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

PIPELINE_NAME = "thesis_tracker"
PROMPT_VERSION = "v1"

VALID = "VALID"
WARNING = "WARNING"
INVALIDATED = "INVALIDATED"


THESIS_SCHEMA = {
    "type": "object",
    "properties": {
        "stock_code": {"type": "string"},
        "status": {"type": "string", "enum": [VALID, WARNING, INVALIDATED]},
        "key_changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "change": {"type": "string"},
                    "impact": {"type": "string", "enum": ["positive", "neutral", "negative"]},
                    "evidence": {"type": "string"},
                },
            },
        },
        "invalidated_triggers": {
            "type": "array",
            "items": {"type": "string"},
            "description": "If status=INVALIDATED, list what triggered it",
        },
        "sell_recommendation": {"type": "boolean"},
        "markdown_summary": {"type": "string"},
        "key_risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["stock_code", "status", "key_changes", "sell_recommendation", "markdown_summary"],
}


@dataclass
class ThesisResult:
    stock_code: str
    status: str
    sell_recommended: bool
    key_changes: list[dict]
    invalidated_triggers: list[str]
    markdown_summary: str
    report_id: Optional[int] = None


def run(
    stock_code: str,
    *,
    db_session: Optional[Session] = None,
    llm_client: Optional[LLMClient] = None,
    model_tier: GLMTier = GLMTier.SONNET,
) -> ThesisResult:
    """Run thesis tracking for one holding."""
    owns_session = db_session is None
    db = db_session or SessionLocal()
    client = llm_client or get_llm_client()

    try:
        # Gather context — position derived from the trade ledger (Q2-A)
        from app.services import position_service

        position = position_service.position_for(
            db, stock_code, price_lookup=lambda _c: None
        )
        if position is None or position.quantity <= 0:
            raise ValueError(f"No active holding for {stock_code}")
        buy_dates = holding_service._buy_dates(db, [stock_code])
        buy_date = buy_dates.get(stock_code)

        # Latest deep_research report (the thesis baseline)
        thesis_report = (
            db.query(ResearchReport)
            .filter(
                ResearchReport.stock_code == stock_code,
                ResearchReport.pipeline_type == "deep_research",
            )
            .order_by(ResearchReport.created_at.desc())
            .first()
        )

        # Latest financials
        financials = (
            db.query(FinancialStatement)
            .filter(FinancialStatement.stock_code == stock_code)
            .order_by(FinancialStatement.report_date.desc())
            .limit(4)
            .all()
        )

        # Recent klines (30 days)
        cutoff = date.today() - timedelta(days=45)
        klines = (
            db.query(PriceKline)
            .filter(
                PriceKline.stock_code == stock_code,
                PriceKline.date >= cutoff,
            )
            .order_by(PriceKline.date.desc())
            .limit(30)
            .all()
        )

        # Build prompt
        user_prompt = _build_prompt(stock_code, position, buy_date, thesis_report, financials, klines)

        # Call LLM
        response = client.complete(
            user_prompt=user_prompt,
            pipeline=PIPELINE_NAME,
            model=model_tier,
            version=PROMPT_VERSION,
            response_schema=THESIS_SCHEMA,
            use_web_search=True,
            stock_code=stock_code,
            pipeline_type=PIPELINE_NAME,
            db_session=db,
            max_tokens=4000,
        )

        if not response.tool_call_args:
            raise LLMClientError("thesis_tracker: LLM did not return submit_result")

        args = response.tool_call_args
        result = ThesisResult(
            stock_code=stock_code,
            status=args.get("status", WARNING),
            sell_recommended=bool(args.get("sell_recommendation", False)),
            key_changes=args.get("key_changes", []),
            invalidated_triggers=args.get("invalidated_triggers", []),
            markdown_summary=args.get("markdown_summary", ""),
        )

        # Persist report
        report = ResearchReport(
            stock_code=stock_code,
            pipeline_type=PIPELINE_THESIS_TRACKER,
            json_output=args,
            markdown_output=result.markdown_summary,
            evidence_grade=None,
            prompt_version=PROMPT_VERSION,
            recommendation=("SELL" if result.sell_recommended else None),
            status=STATUS_REJECTED if result.status == INVALIDATED else STATUS_COMPLETED,
            expires_at=None,  # thesis reports don't expire
        )
        db.add(report)
        db.flush()
        result.report_id = report.id

        if owns_session:
            db.commit()

        return result

    finally:
        if owns_session:
            db.close()


def _build_prompt(
    stock_code: str,
    position: "position_service.Position",
    buy_date,
    thesis_report: Optional[ResearchReport],
    financials: list[FinancialStatement],
    klines: list[PriceKline],
) -> str:
    """Assemble user prompt for thesis check."""
    import json as _json

    from app.services import position_service  # noqa: F401 — type ref only

    system = load_prompt(PIPELINE_NAME, "system", PROMPT_VERSION)

    payload = {
        "stock_code": stock_code,
        "position": {
            "shares": position.quantity,
            "avg_cost": float(position.avg_cost) if position.avg_cost else None,
            "buy_date": str(buy_date) if buy_date else None,
        },
        "original_thesis": (
            {
                "markdown": thesis_report.markdown_output[:3000] if thesis_report else None,
                "overall_score": thesis_report.overall_score if thesis_report else None,
                "recommendation": thesis_report.recommendation if thesis_report else None,
                "created_at": str(thesis_report.created_at) if thesis_report else None,
            }
            if thesis_report
            else None
        ),
        "latest_financials": [
            {
                "report_date": str(f.report_date),
                "report_type": f.report_type,
                "revenue": float(f.revenue) if f.revenue else None,
                "revenue_growth": float(f.revenue_growth) if f.revenue_growth else None,
                "net_profit": float(f.net_profit) if f.net_profit else None,
                "net_profit_growth": float(f.net_profit_growth) if f.net_profit_growth else None,
                "gross_margin": float(f.gross_margin) if f.gross_margin else None,
            }
            for f in financials
        ],
        "recent_klines": {
            "last_close": float(klines[0].close) if klines and klines[0].close else None,
            "period_change_pct": _period_change(klines),
            "trading_days": len(klines),
        },
    }

    return (
        f"{system}\n\n"
        f"# 持仓与论文数据\n\n```json\n{_json.dumps(payload, ensure_ascii=False, indent=2, default=str)}\n```\n\n"
        f"用 web_search 查最近 30 天的公告/新闻，然后提交结构化结果。"
    )


def _period_change(klines: list[PriceKline]) -> Optional[float]:
    if not klines or len(klines) < 2:
        return None
    latest = klines[0].close
    oldest = klines[-1].close
    if not latest or not oldest or float(oldest) == 0:
        return None
    return round((float(latest) - float(oldest)) / float(oldest) * 100, 2)
