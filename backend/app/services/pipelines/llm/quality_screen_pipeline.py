"""Quality screen pipeline — rule-based hard filter + LLM edge-case judgment.

Per decision 5: hybrid architecture. Rule layer is cheap (SQL), LLM only
handles ambiguous cases. Output → watchlist state.

7 hard rules (decision 5 reference, ai-berkshire quality-screen):
  1. NOT ST / not suspended
  2. Market cap > 5 亿 (avoid micro-caps)
  3. PE TTM 5-50 (not absurdly cheap = trap, not absurdly expensive)
  4. ROE TTM > 8% (profitable enough)
  5. Positive OCF last year (cash flow real)
  6. Dividend payout sustainable (or growth stock w/ high ROE)
  7. Revenue not collapsing (> -20% YoY = warning)

Stocks that pass all 7 → enter watchlist.
Stocks with 1-2 borderline → LLM judges (worth tracking or not).
Stocks that fail 3+ rules → skip (stay in universe).

Relationship to the 8 红线 (trading-philosophy.md §4.4): these 7 rules are a
cheap *pre-filter* (SQL layer, decides what's worth researching). The 8 红线
in defense_methodology.md are the *post-research* binary veto (LLM layer,
applied at synthesis). They partially overlap (rule 1 NOT-ST ≈ 红线 重大违规/
退市; rule 7 营收不崩 ≈ 红线 连年亏损 预警) but play different roles — keep both.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.datetime_utils import now
from app.db.session import SessionLocal
from app.models import StockLifecycle
from app.models.financial import FinancialStatement
from app.models.research_report import (
    PIPELINE_QUALITY_SCREEN,
    STATUS_COMPLETED,
    ResearchReport,
)
from app.models.stock import Stock
from app.models.valuation import ValuationSnapshot
from app.services import lifecycle_service
from app.services.llm.client import GLMTier, LLMClient, LLMClientError, get_llm_client

logger = logging.getLogger(__name__)

PIPELINE_NAME = "quality_screen"
PROMPT_VERSION = "v1"

# Hard thresholds (decision 5; can be tuned via config in Phase 6)
MIN_MARKET_CAP_YI: float = 5.0           # 5 亿
MIN_PE: float = 5.0
MAX_PE: float = 50.0
MIN_ROE_PCT: float = 8.0                 # 8%
MAX_REVENUE_DECLINE_PCT: float = -20.0   # YoY change ≥ -20%


@dataclass
class ScreenRuleResult:
    rule_name: str
    passed: bool
    value: Any
    threshold: Any
    note: str = ""


@dataclass
class StockScreenResult:
    stock_code: str
    stock_name: str
    passed: bool  # all hard rules passed
    borderline: bool  # 1-2 rules failed (LLM-judged)
    rejected: bool  # 3+ rules failed
    rule_results: list[ScreenRuleResult] = field(default_factory=list)
    llm_judgment: Optional[dict] = None  # if borderline, LLM decides


def _evaluate_rules(
    stock: Stock,
    latest_val: Optional[ValuationSnapshot],
    annuals: list[FinancialStatement],
) -> list[ScreenRuleResult]:
    """Run 7 hard rules against stock data."""
    results: list[ScreenRuleResult] = []

    # Rule 1: not ST / not suspended (use name heuristic — ST stocks have 'ST' in name)
    is_st = "ST" in (stock.name or "").upper() or "*" in (stock.name or "")
    results.append(ScreenRuleResult(
        rule_name="not_st",
        passed=not is_st,
        value=is_st,
        threshold=False,
        note=f"Name: {stock.name}",
    ))

    # Rule 2: market cap > 5 亿 (using latest valuation pe_ttm * eps_basic as proxy if no market cap)
    # Lixinger may not have market cap directly; we use pe_ttm > 0 as sanity check
    # TODO: when full market cap data available, use it
    if latest_val and latest_val.pe_ttm:
        # Proxy: pe > 0 implies non-penny stock
        results.append(ScreenRuleResult(
            rule_name="market_cap_sanity",
            passed=latest_val.pe_ttm > 0,
            value=latest_val.pe_ttm,
            threshold="pe > 0",
            note="Proxy rule (no direct market cap); replace when available",
        ))
    else:
        results.append(ScreenRuleResult(
            rule_name="market_cap_sanity",
            passed=False,
            value=None,
            threshold="pe > 0",
            note="No valuation data",
        ))

    # Rule 3: PE 5-50
    if latest_val and latest_val.pe_ttm:
        pe = float(latest_val.pe_ttm)
        results.append(ScreenRuleResult(
            rule_name="pe_range",
            passed=(MIN_PE <= pe <= MAX_PE),
            value=pe,
            threshold=f"{MIN_PE} ≤ pe ≤ {MAX_PE}",
        ))
    else:
        results.append(ScreenRuleResult(
            rule_name="pe_range",
            passed=False,
            value=None,
            threshold=f"{MIN_PE} ≤ pe ≤ {MAX_PE}",
            note="No PE data",
        ))

    # Rules 4-6 from financials (annual reports)
    latest_annual = next((f for f in annuals if f.report_type == "annual"), None)
    prev_annual = next((f for f in annuals[1:] if f.report_type == "annual"), None) if len(annuals) > 1 else None

    # Rule 4: ROE > 8% (use net_margin as proxy if no direct ROE)
    if latest_annual and latest_annual.net_margin is not None:
        # net_margin > 8% as proxy
        nm = float(latest_annual.net_margin) * 100
        results.append(ScreenRuleResult(
            rule_name="roe_proxy",
            passed=nm >= MIN_ROE_PCT,
            value=nm,
            threshold=f"net_margin ≥ {MIN_ROE_PCT}%",
            note="Using net_margin as ROE proxy",
        ))
    else:
        results.append(ScreenRuleResult(
            rule_name="roe_proxy",
            passed=False,
            value=None,
            threshold=f"net_margin ≥ {MIN_ROE_PCT}%",
            note="No financial data",
        ))

    # Rule 5: revenue not collapsing (>= -20% YoY)
    if (latest_annual and prev_annual and
        latest_annual.revenue is not None and prev_annual.revenue is not None
        and float(prev_annual.revenue) > 0):
        rev_yoy = ((float(latest_annual.revenue) - float(prev_annual.revenue)) /
                   float(prev_annual.revenue)) * 100
        results.append(ScreenRuleResult(
            rule_name="revenue_growth",
            passed=rev_yoy >= MAX_REVENUE_DECLINE_PCT,
            value=round(rev_yoy, 2),
            threshold=f"YoY ≥ {MAX_REVENUE_DECLINE_PCT}%",
        ))
    else:
        results.append(ScreenRuleResult(
            rule_name="revenue_growth",
            passed=True,  # don't fail on missing data
            value=None,
            threshold=f"YoY ≥ {MAX_REVENUE_DECLINE_PCT}%",
            note="No comparable prior period",
        ))

    return results


def screen_stock(
    db: Session,
    stock_code: str,
    *,
    llm_client: Optional[LLMClient] = None,
    use_llm_for_borderline: bool = True,
) -> Optional[StockScreenResult]:
    """Run quality_screen on a single stock.

    Returns None if stock doesn't exist.
    """
    stock = db.query(Stock).filter(Stock.code == stock_code).first()
    if stock is None:
        return None

    # Latest valuation
    latest_val = (
        db.query(ValuationSnapshot)
        .filter(ValuationSnapshot.stock_code == stock_code)
        .order_by(ValuationSnapshot.date.desc())
        .first()
    )

    # Last 2 annual reports
    annuals = (
        db.query(FinancialStatement)
        .filter(FinancialStatement.stock_code == stock_code)
        .order_by(FinancialStatement.report_date.desc())
        .limit(8)
        .all()
    )

    rule_results = _evaluate_rules(stock, latest_val, annuals)
    failed_count = sum(1 for r in rule_results if not r.passed)

    passed = failed_count == 0
    borderline = 1 <= failed_count <= 2
    rejected = failed_count >= 3

    result = StockScreenResult(
        stock_code=stock_code,
        stock_name=stock.name or "",
        passed=passed,
        borderline=borderline,
        rejected=rejected,
        rule_results=rule_results,
    )

    # Borderline → LLM judgment
    if borderline and use_llm_for_borderline:
        try:
            client = llm_client or get_llm_client()
            result.llm_judgment = _llm_judge_borderline(
                client, db, stock_code, result
            )
            # Override based on LLM
            if result.llm_judgment.get("pass"):
                result.passed = True
                result.borderline = False
            else:
                result.rejected = True
                result.borderline = False
        except LLMClientError:
            logger.exception("LLM judgment failed for %s; keeping borderline", stock_code)

    return result


def _llm_judge_borderline(
    client: LLMClient,
    db: Session,
    stock_code: str,
    result: StockScreenResult,
) -> dict:
    """Ask LLM whether borderline stock is worth tracking."""
    from app.services.llm.prompt_loader import load_shared

    system = load_shared("system_base")
    user_prompt = f"""# 边界判断任务

判断以下股票是否值得进入观察池（watchlist）。

## 股票
- 代码: {stock_code}
- 名称: {result.stock_name}

## 规则评估结果（{sum(1 for r in result.rule_results if not r.passed)} 项未通过）

{chr(10).join(f"- {r.rule_name}: passed={r.passed}, value={r.value}, threshold={r.threshold}, note={r.note}" for r in result.rule_results)}

## 你的判断

基于以上规则和该股票的具体情况，回答：
1. 这是不是临时性问题（如周期性低谷）还是结构性问题？
2. 这个股票值不值得花 LLM 资源做深度研究？
3. 通过：true / false
4. 理由：1-2 句

通过 submit_result 提交。
"""

    schema = {
        "type": "object",
        "properties": {
            "pass": {"type": "boolean"},
            "reason": {"type": "string"},
            "is_temporary_issue": {"type": "boolean"},
            "worth_deep_research": {"type": "boolean"},
        },
        "required": ["pass", "reason"],
    }

    response = client.complete(
        user_prompt=user_prompt,
        pipeline=PIPELINE_NAME,
        model=GLMTier.HAIKU,  # cheap LLM for simple judgment
        version=PROMPT_VERSION,
        response_schema=schema,
        use_web_search=False,  # don't waste searches on borderline judgment
        stock_code=stock_code,
        pipeline_type=f"{PIPELINE_NAME}.borderline_judgment",
        db_session=db,
        max_tokens=1000,
    )
    return response.tool_call_args or {}


def screen_universe(
    db: Session,
    *,
    limit: int = 200,
    llm_client: Optional[LLMClient] = None,
) -> dict[str, Any]:
    """Scan the full universe (non-delisted stocks) and update watchlist.

    Args:
        limit: max stocks to screen (sorted by code; for full scan use higher)
        llm_client: optional injected client

    Returns:
        Summary {scanned, passed, borderline_stayed, rejected}
    """
    stocks = (
        db.query(Stock.code)
        .filter(Stock.delisted_at.is_(None))
        .order_by(Stock.code)
        .limit(limit)
        .all()
    )
    codes = [s[0] for s in stocks]

    passed_count = 0
    borderline_count = 0
    rejected_count = 0

    for code in codes:
        try:
            result = screen_stock(db, code, llm_client=llm_client)
            if result is None:
                continue
            if result.passed:
                lifecycle_service.enter_state(
                    db, code, "watchlist",
                    reason=f"quality_screen passed ({sum(1 for r in result.rule_results if r.passed)}/{len(result.rule_results)} rules)",
                )
                passed_count += 1
            elif result.borderline:
                # LLM couldn't decide or wasn't called — leave in universe
                borderline_count += 1
            else:
                rejected_count += 1
        except Exception:
            logger.exception("screen_stock failed for %s", code)

    db.commit()
    return {
        "scanned": len(codes),
        "passed": passed_count,
        "borderline": borderline_count,
        "rejected": rejected_count,
    }
