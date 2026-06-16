"""Research diff service — Phase 2 #10 (Q15).

Computes diff between two completed ResearchRuns of the same theme across
three dimensions:
  1. company_ranking升降 (stock_code keyed)
  2. failure_conditions claims 变化 (subject keyed; legacy runs degrade)
  3. scarce_layers 增减 (layer_index keyed)

Per spec 2026-06-16-phase2-num10-run-diff.md:
- Runs must be same theme + both completed (caller validates)
- Real-time compute, no persistence (Run data is immutable)
- Per-dimension failure isolation: one dimension's error doesn't kill others
- Legacy run (no structured claims) → claims_diff=null + degradation flag
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.research_claim import ResearchClaim
from app.models.research_company_ranking import ResearchCompanyRanking
from app.models.research_run import ResearchRun
from app.models.scarce_layer import ScarceLayer
from app.models.value_chain_layer import ValueChainLayer

logger = logging.getLogger(__name__)


# ── Pydantic schemas (response contract) ─────────────────────────────────


class RunRef(BaseModel):
    id: int
    started_at: Any  # datetime serialized as str by FastAPI
    status: str


class ClaimSnapshot(BaseModel):
    predicate: str
    signal: str | None
    outcome: str
    stock_codes: list[str]
    layer_index: int | None


class RankingDiffItem(BaseModel):
    stock_code: str
    name: str
    rank_from: int | None
    rank_to: int | None
    delta: int | None
    category: str  # promoted | demoted | new_in | dropped | unchanged


class RankingDiff(BaseModel):
    promoted: list[RankingDiffItem]
    demoted: list[RankingDiffItem]
    new_in: list[RankingDiffItem]
    dropped: list[RankingDiffItem]
    unchanged: list[RankingDiffItem]


class ClaimDiffItem(BaseModel):
    subject: str
    claim_from: ClaimSnapshot | None
    claim_to: ClaimSnapshot | None
    signal_changed: bool
    category: str  # new_risk | resolved | tightened | loosened | unchanged


class ClaimsDiff(BaseModel):
    new_risks: list[ClaimDiffItem]
    resolved: list[ClaimDiffItem]
    tightened: list[ClaimDiffItem]
    loosened: list[ClaimDiffItem]
    unchanged: list[ClaimDiffItem]


class ScarceLayerDiffItem(BaseModel):
    layer_index: int
    layer_name: str
    rank_from: int | None
    rank_to: int | None
    category: str  # entered | exited | reranked | unchanged


class ScarceLayerDiff(BaseModel):
    entered: list[ScarceLayerDiffItem]
    exited: list[ScarceLayerDiffItem]
    reranked: list[ScarceLayerDiffItem]
    unchanged: list[ScarceLayerDiffItem]


class RunDiffResponse(BaseModel):
    run_a: RunRef
    run_b: RunRef
    summary: dict[str, dict[str, int]]
    ranking_diff: RankingDiff
    claims_diff: ClaimsDiff | None
    scarce_layers_diff: ScarceLayerDiff
    degradations: list[str]


class DiffError(Exception):
    """Raised on diff computation failure (validation / not found / etc)."""


# ── Public API ────────────────────────────────────────────────────────────


def compute_diff(db: Session, run_a_id: int, run_b_id: int) -> RunDiffResponse:
    """Compute diff between two completed runs of the same theme.

    Caller responsibility (router-level): validate same theme + both completed
    + exists + different. This function assumes inputs are valid.

    Per-dimension failures are isolated: a dimension's exception is caught,
    the dimension is set to null (or its degraded form), and a flag is added
    to `degradations`.

    Run ordering: caller may pass either order; this function returns run_a
    as the EARLIER one (by started_at) and run_b as the LATER. UI relies on
    this for left=earlier / right=later rendering.
    """
    run_a = db.get(ResearchRun, run_a_id)
    run_b = db.get(ResearchRun, run_b_id)
    if run_a is None:
        raise DiffError(f"run {run_a_id} not found")
    if run_b is None:
        raise DiffError(f"run {run_b_id} not found")

    # Normalize order: run_a earlier, run_b later
    if run_a.started_at and run_b.started_at and run_a.started_at > run_b.started_at:
        run_a, run_b = run_b, run_a

    degradations: list[str] = []

    # Dimension 1: ranking
    try:
        ranking_diff = _diff_ranking(db, run_a.id, run_b.id)
    except Exception as exc:
        logger.exception("ranking_diff failed for %s vs %s", run_a.id, run_b.id)
        ranking_diff = RankingDiff(
            promoted=[], demoted=[], new_in=[], dropped=[], unchanged=[]
        )
        degradations.append(f"ranking_diff_failed: {type(exc).__name__}")

    # Dimension 2: claims (may degrade for legacy runs)
    try:
        claims_diff = _diff_claims(db, run_a.id, run_b.id)
    except _LegacyRunError as exc:
        claims_diff = None
        degradations.append(f"claims_diff_unavailable_legacy: {exc}")
    except Exception as exc:
        logger.exception("claims_diff failed for %s vs %s", run_a.id, run_b.id)
        claims_diff = None
        degradations.append(f"claims_diff_failed: {type(exc).__name__}")

    # Dimension 3: scarce_layers
    try:
        scarce_layers_diff = _diff_scarce_layers(db, run_a.id, run_b.id)
    except Exception as exc:
        logger.exception("scarce_layers_diff failed for %s vs %s", run_a.id, run_b.id)
        scarce_layers_diff = ScarceLayerDiff(
            entered=[], exited=[], reranked=[], unchanged=[]
        )
        degradations.append(f"scarce_layers_diff_failed: {type(exc).__name__}")

    summary = {
        "ranking": _summarize_ranking(ranking_diff),
        "claims": _summarize_claims(claims_diff) if claims_diff else {},
        "scarce_layers": _summarize_scarce_layers(scarce_layers_diff),
    }

    return RunDiffResponse(
        run_a=RunRef(id=run_a.id, started_at=run_a.started_at, status=run_a.status),
        run_b=RunRef(id=run_b.id, started_at=run_b.started_at, status=run_b.status),
        summary=summary,
        ranking_diff=ranking_diff,
        claims_diff=claims_diff,
        scarce_layers_diff=scarce_layers_diff,
        degradations=degradations,
    )


# ── Dimension 1: ranking ─────────────────────────────────────────────────


def _diff_ranking(db: Session, run_a_id: int, run_b_id: int) -> RankingDiff:
    """Diff company_ranking by stock_code. Returns 5 buckets."""
    a_rows = db.query(ResearchCompanyRanking).filter(
        ResearchCompanyRanking.research_run_id == run_a_id
    ).all()
    b_rows = db.query(ResearchCompanyRanking).filter(
        ResearchCompanyRanking.research_run_id == run_b_id
    ).all()

    a_by_code = {r.stock_code: r for r in a_rows}
    b_by_code = {r.stock_code: r for r in b_rows}

    all_codes = set(a_by_code) | set(b_by_code)
    out = RankingDiff(
        promoted=[], demoted=[], new_in=[], dropped=[], unchanged=[]
    )

    for code in all_codes:
        a = a_by_code.get(code)
        b = b_by_code.get(code)
        # ResearchCompanyRanking has no `name` column (persist drops it).
        # Use stock_code as display; UI can lookup actual name from stocks table.
        name = code

        if a and b:
            delta = b.rank - a.rank
            if delta > 0:
                # Note: lower rank number = higher position. rank 1 → 3 is a
                # demotion (got worse). delta = b.rank - a.rank: positive
                # means rank number went up = position went down.
                item = RankingDiffItem(
                    stock_code=code, name=name,
                    rank_from=a.rank, rank_to=b.rank, delta=delta,
                    category="demoted",
                )
                out.demoted.append(item)
            elif delta < 0:
                item = RankingDiffItem(
                    stock_code=code, name=name,
                    rank_from=a.rank, rank_to=b.rank, delta=delta,
                    category="promoted",
                )
                out.promoted.append(item)
            else:
                out.unchanged.append(RankingDiffItem(
                    stock_code=code, name=name,
                    rank_from=a.rank, rank_to=b.rank, delta=0,
                    category="unchanged",
                ))
        elif b and not a:
            out.new_in.append(RankingDiffItem(
                stock_code=code, name=name,
                rank_from=None, rank_to=b.rank, delta=None,
                category="new_in",
            ))
        elif a and not b:
            out.dropped.append(RankingDiffItem(
                stock_code=code, name=name,
                rank_from=a.rank, rank_to=None, delta=None,
                category="dropped",
            ))

    # Sort each bucket by absolute delta (biggest changes first)
    out.promoted.sort(key=lambda x: x.delta or 0)  # most negative first
    out.demoted.sort(key=lambda x: -(x.delta or 0))  # most positive first
    out.new_in.sort(key=lambda x: x.rank_to or 99)
    out.dropped.sort(key=lambda x: x.rank_from or 99)
    out.unchanged.sort(key=lambda x: x.rank_to or 99)
    return out


def _summarize_ranking(d: RankingDiff) -> dict[str, int]:
    return {
        "promoted": len(d.promoted),
        "demoted": len(d.demoted),
        "new_in": len(d.new_in),
        "dropped": len(d.dropped),
        "unchanged": len(d.unchanged),
    }


# ── Dimension 2: claims ──────────────────────────────────────────────────


class _LegacyRunError(Exception):
    """Raised when a run has no structured claims (pre-Phase 2 #9)."""


def _diff_claims(db: Session, run_a_id: int, run_b_id: int) -> ClaimsDiff:
    """Diff failure_condition claims by subject. Raises _LegacyRunError if
    either run has zero structured claims (legacy / pre-Phase-2-#9)."""
    import json

    a_claims = db.query(ResearchClaim).filter(
        ResearchClaim.research_run_id == run_a_id,
        ResearchClaim.type == "failure_condition",
    ).order_by(ResearchClaim.position).all()
    b_claims = db.query(ResearchClaim).filter(
        ResearchClaim.research_run_id == run_b_id,
        ResearchClaim.type == "failure_condition",
    ).order_by(ResearchClaim.position).all()

    # Legacy detection: zero claims in either run
    if not a_claims and not b_claims:
        raise _LegacyRunError("both runs have no structured claims")
    if not a_claims:
        raise _LegacyRunError(f"run {run_a_id} has no structured claims")
    if not b_claims:
        raise _LegacyRunError(f"run {run_b_id} has no structured claims")

    a_by_subject = {c.subject: c for c in a_claims}
    b_by_subject = {c.subject: c for c in b_claims}

    all_subjects = set(a_by_subject) | set(b_by_subject)
    out = ClaimsDiff(
        new_risks=[], resolved=[], tightened=[], loosened=[], unchanged=[]
    )

    for subject in all_subjects:
        a = a_by_subject.get(subject)
        b = b_by_subject.get(subject)

        if a and not b:
            out.resolved.append(ClaimDiffItem(
                subject=subject,
                claim_from=_claim_snapshot(a), claim_to=None,
                signal_changed=False, category="resolved",
            ))
        elif b and not a:
            out.new_risks.append(ClaimDiffItem(
                subject=subject,
                claim_from=None, claim_to=_claim_snapshot(b),
                signal_changed=True, category="new_risk",
            ))
        else:
            signal_changed = (a.signal or "") != (b.signal or "")
            # Simplified: any signal text change = "tightened" by default.
            # Future: parse thresholds to differentiate tightened vs loosened.
            if signal_changed:
                out.tightened.append(ClaimDiffItem(
                    subject=subject,
                    claim_from=_claim_snapshot(a), claim_to=_claim_snapshot(b),
                    signal_changed=True, category="tightened",
                ))
            else:
                out.unchanged.append(ClaimDiffItem(
                    subject=subject,
                    claim_from=_claim_snapshot(a), claim_to=_claim_snapshot(b),
                    signal_changed=False, category="unchanged",
                ))

    return out


def _claim_snapshot(c: ResearchClaim) -> ClaimSnapshot:
    import json
    try:
        codes = json.loads(c.stock_codes_json) if c.stock_codes_json else []
    except (json.JSONDecodeError, TypeError):
        codes = []
    return ClaimSnapshot(
        predicate=c.predicate,
        signal=c.signal,
        outcome=c.outcome,
        stock_codes=codes,
        layer_index=c.layer_index,
    )


def _summarize_claims(d: ClaimsDiff) -> dict[str, int]:
    return {
        "new_risks": len(d.new_risks),
        "resolved": len(d.resolved),
        "tightened": len(d.tightened),
        "loosened": len(d.loosened),
        "unchanged": len(d.unchanged),
    }


# ── Dimension 3: scarce_layers ───────────────────────────────────────────


def _diff_scarce_layers(
    db: Session, run_a_id: int, run_b_id: int
) -> ScarceLayerDiff:
    """Diff scarce_layers by layer_index (stable across runs).

    Each run has its own value_chain_layers rows, so layer_ref_id differs
    between runs even for the same conceptual layer (e.g. "系统集成" layer 2).
    Key by layer_index instead — that's the serenity-canonical identifier
    (1=下游客户 ... 8=物理基建).
    """
    a_scarce = db.query(ScarceLayer).filter(
        ScarceLayer.research_run_id == run_a_id
    ).all()
    b_scarce = db.query(ScarceLayer).filter(
        ScarceLayer.research_run_id == run_b_id
    ).all()

    # Resolve layer_ref_id → layer_index per run via value_chain_layers
    def _resolve(scarce_rows, run_id):
        vcl_rows = db.query(ValueChainLayer).filter(
            ValueChainLayer.research_run_id == run_id,
        ).all()
        ref_to_index = {v.id: v.layer_index for v in vcl_rows}
        ref_to_name = {v.id: v.name for v in vcl_rows}
        return [
            (ref_to_index.get(s.layer_ref_id), ref_to_name.get(s.layer_ref_id, ""), s)
            for s in scarce_rows
        ]

    a_resolved = _resolve(a_scarce, run_a_id)
    b_resolved = _resolve(b_scarce, run_b_id)

    a_by_index = {idx: s for idx, _, s in a_resolved if idx is not None}
    b_by_index = {idx: s for idx, _, s in b_resolved if idx is not None}

    # Build layer_index → name map (prefer A's name; fall back to B's)
    a_name_by_idx = {idx: name for idx, name, _ in a_resolved if idx is not None}
    b_name_by_idx = {idx: name for idx, name, _ in b_resolved if idx is not None}

    out = ScarceLayerDiff(
        entered=[], exited=[], reranked=[], unchanged=[]
    )

    all_indices = set(a_by_index) | set(b_by_index)
    for layer_index in all_indices:
        layer_name = a_name_by_idx.get(layer_index) or b_name_by_idx.get(layer_index, "")
        a = a_by_index.get(layer_index)
        b = b_by_index.get(layer_index)

        if a and b:
            if a.rank == b.rank:
                out.unchanged.append(ScarceLayerDiffItem(
                    layer_index=layer_index, layer_name=layer_name,
                    rank_from=a.rank, rank_to=b.rank, category="unchanged",
                ))
            else:
                out.reranked.append(ScarceLayerDiffItem(
                    layer_index=layer_index, layer_name=layer_name,
                    rank_from=a.rank, rank_to=b.rank, category="reranked",
                ))
        elif b and not a:
            out.entered.append(ScarceLayerDiffItem(
                layer_index=layer_index, layer_name=layer_name,
                rank_from=None, rank_to=b.rank, category="entered",
            ))
        elif a and not b:
            out.exited.append(ScarceLayerDiffItem(
                layer_index=layer_index, layer_name=layer_name,
                rank_from=a.rank, rank_to=None, category="exited",
            ))

    out.entered.sort(key=lambda x: x.rank_to or 99)
    out.exited.sort(key=lambda x: x.rank_from or 99)
    out.reranked.sort(key=lambda x: abs((x.rank_to or 0) - (x.rank_from or 0)), reverse=True)
    out.unchanged.sort(key=lambda x: x.rank_to or 99)
    return out


def _summarize_scarce_layers(d: ScarceLayerDiff) -> dict[str, int]:
    return {
        "entered": len(d.entered),
        "exited": len(d.exited),
        "reranked": len(d.reranked),
        "unchanged": len(d.unchanged),
    }
