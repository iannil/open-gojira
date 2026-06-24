"""Earnings review pipeline — deep read of latest quarterly/annual report.

Per decision 5: triggered by EarningsPublished event. Outputs thesis_impact
(strengthens / weakens / neutral / invalidates).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import ResearchReport
from app.models.financial import FinancialStatement
from app.models.research_report import (
    PIPELINE_EARNINGS_REVIEW,
    STATUS_COMPLETED,
    STATUS_REJECTED,
    ResearchReport,
)
from app.services.llm.client import GLMTier, LLMClient, LLMClientError, get_llm_client
from app.services.llm.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

PIPELINE_NAME = "earnings_review"
PROMPT_VERSION = "v1"

IMPACT_STRENGTHENS = "strengthens"
IMPACT_WEAKENS = "weakens"
IMPACT_NEUTRAL = "neutral"
IMPACT_INVALIDATES = "invalidates"

ACTION_THESIS_REVIEW = "thesis_review"
ACTION_DEEP_RESEARCH = "deep_research"
ACTION_HOLD = "hold"


EARNINGS_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "stock_code": {"type": "string"},
        "report_date": {"type": "string"},
        "thesis_impact": {"type": "string", "enum": [
            IMPACT_STRENGTHENS, IMPACT_WEAKENS, IMPACT_NEUTRAL, IMPACT_INVALIDATES
        ]},
        "key_findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "finding": {"type": "string"},
                    "metric": {"type": "string"},
                    "value": {"type": "string"},
                    "interpretation": {"type": "string"},
                },
                "required": ["finding"],
            },
        },
        "accounting_concerns": {
            "type": "array",
            "items": {"type": "string"},
            "description": "会计政策 / 财务质量疑虑列表",
        },
        "guidance_assessment": {
            "type": "object",
            "properties": {
                "credibility": {"type": "string", "enum": ["high", "medium", "low"]},
                "tone": {"type": "string", "enum": ["conservative", "neutral", "optimistic"]},
                "notes": {"type": "string"},
            },
        },
        "action_recommendation": {"type": "string", "enum": [
            ACTION_THESIS_REVIEW, ACTION_DEEP_RESEARCH, ACTION_HOLD
        ]},
        "markdown_report": {"type": "string"},
    },
    "required": ["stock_code", "thesis_impact", "key_findings", "markdown_report"],
}


@dataclass
class EarningsReviewResult:
    stock_code: str
    report_date: str
    thesis_impact: str
    key_findings: list[dict]
    accounting_concerns: list[str]
    action_recommendation: str
    markdown_report: str
    report_id: Optional[int] = None


def run(
    stock_code: str,
    *,
    report_date: Optional[str] = None,  # specific report; if None use latest
    db_session: Optional[Session] = None,
    llm_client: Optional[LLMClient] = None,
    model_tier: GLMTier = GLMTier.SONNET,
) -> EarningsReviewResult:
    """Run earnings_review for a stock's latest or specific report."""
    owns_session = db_session is None
    db = db_session or SessionLocal()
    client = llm_client or get_llm_client()

    try:
        # Latest or specific report
        q = db.query(FinancialStatement).filter(
            FinancialStatement.stock_code == stock_code
        )
        if report_date:
            q = q.filter(FinancialStatement.report_date == report_date)
        latest_fin = q.order_by(FinancialStatement.report_date.desc()).first()

        if latest_fin is None:
            raise ValueError(f"No financial statements for {stock_code}")

        # Previous period for comparison
        prev_fin = (
            db.query(FinancialStatement)
            .filter(
                FinancialStatement.stock_code == stock_code,
                FinancialStatement.report_date < latest_fin.report_date,
                FinancialStatement.report_type == latest_fin.report_type,
            )
            .order_by(FinancialStatement.report_date.desc())
            .first()
        )

        # Original thesis (for impact comparison)
        thesis_report = (
            db.query(ResearchReport)
            .filter(
                ResearchReport.stock_code == stock_code,
                ResearchReport.pipeline_type == "deep_research",
            )
            .order_by(ResearchReport.created_at.desc())
            .first()
        )

        user_prompt = _build_prompt(stock_code, latest_fin, prev_fin, thesis_report)

        response = client.complete(
            user_prompt=user_prompt,
            pipeline=PIPELINE_NAME,
            model=model_tier,
            version=PROMPT_VERSION,
            response_schema=EARNINGS_REVIEW_SCHEMA,
            use_web_search=True,
            stock_code=stock_code,
            pipeline_type=PIPELINE_NAME,
            db_session=db,
            max_tokens=6000,
        )

        if not response.tool_call_args:
            raise LLMClientError("earnings_review: LLM did not return submit_result")

        args = response.tool_call_args
        result = EarningsReviewResult(
            stock_code=stock_code,
            report_date=str(latest_fin.report_date),
            thesis_impact=args.get("thesis_impact", IMPACT_NEUTRAL),
            key_findings=args.get("key_findings", []),
            accounting_concerns=args.get("accounting_concerns", []),
            action_recommendation=args.get("action_recommendation", ACTION_HOLD),
            markdown_report=args.get("markdown_report", ""),
        )

        # Persist
        report = ResearchReport(
            stock_code=stock_code,
            pipeline_type=PIPELINE_EARNINGS_REVIEW,
            json_output=args,
            markdown_output=result.markdown_report,
            evidence_grade=None,
            prompt_version=PROMPT_VERSION,
            recommendation=("SELL" if result.thesis_impact == IMPACT_INVALIDATES else None),
            status=STATUS_REJECTED if result.thesis_impact == IMPACT_INVALIDATES else STATUS_COMPLETED,
            expires_at=None,
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
    latest_fin: FinancialStatement,
    prev_fin: Optional[FinancialStatement],
    thesis_report: Optional[ResearchReport],
) -> str:
    import json as _json

    system = load_prompt(PIPELINE_NAME, "system", PROMPT_VERSION)

    def _fin_to_dict(f: FinancialStatement) -> dict:
        return {
            "report_date": str(f.report_date),
            "report_type": f.report_type,
            "revenue": float(f.revenue) if f.revenue else None,
            "revenue_growth": float(f.revenue_growth) if f.revenue_growth else None,
            "net_profit": float(f.net_profit) if f.net_profit else None,
            "net_profit_growth": float(f.net_profit_growth) if f.net_profit_growth else None,
            "gross_margin": float(f.gross_margin) if f.gross_margin else None,
            "net_margin": float(f.net_margin) if f.net_margin else None,
            "eps_basic": float(f.eps_basic) if f.eps_basic else None,
            "total_assets": float(f.total_assets) if f.total_assets else None,
            "total_liabilities": float(f.total_liabilities) if f.total_liabilities else None,
            "shareholders_equity": float(f.shareholders_equity) if f.shareholders_equity else None,
            "current_ratio": float(f.current_ratio) if f.current_ratio else None,
        }

    payload = {
        "stock_code": stock_code,
        "latest_report": _fin_to_dict(latest_fin),
        "previous_report": _fin_to_dict(prev_fin) if prev_fin else None,
        "original_thesis_score": thesis_report.overall_score if thesis_report else None,
        "original_thesis_recommendation": thesis_report.recommendation if thesis_report else None,
    }

    return (
        f"{system}\n\n"
        f"# 财报数据\n\n```json\n{_json.dumps(payload, ensure_ascii=False, indent=2, default=str)}\n```\n\n"
        f"用 web_search 查电话会要点 / 卖方研报反应，然后提交结构化精读结果。"
    )
