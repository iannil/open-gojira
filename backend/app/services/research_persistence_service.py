"""Persist LLM research result to 6 child tables.

Maps JSON output from submit_research tool call to ORM rows:
- value_chain_layers (8)
- scarce_layers (3-5)
- research_company_universe (≥20)
- research_evidence (≥25)
- research_company_ranking (3-7)
- run-level markdown fields (system_change / failure_conditions / next_steps)
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models.research_company_ranking import ResearchCompanyRanking
from app.models.research_company_universe import ResearchCompanyUniverse
from app.models.research_evidence import ResearchEvidence
from app.models.research_claim import ResearchClaim
from app.models.research_run import ResearchRun
from app.models.scarce_layer import ScarceLayer
from app.models.value_chain_layer import ValueChainLayer

logger = logging.getLogger(__name__)


class ResearchPersistenceError(Exception):
    """Raised when LLM output fails schema/size validation."""


def persist_research_result(
    db: Session, run: ResearchRun, result: dict[str, Any]
) -> None:
    """Validate + persist LLM output. Mutates run in place (markdown fields).

    Raises ResearchPersistenceError on validation failure.
    """
    _require_fields(result, [
        "system_change", "value_chain", "scarce_layers",
        "company_universe", "evidence", "company_ranking",
        "failure_conditions", "next_steps",
    ])

    value_chain = result["value_chain"]
    scarce_layers_data = result["scarce_layers"]
    universe_data = result["company_universe"]
    evidence_data = result["evidence"]
    ranking_data = result["company_ranking"]

    if len(value_chain) != 8:
        raise ResearchPersistenceError(
            f"value_chain must have exactly 8 layers, got {len(value_chain)}"
        )
    if not (3 <= len(scarce_layers_data) <= 5):
        raise ResearchPersistenceError(
            f"scarce_layers must have 3-5 items, got {len(scarce_layers_data)}"
        )
    if len(universe_data) < 20:
        raise ResearchPersistenceError(
            f"company_universe must have ≥20 items, got {len(universe_data)}"
        )
    if len(evidence_data) < 25:
        raise ResearchPersistenceError(
            f"evidence must have ≥25 items, got {len(evidence_data)}"
        )
    if not (3 <= len(ranking_data) <= 7):
        raise ResearchPersistenceError(
            f"company_ranking must have 3-7 items, got {len(ranking_data)}"
        )

    # 1) Value chain layers (8) — capture id mapping for scarce_layers FK
    layer_id_by_index: dict[int, int] = {}
    for layer in value_chain:
        _require_fields(layer, ["layer_index", "name"])
        row = ValueChainLayer(
            research_run_id=run.id,
            layer_index=layer["layer_index"],
            name=layer["name"],
            description=layer.get("description"),
        )
        db.add(row)
        db.flush()
        layer_id_by_index[row.layer_index] = row.id

    # 2) Scarce layers (3-5)
    for sl in scarce_layers_data:
        _require_fields(sl, ["rank", "layer_index", "reason", "difficulty"])
        layer_ref_id = layer_id_by_index.get(sl["layer_index"])
        if layer_ref_id is None:
            raise ResearchPersistenceError(
                f"scarce_layer rank={sl['rank']} references unknown "
                f"layer_index={sl['layer_index']}"
            )
        db.add(ScarceLayer(
            research_run_id=run.id,
            rank=sl["rank"],
            layer_ref_id=layer_ref_id,
            scarcity_reason_md=sl["reason"],
            expansion_difficulty=sl["difficulty"],
        ))

    # 3) Company universe (≥20)
    for c in universe_data:
        _require_fields(c, ["stock_code", "classification"])
        layer_ref_id = (
            layer_id_by_index[c["layer_index"]]
            if c.get("layer_index") in layer_id_by_index
            else None
        )
        db.add(ResearchCompanyUniverse(
            research_run_id=run.id,
            stock_code=c["stock_code"],
            classification=c["classification"],
            layer_ref_id=layer_ref_id,
            note=c.get("note"),
        ))

    # 4) Evidence (≥25)
    for ev in evidence_data:
        _require_fields(ev, [
            "source_url", "source_title", "source_type", "grade", "summary",
        ])
        db.add(ResearchEvidence(
            research_run_id=run.id,
            stock_code=ev.get("stock_code"),
            source_type=ev["source_type"],
            source_url=ev["source_url"],
            source_title=ev["source_title"],
            published_at=_parse_date(ev.get("published_at")),
            grade=ev["grade"],
            summary_md=ev["summary"],
        ))

    # 5) Company ranking (3-7)
    for r in ranking_data:
        _require_fields(r, [
            "rank", "stock_code", "constrains_what", "chain_position",
            "rank_reason", "evidence_summary", "main_risk",
        ])
        db.add(ResearchCompanyRanking(
            research_run_id=run.id,
            rank=r["rank"],
            stock_code=r["stock_code"],
            constrains_what=r["constrains_what"],
            chain_position=r["chain_position"],
            rank_reason_md=r["rank_reason"],
            evidence_summary_md=r["evidence_summary"],
            main_risk_md=r["main_risk"],
        ))

    # 6) Run-level markdown summaries + structured claims (Phase 2 #9)
    run.system_change_md = result["system_change"]

    failure_claims = _persist_claims(
        db, run.id, result["failure_conditions"], "failure_condition"
    )
    next_step_claims = _persist_claims(
        db, run.id, result["next_steps"], "next_step"
    )
    # Derive backward-compat md from structured claims (Q5 双写决策)
    run.failure_conditions_md = _derive_md(failure_claims)
    run.next_steps_md = _derive_md(next_step_claims)

    db.flush()


def _persist_claims(
    db: Session,
    run_id: int,
    raw_claims: list[Any],
    claim_type: str,
) -> list[ResearchClaim]:
    """Persist list of structured claim dicts to research_claims table.

    Each claim must have: subject / predicate / outcome (required)
    Optional: signal / stock_codes / layer_index

    Returns the list of persisted ResearchClaim ORM rows (used by caller
    to derive md).

    Raises ResearchPersistenceError on missing required fields.
    """
    persisted: list[ResearchClaim] = []
    for i, raw in enumerate(raw_claims):
        # Tolerate legacy string format (defensive — shouldn't happen post-Q19)
        if isinstance(raw, str):
            logger.warning(
                "Claim type=%s position=%d is bare string (legacy?), wrapping",
                claim_type, i,
            )
            raw = {
                "subject": "(未结构化)",
                "predicate": "(legacy)",
                "outcome": raw,
            }

        _require_fields(raw, ["subject", "predicate", "outcome"])

        stock_codes = _validate_stock_codes(raw.get("stock_codes"))
        layer_idx = raw.get("layer_index")
        if layer_idx is not None and not (1 <= int(layer_idx) <= 8):
            logger.warning(
                "Claim type=%s position=%d has invalid layer_index=%r, setting None",
                claim_type, i, layer_idx,
            )
            layer_idx = None

        claim = ResearchClaim(
            research_run_id=run_id,
            type=claim_type,
            position=i,
            subject=raw["subject"],
            predicate=raw["predicate"],
            signal=raw.get("signal"),
            outcome=raw["outcome"],
            stock_codes_json=json.dumps(stock_codes, ensure_ascii=False),
            layer_index=int(layer_idx) if layer_idx is not None else None,
        )
        db.add(claim)
        persisted.append(claim)
    return persisted


def _validate_stock_codes(raw: Any) -> list[str]:
    """Validate and normalize A-share 6-digit stock codes.

    Drops entries that don't match ^\\d{6}$. Logs warn for each dropped.
    """
    import re
    if not raw:
        return []
    if not isinstance(raw, list):
        logger.warning("stock_codes not a list: %r, returning []", raw)
        return []
    pattern = re.compile(r"^\d{6}$")
    valid: list[str] = []
    for code in raw:
        if isinstance(code, str) and pattern.match(code):
            valid.append(code)
        else:
            logger.warning("Dropping invalid stock_code=%r", code)
    return valid


def _derive_md(claims: list[ResearchClaim]) -> str:
    """Derive backward-compat markdown from structured claims.

    Format: "{position}. {subject}{predicate}" + optional "({signal})" + ",{outcome}"
    """
    if not claims:
        return ""
    lines: list[str] = []
    for i, c in enumerate(claims):
        parts = [c.subject, c.predicate]
        line = "".join(p for p in parts if p)
        if c.signal:
            line += f"({c.signal})"
        if c.outcome:
            line += f",{c.outcome}" if line else c.outcome
        lines.append(f"{i+1}. {line}")
    return "\n".join(lines)


def _require_fields(d: dict[str, Any], required: list[str]) -> None:
    for k in required:
        if k not in d or d[k] in (None, ""):
            raise ResearchPersistenceError(f"missing required field: {k}")


def _parse_date(value: Any) -> date | None:
    """Parse LLM-returned date string (YYYY-MM-DD or similar) to date.

    LLMs typically return ISO date strings, but may also return:
    - None (no published_at)
    - Already a date object (defensive)
    - Strings like "2025-03-28" / "2025/3/28" / "2025年3月28日"

    Returns None on unparseable input — evidence row keeps published_at=None.
    """
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        s = value.strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日"):
            try:
                return date.strptime(s, fmt)
            except ValueError:
                continue
        # ISO 8601 may have time component — try fromisoformat with fallback
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            logger.warning("Could not parse published_at=%r — storing None", value)
            return None
    logger.warning("Unexpected published_at type %s — storing None", type(value).__name__)
    return None
