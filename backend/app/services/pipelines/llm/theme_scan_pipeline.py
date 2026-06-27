"""theme_scan_pipeline — serenity bottleneck-hunter engine (trading-philosophy.md §2).

5-step LLM workflow over an investment theme:
  1. system_change → 2. value_chain → 3. scarce_layer (rank) →
  4. company_universe (propose A-share codes) → [validate vs Stock master] →
  5. candidate_rank (scarcity_score 1-5 + thesis + failure_conditions)

Output: a ThemeScanReport (theme-level) with ranked candidates. Each candidate's
scarcity_score is later handed into deep_research as the 卡点 dimension (§3,
reuse) via deep_research_pipeline.run(code, source="theme_scan", scarcity_score=).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.stock import Stock
from app.models.theme_scan_report import (
    STATUS_COMPLETED,
    STATUS_EMPTY,
    STATUS_FAILED,
    ThemeScanReport,
)
from app.services.llm.client import GLMTier, LLMClient, LLMClientError, get_llm_client
from app.services.llm.prompt_loader import load_prompt
from app.services.llm.theme_scan_schema import (
    CANDIDATE_RANK_SCHEMA,
    COMPANY_UNIVERSE_SCHEMA,
    SCARCE_LAYER_SCHEMA,
    SYSTEM_CHANGE_SCHEMA,
    VALUE_CHAIN_SCHEMA,
)

logger = logging.getLogger(__name__)

PIPELINE_NAME = "theme_scan"
PROMPT_VERSION = "v1"
STEP_MAX_TOKENS = 8000


@dataclass
class ThemeScanResult:
    theme: str
    system_change: Optional[str]
    ranked_layers: list[dict[str, Any]]
    ranked_candidates: list[dict[str, Any]]
    evidence_grade: str
    markdown_report: str
    dropped_codes: list[str] = field(default_factory=list)
    status: str = STATUS_COMPLETED
    report_id: Optional[int] = None


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


def _step(
    client: LLMClient,
    *,
    name: str,
    schema: dict,
    payload: dict,
    model_tier: GLMTier,
    use_web_search: bool,
    db: Session,
) -> dict[str, Any]:
    """Run one LLM step; return its submit_result args."""
    instructions = load_prompt(PIPELINE_NAME, name, PROMPT_VERSION)
    user_prompt = (
        f"{instructions}\n\n# 输入\n\n"
        f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"
    )
    response = client.complete(
        user_prompt=user_prompt,
        pipeline=PIPELINE_NAME,
        model=model_tier,
        version=PROMPT_VERSION,
        response_schema=schema,
        use_web_search=use_web_search,
        pipeline_type=f"{PIPELINE_NAME}.{name}",
        db_session=db,
        max_tokens=STEP_MAX_TOKENS,
    )
    if not response.tool_call_args:
        raise LLMClientError(f"theme_scan.{name}: LLM did not return submit_result")
    return response.tool_call_args


def _validate_codes(
    db: Session, candidates: list[dict]
) -> tuple[list[dict], list[str]]:
    """Keep only candidates whose code exists in the A-share Stock master;
    backfill the canonical name. Unknown/fabricated codes are dropped."""
    codes = [c["code"] for c in candidates if c.get("code")]
    existing = {
        s.code: s.name
        for s in db.query(Stock).filter(Stock.code.in_(codes)).all()
    }
    valid: list[dict] = []
    dropped: list[str] = []
    for c in candidates:
        code = c.get("code")
        if code in existing:
            valid.append({**c, "name": existing[code] or c.get("name")})
        else:
            dropped.append(code)
    if dropped:
        logger.warning(
            "theme_scan dropped %d unknown A-share codes: %s", len(dropped), dropped
        )
    return valid, dropped


def _persist(
    db: Session, result: ThemeScanResult, raw: dict,
    existing_report: Optional[ThemeScanReport] = None,
) -> ThemeScanReport:
    """Persist result to a new or existing ThemeScanReport row.

    If *existing_report* is provided, update its fields in-place instead of
    creating a new row.
    """
    data = dict(
        theme=result.theme,
        system_change=result.system_change,
        ranked_layers_json=result.ranked_layers,
        ranked_candidates_json=result.ranked_candidates,
        json_output=raw,
        markdown_output=result.markdown_report,
        evidence_grade=result.evidence_grade,
        prompt_version=PROMPT_VERSION,
        status=result.status,
    )
    if existing_report is not None:
        for key, value in data.items():
            setattr(existing_report, key, value)
        db.flush()
        return existing_report
    report = ThemeScanReport(**data)
    db.add(report)
    db.flush()
    return report


def run(
    theme: str,
    *,
    model_tier: GLMTier = GLMTier.SONNET,
    use_web_search: bool = True,
    db_session: Optional[Session] = None,
    llm_client: Optional[LLMClient] = None,
    existing_report_id: Optional[int] = None,
    on_progress: Callable[[float, str], None] | None = None,
) -> ThemeScanResult:
    """Run the full 5-step theme_scan workflow for one theme.

    Args:
        theme: investment theme, e.g. "CPO 光模块"
        model_tier: GLM tier
        use_web_search: enable web_search in LLM steps
        db_session: caller's session; else creates own
        llm_client: optional injected client (for testing)
        existing_report_id: if set, update this existing ThemeScanReport row
            (created as a placeholder) instead of creating a new one.
        on_progress: optional callback for granular progress reporting.
            Called with (progress_0_to_1, message) after each pipeline step.

    Returns:
        ThemeScanResult with ranked candidates (status="empty" if no valid
        A-share candidate survived code validation).
    """
    owns_session = db_session is None
    db = db_session or SessionLocal()
    client = llm_client or get_llm_client()

    existing_report: Optional[ThemeScanReport] = None
    if existing_report_id is not None:
        existing_report = db.query(ThemeScanReport).filter(
            ThemeScanReport.id == existing_report_id
        ).first()
        if existing_report is None:
            logger.warning(
                "existing_report_id=%s not found, will create new report",
                existing_report_id,
            )

    try:
        if on_progress:
            on_progress(0.10, "Step 1/5: Analyzing system change")
        with _heartbeat_while(on_progress, 0.10, 0.28, "Step 1/5: system_change"):
            sc = _step(client, name="system_change", schema=SYSTEM_CHANGE_SCHEMA,
                       payload={"theme": theme},
                       model_tier=model_tier, use_web_search=use_web_search, db=db)

        if on_progress:
            on_progress(0.30, "Step 2/5: Mapping value chain")
        with _heartbeat_while(on_progress, 0.30, 0.48, "Step 2/5: value_chain"):
            vc = _step(client, name="value_chain", schema=VALUE_CHAIN_SCHEMA,
                       payload={"theme": theme, "system_change": sc},
                       model_tier=model_tier, use_web_search=use_web_search, db=db)

        if on_progress:
            on_progress(0.50, "Step 3/5: Ranking scarce layers")
        with _heartbeat_while(on_progress, 0.50, 0.63, "Step 3/5: scarce_layer"):
            sl = _step(client, name="scarce_layer", schema=SCARCE_LAYER_SCHEMA,
                       payload={"value_chain": vc},
                       model_tier=model_tier, use_web_search=use_web_search, db=db)

        if on_progress:
            on_progress(0.65, "Step 4/5: Discovering A-share candidates")
        with _heartbeat_while(on_progress, 0.65, 0.78, "Step 4/5: company_universe"):
            cu = _step(client, name="company_universe", schema=COMPANY_UNIVERSE_SCHEMA,
                       payload={"ranked_layers": sl.get("ranked_layers", [])},
                       model_tier=model_tier, use_web_search=use_web_search, db=db)

        valid, dropped = _validate_codes(db, cu.get("candidates", []))
        if on_progress:
            on_progress(0.80, f"Validated candidates: {len(valid)} valid, {len(dropped)} dropped")

        if not valid:
            if on_progress:
                on_progress(0.95, "No valid A-share candidates found")
            result = ThemeScanResult(
                theme=theme,
                system_change=sc.get("system_change"),
                ranked_layers=sl.get("ranked_layers", []),
                ranked_candidates=[],
                evidence_grade="C",
                markdown_report="",
                dropped_codes=dropped,
                status=STATUS_EMPTY,
            )
            report = _persist(db, result, raw={
                "system_change": sc, "value_chain": vc, "scarce_layer": sl,
                "company_universe": cu, "dropped_codes": dropped,
            }, existing_report=existing_report)
            result.report_id = report.id
            if owns_session:
                db.commit()
            return result

        if on_progress:
            on_progress(0.85, "Step 5/5: Ranking and scoring candidates")
        with _heartbeat_while(on_progress, 0.85, 0.98, "Step 5/5: candidate_rank"):
            cr = _step(client, name="candidate_rank", schema=CANDIDATE_RANK_SCHEMA,
                       payload={"candidates": valid},
                       model_tier=model_tier, use_web_search=use_web_search, db=db)

        ranked = sorted(
            cr.get("ranked", []),
            key=lambda c: c.get("scarcity_score", 0.0),
            reverse=True,
        )
        result = ThemeScanResult(
            theme=theme,
            system_change=sc.get("system_change"),
            ranked_layers=sl.get("ranked_layers", []),
            ranked_candidates=ranked,
            evidence_grade=cr.get("evidence_grade", "B"),
            markdown_report=cr.get("markdown_report", ""),
            dropped_codes=dropped,
            status=STATUS_COMPLETED,
        )
        report = _persist(db, result, raw={
            "system_change": sc, "value_chain": vc, "scarce_layer": sl,
            "company_universe": cu, "dropped_codes": dropped, "candidate_rank": cr,
        }, existing_report=existing_report)
        result.report_id = report.id
        if owns_session:
            db.commit()
        return result
    finally:
        if owns_session:
            db.close()
