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
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.stock import Stock
from app.models.theme_scan_report import (
    STATUS_COMPLETED,
    STATUS_EMPTY,
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


def _persist(db: Session, result: ThemeScanResult, raw: dict) -> ThemeScanReport:
    report = ThemeScanReport(
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
) -> ThemeScanResult:
    """Run the full 5-step theme_scan workflow for one theme.

    Args:
        theme: investment theme, e.g. "CPO 光模块"
        model_tier: GLM tier
        use_web_search: enable web_search in LLM steps
        db_session: caller's session; else creates own
        llm_client: optional injected client (for testing)

    Returns:
        ThemeScanResult with ranked candidates (status="empty" if no valid
        A-share candidate survived code validation).
    """
    owns_session = db_session is None
    db = db_session or SessionLocal()
    client = llm_client or get_llm_client()

    try:
        sc = _step(client, name="system_change", schema=SYSTEM_CHANGE_SCHEMA,
                   payload={"theme": theme},
                   model_tier=model_tier, use_web_search=use_web_search, db=db)
        vc = _step(client, name="value_chain", schema=VALUE_CHAIN_SCHEMA,
                   payload={"theme": theme, "system_change": sc},
                   model_tier=model_tier, use_web_search=use_web_search, db=db)
        sl = _step(client, name="scarce_layer", schema=SCARCE_LAYER_SCHEMA,
                   payload={"value_chain": vc},
                   model_tier=model_tier, use_web_search=use_web_search, db=db)
        cu = _step(client, name="company_universe", schema=COMPANY_UNIVERSE_SCHEMA,
                   payload={"ranked_layers": sl.get("ranked_layers", [])},
                   model_tier=model_tier, use_web_search=use_web_search, db=db)

        valid, dropped = _validate_codes(db, cu.get("candidates", []))

        if not valid:
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
            })
            result.report_id = report.id
            if owns_session:
                db.commit()
            return result

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
        })
        result.report_id = report.id
        if owns_session:
            db.commit()
        return result
    finally:
        if owns_session:
            db.close()
