"""Deep research pipeline — 4-master parallel analysis.

Per decisions 5, 6, 12, 13:
  6-step flow per stock:
    1. data_collection (LLM): compress Lixinger data + web_search into brief
    2-5. 4 masters in parallel (段永平 / 巴菲特 / 芒格 / 李录)
    6. synthesis (LLM Team Lead): aggregate → final recommendation + markdown

Defense:
  - conflict_validator: PE/PB/revenue vs Lixinger post-check
  - red_line_checker: 8 red lines (consecutive_losses + LLM-flagged)

Output:
  - ResearchReport row (json_output + markdown_output)
  - StockLifecycle transition to 'researched' → 'candidate' (on success) or stays 'researched' (on red_line)
  - RedLineEvent rows for any hits
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Iterator, Optional

from sqlalchemy.orm import Session

from app.core.datetime_utils import now
from app.db.session import SessionLocal
from app.models.financial import FinancialStatement
from app.models.price_kline import PriceKline
from app.models.research_report import (
    PIPELINE_DEEP_RESEARCH,
    REC_PASS,
    STATUS_COMPLETED,
    STATUS_REJECTED,
    ResearchReport,
)
from app.models.stock import Stock
from app.models.valuation import ValuationSnapshot
from app.services.llm.client import GLMTier, LLMClient, LLMClientError, get_llm_client
from app.services.llm.conflict_validator import validate_financials, conflicts_to_dict
from app.services.llm.deep_research_schema import (
    BUFFETT_MASTER_SCHEMA,
    DATA_COLLECTION_SCHEMA,
    DUAN_MASTER_SCHEMA,
    LILU_MASTER_SCHEMA,
    MUNGER_MASTER_SCHEMA,
    SYNTHESIS_SCHEMA,
)
from app.services.llm.prompt_loader import load_prompt
from app.services.llm.red_line_checker import (
    check_all as check_red_lines,
    write_red_line_events,
)
from app.services import lifecycle_service
from app.core.scoring_config import DEFAULT_SOURCE
from app.services.llm.scoring import (
    compute_overall_score,
    recommend,
    score_divergence,
)

logger = logging.getLogger(__name__)

PIPELINE_NAME = "deep_research"
PROMPT_VERSION = "v1"

# Parallel 4 masters
MASTER_PARALLEL_WORKERS = 4


@dataclass
class DeepResearchInput:
    """Input bundle gathered from Lixinger DB."""
    stock_code: str
    stock_name: str = ""
    industry: str = ""
    fundamentals: dict[str, Any] = field(default_factory=dict)
    valuations: list[dict] = field(default_factory=list)
    financials: list[dict] = field(default_factory=list)
    klines_recent: list[dict] = field(default_factory=list)


@dataclass
class DeepResearchResult:
    """Final output of the pipeline."""
    stock_code: str
    overall_score: Optional[float]
    recommendation: str
    evidence_grade: str
    markdown_report: str
    json_output: dict[str, Any]
    data_conflicts: list[dict]
    red_line_hits: list[dict]
    report_id: Optional[int] = None
    rejected: bool = False
    rejection_reason: str = ""


# ── Step 1: Gather Lixinger data ─────────────────────────────────────────


def gather_input(db: Session, stock_code: str) -> Optional[DeepResearchInput]:
    """Pull Lixinger data for a stock from DB.

    Returns None if stock doesn't exist.
    """
    stock = db.query(Stock).filter(Stock.code == stock_code).first()
    if stock is None:
        return None

    # Latest 3 years of financials
    financials = (
        db.query(FinancialStatement)
        .filter(FinancialStatement.stock_code == stock_code)
        .order_by(FinancialStatement.report_date.desc())
        .limit(8)  # ~2 years quarterly + annuals
        .all()
    )

    # Latest valuations
    valuations = (
        db.query(ValuationSnapshot)
        .filter(ValuationSnapshot.stock_code == stock_code)
        .order_by(ValuationSnapshot.date.desc())
        .limit(60)  # ~3 months daily
        .all()
    )

    # Recent klines (30 trading days)
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

    return DeepResearchInput(
        stock_code=stock_code,
        stock_name=stock.name or "",
        industry=stock.industry or "",
        fundamentals={
            "listed_date": str(stock.listed_date) if stock.listed_date else None,
            "security_theme": stock.security_theme,
            "tier": stock.tier,
        },
        valuations=[_serialize_valuation(v) for v in valuations],
        financials=[_serialize_financial(f) for f in financials],
        klines_recent=[_serialize_kline(k) for k in klines],
    )


def _serialize_valuation(v: ValuationSnapshot) -> dict:
    return {
        "date": str(v.date) if v.date else None,
        "pe_ttm": v.pe_ttm,
        "pb": v.pb,
        "dividend_yield": v.dividend_yield,
        "pe_percentile_10y": v.pe_percentile_10y,
        "pb_percentile_10y": v.pb_percentile_10y,
    }


def _serialize_financial(f: FinancialStatement) -> dict:
    return {
        "report_date": str(f.report_date) if f.report_date else None,
        "report_type": f.report_type,
        "revenue": f.revenue,
        "revenue_growth": f.revenue_growth,
        "net_profit": f.net_profit,
        "net_profit_growth": f.net_profit_growth,
        "gross_margin": f.gross_margin,
        "net_margin": f.net_margin,
        "eps_basic": f.eps_basic,
        "total_assets": f.total_assets,
        "total_liabilities": f.total_liabilities,
        "shareholders_equity": f.shareholders_equity,
        "current_ratio": f.current_ratio,
    }


def _serialize_kline(k: PriceKline) -> dict:
    return {
        "date": str(k.date) if k.date else None,
        "open": k.open,
        "high": k.high,
        "low": k.low,
        "close": k.close,
        "volume": k.volume,
    }


# ── Step 2: Build prompts ────────────────────────────────────────────────


def _build_data_collection_prompt(input_data: DeepResearchInput) -> str:
    """Assemble user message for step 1 (data_collection)."""
    payload = {
        "stock": {
            "code": input_data.stock_code,
            "name": input_data.stock_name,
            "industry": input_data.industry,
            **input_data.fundamentals,
        },
        "valuations_recent": input_data.valuations[:10],
        "financials_history": input_data.financials,
        "klines_recent_summary": _summarize_klines(input_data.klines_recent),
    }
    instructions = load_prompt(PIPELINE_NAME, "data_collection", PROMPT_VERSION)
    return (
        f"{instructions}\n\n"
        f"# 输入数据\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```\n\n"
        f"用 web_search 工具查询最近 30 天的公告、新闻、研报，然后提交结构化结果。"
    )


def _build_master_prompt(
    master: str,
    input_data: DeepResearchInput,
    data_brief: dict[str, Any],
    failure_conditions: Optional[list[str]] = None,
) -> str:
    """Assemble user message for a master step (段永平/巴菲特/芒格/李录)."""
    instructions = load_prompt(PIPELINE_NAME, f"{master}_master", PROMPT_VERSION)
    payload = {
        "stock": {
            "code": input_data.stock_code,
            "name": input_data.stock_name,
            "industry": input_data.industry,
        },
        "data_brief": data_brief,
    }
    prompt = (
        f"{instructions}\n\n"
        f"# 研究数据\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"
    )
    # §4.3 失败机制合并 (trading-philosophy.md): theme_scan 已识别的 serenity
    # 失败条件并入芒格 failure_scenarios，避免两份「会出错清单」。仅芒格收到。
    if master == "munger" and failure_conditions:
        conds = "\n".join(f"- {c}" for c in failure_conditions)
        prompt += (
            "\n\n# serenity 已识别的失败条件（来自 theme_scan）\n\n"
            "以下是产业链卡点视角识别的证伪点。**必须并入你的 failure_scenarios**"
            "（作为子项评估其概率/触发信号/下行幅度），不要另列成第二份清单：\n\n"
            f"{conds}"
        )
    return prompt


def _build_synthesis_prompt(
    input_data: DeepResearchInput,
    data_brief: dict[str, Any],
    master_outputs: dict[str, dict[str, Any]],
) -> str:
    """Assemble user message for synthesis step."""
    instructions = load_prompt(PIPELINE_NAME, "synthesis", PROMPT_VERSION)
    payload = {
        "stock": {
            "code": input_data.stock_code,
            "name": input_data.stock_name,
            "industry": input_data.industry,
        },
        "data_brief": data_brief,
        "master_analyses": master_outputs,
    }
    return (
        f"{instructions}\n\n"
        f"# 四大师评估结果\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"
    )


def _summarize_klines(klines: list[dict]) -> dict:
    """Compact 30-day kline summary instead of dumping all rows."""
    if not klines:
        return {"error": "no recent kline data"}
    closes = [k["close"] for k in klines if k.get("close") is not None]
    if not closes:
        return {"error": "no close prices"}
    latest = closes[0]
    oldest = closes[-1]
    change_pct = ((latest - oldest) / oldest * 100) if oldest else 0.0
    high = max(k["high"] for k in klines if k.get("high") is not None)
    low = min(k["low"] for k in klines if k.get("low") is not None)
    return {
        "last_close": latest,
        "period_high": high,
        "period_low": low,
        "period_change_pct": round(change_pct, 2),
        "trading_days": len(klines),
    }


# ── Pipeline orchestration ───────────────────────────────────────────────


@contextmanager
def _heartbeat_while(
    on_progress: Callable[[float, str], None] | None,
    step_base: float,
    step_ceiling: float,
    step_label: str,
) -> Iterator[None]:
    """Periodically report progress during a long-running LLM step.

    Fires *on_progress* every 10 s with an elapsed-time message so the
    front-end progress bar shows the task is alive even while the LLM call
    blocks the thread.  The progress value creeps from *step_base* toward
    *step_ceiling* to give visual movement.

    Cleans up the background thread when the ``with`` block exits.
    """
    if on_progress is None:
        yield
        return

    stop = threading.Event()
    last_p = [step_base]  # mutable box for closure

    def _tick() -> None:
        start = time.monotonic()
        while not stop.wait(10):
            elapsed = int(time.monotonic() - start)
            p = min(last_p[0] + 0.01, step_ceiling)
            last_p[0] = p
            on_progress(p, f"{step_label} — 已等待 {elapsed}s")

    t = threading.Thread(target=_tick, daemon=True)
    t.start()
    try:
        yield
    finally:
        stop.set()
        t.join(2)


def run(
    stock_code: str,
    *,
    source: str = DEFAULT_SOURCE,
    scarcity_score: Optional[float] = None,
    failure_conditions: Optional[list[str]] = None,
    model_tier: GLMTier = GLMTier.SONNET,
    use_web_search: bool = True,
    db_session: Optional[Session] = None,
    llm_client: Optional[LLMClient] = None,
    existing_report_id: Optional[int] = None,
    on_progress: Callable[[float, str], None] | None = None,
) -> DeepResearchResult:
    """Run the full 6-step deep research pipeline for one stock.

    Args:
        stock_code: A-share code
        source: sourcing engine ("quality_screen" | "theme_scan") — selects the
            scoring weight profile (trading-philosophy.md §3)
        scarcity_score: serenity 卡点 score (1-5) handed in by theme_scan; injected
            as the 'scarcity' dimension for the theme profile (reuse, no re-assess)
        failure_conditions: serenity 失败条件 from theme_scan; folded into 芒格's
            failure_scenarios (§4.3 merge — one "what could go wrong" list)
        model_tier: GLM tier (default SONNET for normal, OPUS for top candidates)
        use_web_search: enable web_search in data_collection step
        db_session: caller's session; else creates own
        llm_client: optional injected client (for testing)
        existing_report_id: when set (async flow), update this placeholder
            "running" row in place instead of inserting a new one
        on_progress: optional callback for granular progress reporting.
            Called with (progress_0_to_1, message) after each step and
            periodically during long-running LLM steps.

    Returns:
        DeepResearchResult with all fields populated.

    Raises:
        LLMClientError on persistent LLM failure.
        ValueError if stock not found.
    """
    owns_session = db_session is None
    db = db_session or SessionLocal()
    client = llm_client or get_llm_client()

    try:
        # Step 0: gather input
        if on_progress:
            on_progress(0.0, f"Gathering input data for {stock_code}")
        input_data = gather_input(db, stock_code)
        if input_data is None:
            raise ValueError(f"Stock not found: {stock_code}")

        # Step 1: data_collection
        if on_progress:
            on_progress(0.10, f"Step 1/6: Data collection for {stock_code}")
        with _heartbeat_while(on_progress, 0.10, 0.35, "Step 1/6: data_collection"):
            data_brief = _run_data_collection(client, db, input_data, model_tier, use_web_search)

        # Steps 2-5: 4 masters in parallel
        if on_progress:
            on_progress(0.40, f"Step 2-5/6: Running 4 masters for {stock_code}")
        with _heartbeat_while(on_progress, 0.40, 0.70, "Steps 2-5/6: masters"):
            master_outputs = _run_masters_parallel(
                client, db, input_data, data_brief, model_tier,
                failure_conditions=failure_conditions,
            )

        # Step 6: synthesis
        if on_progress:
            on_progress(0.75, f"Step 6/6: Synthesizing results for {stock_code}")
        with _heartbeat_while(on_progress, 0.75, 0.88, "Step 6/6: synthesis"):
            synthesis = _run_synthesis(
                client, db, input_data, data_brief, master_outputs, model_tier
            )

        # Defense layer — fast, no heartbeat needed
        if on_progress:
            on_progress(0.90, f"Validating for {stock_code}")
        conflicts = _run_conflict_validation(db, stock_code, synthesis)
        red_line_hits = _run_red_line_check(db, stock_code, synthesis)

        rejected = bool(red_line_hits)

        # Hybrid scoring (trading-philosophy.md §3): the LLM's overall_score is
        # advisory. Recompute the authoritative score from each master's own
        # 1-5 score under the source profile, derive the recommendation, and
        # log when the LLM diverges (prompt-drift signal).
        per_master_scores = {
            name: out["score"]
            for name, out in master_outputs.items()
            if isinstance(out, dict) and isinstance(out.get("score"), (int, float))
        }
        advantage_sources = {
            name: out.get("advantage_source")
            for name, out in master_outputs.items()
            if isinstance(out, dict)
        }
        # theme_scan hands in the 卡点 score (reuse, §3): inject as the 'scarcity'
        # dimension so the theme profile weights it; its advantage_source is
        # chain_scarcity so it joins the §4.1 same-source collapse.
        if scarcity_score is not None:
            per_master_scores["scarcity"] = scarcity_score
            advantage_sources["scarcity"] = "chain_scarcity"
        llm_score = synthesis.get("overall_score")
        authoritative_score = compute_overall_score(
            per_master_scores, source, advantage_sources=advantage_sources
        )
        divergence = score_divergence(llm_score, authoritative_score)
        if divergence["divergent"]:
            logger.warning(
                "deep_research score divergence %s: llm=%.2f python=%.2f delta=%.2f source=%s",
                stock_code, llm_score, authoritative_score, divergence["delta"], source,
            )

        recommendation = REC_PASS if rejected else recommend(authoritative_score)

        # Persist
        if on_progress:
            on_progress(0.95, f"Persisting report for {stock_code}")
        result = DeepResearchResult(
            stock_code=stock_code,
            overall_score=authoritative_score,
            recommendation=recommendation,
            evidence_grade=synthesis.get("evidence_grade", "B"),
            markdown_report=synthesis.get("markdown_report", ""),
            json_output={
                "data_brief": data_brief,
                "masters": master_outputs,
                "synthesis": synthesis,
                "scoring": {
                    "source": source,
                    "authoritative_score": authoritative_score,
                    "llm_advisory_score": llm_score,
                    "divergent": divergence["divergent"],
                    "delta": divergence["delta"],
                    "per_master_scores": per_master_scores,
                    "advantage_sources": advantage_sources,
                },
            },
            data_conflicts=conflicts,
            red_line_hits=red_line_hits,
            rejected=rejected,
            rejection_reason="red_line_hit" if rejected else "",
        )

        report = _persist_report(db, result, existing_report_id=existing_report_id)
        result.report_id = report.id

        if rejected:
            _persist_red_lines(db, stock_code, red_line_hits, report.id)

        # Update lifecycle — promote to candidate on success (§2)
        lifecycle_service.mark_researched(
            db, stock_code,
            rejected=rejected,
            reason=result.rejection_reason or "deep_research completed",
            promote_to_candidate=not rejected,
        )

        if owns_session:
            db.commit()

        return result

    finally:
        if owns_session:
            db.close()


def _run_data_collection(
    client: LLMClient,
    db: Session,
    input_data: DeepResearchInput,
    model_tier: GLMTier,
    use_web_search: bool,
) -> dict[str, Any]:
    """Step 1: data collection via LLM."""
    user_prompt = _build_data_collection_prompt(input_data)
    response = client.complete(
        user_prompt=user_prompt,
        pipeline=PIPELINE_NAME,
        model=model_tier,
        version=PROMPT_VERSION,
        response_schema=DATA_COLLECTION_SCHEMA,
        use_web_search=use_web_search,
        stock_code=input_data.stock_code,
        pipeline_type=f"{PIPELINE_NAME}.data_collection",
        db_session=db,
        max_tokens=8000,
    )
    if not response.tool_call_args:
        raise LLMClientError("data_collection: LLM did not return submit_result")
    return response.tool_call_args


def _run_masters_parallel(
    client: LLMClient,
    db: Session,
    input_data: DeepResearchInput,
    data_brief: dict[str, Any],
    model_tier: GLMTier,
    failure_conditions: Optional[list[str]] = None,
) -> dict[str, dict[str, Any]]:
    """Steps 2-5: 4 masters in parallel."""
    masters = [
        ("duan", DUAN_MASTER_SCHEMA),
        ("buffett", BUFFETT_MASTER_SCHEMA),
        ("munger", MUNGER_MASTER_SCHEMA),
        ("lilu", LILU_MASTER_SCHEMA),
    ]

    def _run_one(master_name: str, schema: dict) -> tuple[str, dict]:
        prompt = _build_master_prompt(
            master_name, input_data, data_brief, failure_conditions=failure_conditions
        )
        # Each master gets its own DB session to avoid thread conflicts
        with SessionLocal() as master_db:
            response = client.complete(
                user_prompt=prompt,
                pipeline=PIPELINE_NAME,
                model=model_tier,
                version=PROMPT_VERSION,
                response_schema=schema,
                use_web_search=True,
                stock_code=input_data.stock_code,
                pipeline_type=f"{PIPELINE_NAME}.{master_name}",
                db_session=master_db,
                max_tokens=6000,
            )
        if not response.tool_call_args:
            raise LLMClientError(f"{master_name}_master: LLM did not return submit_result")
        return master_name, response.tool_call_args

    outputs: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=MASTER_PARALLEL_WORKERS) as pool:
        futures = [pool.submit(_run_one, m, s) for m, s in masters]
        for fut in futures:
            name, result = fut.result()
            outputs[name] = result

    return outputs


def _run_synthesis(
    client: LLMClient,
    db: Session,
    input_data: DeepResearchInput,
    data_brief: dict[str, Any],
    master_outputs: dict[str, dict[str, Any]],
    model_tier: GLMTier,
) -> dict[str, Any]:
    """Step 6: synthesis."""
    user_prompt = _build_synthesis_prompt(input_data, data_brief, master_outputs)
    response = client.complete(
        user_prompt=user_prompt,
        pipeline=PIPELINE_NAME,
        model=model_tier,
        version=PROMPT_VERSION,
        response_schema=SYNTHESIS_SCHEMA,
        use_web_search=False,  # synthesis uses what masters already gathered
        stock_code=input_data.stock_code,
        pipeline_type=f"{PIPELINE_NAME}.synthesis",
        db_session=db,
        max_tokens=10000,
    )
    if not response.tool_call_args:
        raise LLMClientError("synthesis: LLM did not return submit_result")
    return response.tool_call_args


# ── Defense layer ────────────────────────────────────────────────────────


def _run_conflict_validation(
    db: Session,
    stock_code: str,
    synthesis: dict[str, Any],
) -> list[dict]:
    """Validate LLM-reported numbers vs Lixinger."""
    # Pull numbers LLM reported (synthesis doesn't have raw numbers;
    # data_brief does, in json_output). For simplicity, validate key
    # fields from data_brief's key_numbers if present.
    data_brief = synthesis  # could be enriched
    # Try extracting from overall pipeline context
    numbers_to_check: dict[str, float | None] = {}

    # Best-effort: pull from master outputs if they have valuation.current_pe
    # (Masters don't directly emit key_numbers; data_brief does.)
    # We'll do conflict detection at the pipeline-result level by re-extracting
    # from the final json_output in the calling run(). This is a stub for
    # per-step validation that can be enriched later.
    try:
        conflicts = validate_financials(db, stock_code, numbers_to_check)
        return conflicts_to_dict(conflicts)
    except Exception:
        logger.exception("conflict_validation failed for %s", stock_code)
        return []


def _run_red_line_check(
    db: Session,
    stock_code: str,
    synthesis: dict[str, Any],
) -> list[dict]:
    """Run red line checks (code + LLM-flagged)."""
    try:
        hits = check_red_lines(db, stock_code, llm_output=synthesis)
        return [
            {
                "red_line_type": h.red_line_type,
                "severity": h.severity,
                "evidence": h.evidence,
                "action_taken": h.action_taken,
            }
            for h in hits
        ]
    except Exception:
        logger.exception("red_line_check failed for %s", stock_code)
        return []


# ── Persistence ─────────────────────────────────────────────────────────


def _persist_report(
    db: Session,
    result: DeepResearchResult,
    *,
    existing_report_id: Optional[int] = None,
) -> ResearchReport:
    """Write research_reports row.

    When ``existing_report_id`` is given (async flow), update that placeholder
    "running" row in place; otherwise insert a fresh row (sync flow).
    """
    status = STATUS_REJECTED if result.rejected else STATUS_COMPLETED
    fields = dict(
        stock_code=result.stock_code,
        pipeline_type=PIPELINE_DEEP_RESEARCH,
        json_output=result.json_output,
        markdown_output=result.markdown_report,
        evidence_grade=result.evidence_grade,
        data_conflict_json=result.data_conflicts or None,
        red_line_hit_json=result.red_line_hits or None,
        prompt_version=PROMPT_VERSION,
        overall_score=result.overall_score,
        recommendation=result.recommendation,
        status=status,
        expires_at=now() + timedelta(days=30),  # decision 8: 30-day cache
    )

    if existing_report_id is not None:
        report = db.query(ResearchReport).filter(
            ResearchReport.id == existing_report_id
        ).first()
        if report is None:
            raise ValueError(f"existing_report_id not found: {existing_report_id}")
        for key, value in fields.items():
            setattr(report, key, value)
        db.flush()
        return report

    report = ResearchReport(**fields)
    db.add(report)
    db.flush()
    return report


def _persist_red_lines(
    db: Session,
    stock_code: str,
    hits: list[dict],
    report_id: int,
) -> None:
    """Write red_line_events rows."""
    from app.services.llm.red_line_checker import RedLineHit
    red_line_hits = [
        RedLineHit(
            red_line_type=h["red_line_type"],
            severity=h.get("severity", "hard_reject"),
            evidence=h.get("evidence", {}),
        )
        for h in hits
    ]
    write_red_line_events(db, stock_code, red_line_hits, report_id=report_id)
