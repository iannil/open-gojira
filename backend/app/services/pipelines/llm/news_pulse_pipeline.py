"""News pulse pipeline — price-move attribution (4-dimension parallel recon).

Per decision 5: triggered by PriceChange ±5% events. 10-15 min attribution.
Output: nature (value_event / liquidity / emotional / mixed / unknown).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import PriceKline, ResearchReport
from app.models.research_report import (
    PIPELINE_NEWS_PULSE,
    STATUS_COMPLETED,
    ResearchReport,
)
from app.services.llm.client import GLMTier, LLMClient, LLMClientError, get_llm_client
from app.services.llm.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

PIPELINE_NAME = "news_pulse"
PROMPT_VERSION = "v1"

# Nature constants
NATURE_VALUE_EVENT = "value_event"
NATURE_LIQUIDITY = "liquidity"
NATURE_EMOTIONAL = "emotional"
NATURE_MIXED = "mixed"
NATURE_UNKNOWN = "unknown"

# Trigger threshold
PRICE_CHANGE_THRESHOLD_PCT: float = 5.0

# Action recommendations
ACTION_DEEP_RESEARCH = "deep_research"
ACTION_THESIS_REVIEW = "thesis_review"
ACTION_OBSERVE = "observe"
ACTION_HOLD = "hold"


NEWS_PULSE_SCHEMA = {
    "type": "object",
    "properties": {
        "stock_code": {"type": "string"},
        "window_change_pct": {"type": "number"},
        "attribution": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "candidate": {"type": "string", "description": "候选解释"},
                    "estimated_contribution_pct": {"type": "number"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "evidence_url": {"type": "string"},
                },
                "required": ["candidate", "confidence"],
            },
        },
        "nature": {"type": "string", "enum": [
            NATURE_VALUE_EVENT, NATURE_LIQUIDITY, NATURE_EMOTIONAL, NATURE_MIXED, NATURE_UNKNOWN
        ]},
        "action_recommendation": {"type": "string", "enum": [
            ACTION_DEEP_RESEARCH, ACTION_THESIS_REVIEW, ACTION_OBSERVE, ACTION_HOLD
        ]},
        "markdown_report": {"type": "string"},
        "key_finding": {"type": "string", "description": "1 sentence summary"},
    },
    "required": ["stock_code", "attribution", "nature", "action_recommendation", "markdown_report"],
}


@dataclass
class NewsPulseResult:
    stock_code: str
    window_change_pct: float
    nature: str
    action: str
    attribution: list[dict]
    markdown_report: str
    report_id: Optional[int] = None


def run(
    stock_code: str,
    *,
    window_days: int = 7,
    change_pct: Optional[float] = None,  # auto-compute if None
    db_session: Optional[Session] = None,
    llm_client: Optional[LLMClient] = None,
    model_tier: GLMTier = GLMTier.HAIKU,  # news_pulse uses cheap tier (per decision 9)
) -> NewsPulseResult:
    """Run news_pulse for a stock.

    Args:
        stock_code: target
        window_days: lookback for price move
        change_pct: precomputed change; if None, computed from klines
    """
    owns_session = db_session is None
    db = db_session or SessionLocal()
    client = llm_client or get_llm_client()

    try:
        # Compute change if not provided
        if change_pct is None:
            change_pct = _compute_recent_change(db, stock_code, window_days)
            if change_pct is None:
                raise ValueError(f"No kline data for {stock_code}")

        # Gather klines
        cutoff = date.today() - timedelta(days=window_days + 5)
        klines = (
            db.query(PriceKline)
            .filter(
                PriceKline.stock_code == stock_code,
                PriceKline.date >= cutoff,
            )
            .order_by(PriceKline.date.desc())
            .limit(window_days + 2)
            .all()
        )

        user_prompt = _build_prompt(stock_code, change_pct, window_days, klines)

        response = client.complete(
            user_prompt=user_prompt,
            pipeline=PIPELINE_NAME,
            model=model_tier,
            version=PROMPT_VERSION,
            response_schema=NEWS_PULSE_SCHEMA,
            use_web_search=True,
            stock_code=stock_code,
            pipeline_type=PIPELINE_NAME,
            db_session=db,
            max_tokens=4000,
        )

        if not response.tool_call_args:
            raise LLMClientError("news_pulse: LLM did not return submit_result")

        args = response.tool_call_args
        result = NewsPulseResult(
            stock_code=stock_code,
            window_change_pct=float(args.get("window_change_pct", change_pct)),
            nature=args.get("nature", NATURE_UNKNOWN),
            action=args.get("action_recommendation", ACTION_HOLD),
            attribution=args.get("attribution", []),
            markdown_report=args.get("markdown_report", ""),
        )

        # Persist
        report = ResearchReport(
            stock_code=stock_code,
            pipeline_type=PIPELINE_NEWS_PULSE,
            json_output=args,
            markdown_output=result.markdown_report,
            evidence_grade=None,
            prompt_version=PROMPT_VERSION,
            recommendation=None,
            status=STATUS_COMPLETED,
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


def _compute_recent_change(db: Session, stock_code: str, window_days: int) -> Optional[float]:
    """Compute % change over last N trading days."""
    cutoff = date.today() - timedelta(days=window_days + 5)
    klines = (
        db.query(PriceKline)
        .filter(
            PriceKline.stock_code == stock_code,
            PriceKline.date >= cutoff,
        )
        .order_by(PriceKline.date.desc())
        .limit(window_days + 1)
        .all()
    )
    if len(klines) < 2:
        return None
    latest = klines[0].close
    oldest = klines[-1].close
    if not latest or not oldest or float(oldest) == 0:
        return None
    return round((float(latest) - float(oldest)) / float(oldest) * 100, 2)


def _build_prompt(stock_code: str, change_pct: float, window_days: int, klines: list) -> str:
    import json as _json

    system = load_prompt(PIPELINE_NAME, "system", PROMPT_VERSION)

    payload = {
        "stock_code": stock_code,
        "window_days": window_days,
        "window_change_pct": change_pct,
        "recent_klines": [
            {"date": str(k.date), "close": float(k.close) if k.close else None,
             "volume": float(k.volume) if k.volume else None}
            for k in klines[:10]
        ],
    }

    direction = "上涨" if change_pct > 0 else "下跌"

    return (
        f"{system}\n\n"
        f"# 任务背景\n\n"
        f"**{stock_code}** 在最近 {window_days} 天{direction} **{abs(change_pct):.2f}%**。\n\n"
        f"# 行情数据\n\n```json\n{_json.dumps(payload, ensure_ascii=False, indent=2)}\n```\n\n"
        f"用 web_search 并行调查 4 维度（公司事件 / 监管政策 / 行业对手 / 市场情绪），"
        f"然后提交结构化归因结果。"
    )
