"""Hybrid deterministic scoring for deep_research (trading-philosophy.md §3).

The LLM's synthesis returns an advisory overall_score; these pure functions
recompute the *authoritative* score from each master's own 1-5 score using the
declarative profile weights, derive the recommendation, and flag divergence
from the LLM for observability. No I/O, no DB — unit-testable.
"""
from __future__ import annotations

from typing import Optional

from app.core.scoring_config import (
    ADVANTAGE_MASTERS,
    DEFAULT_SOURCE,
    PROFILE_WEIGHTS,
    REC_FALLBACK,
    REC_THRESHOLDS,
    SCORE_DIVERGENCE_EPSILON,
)


def _weights_for(source: str) -> dict[str, float]:
    return PROFILE_WEIGHTS.get(source, PROFILE_WEIGHTS[DEFAULT_SOURCE])


def _effective_dimensions(
    contributing: dict[str, float],
    per_master_scores: dict[str, float],
    advantage_sources: Optional[dict[str, Optional[str]]],
) -> list[tuple[float, float]]:
    """Resolve contributing masters into (weight, score) dimensions, applying the
    §4.1 same-source collapse.

    Masters in ADVANTAGE_MASTERS that share a non-null advantage_source tag are
    collapsed into ONE dimension: weight = max(group weights), score = mean(group
    scores). Everything else passes through unchanged.
    """
    if not advantage_sources:
        return [(w, per_master_scores[m]) for m, w in contributing.items()]

    by_tag: dict[str, list[str]] = {}
    dims: list[tuple[float, float]] = []
    for master, weight in contributing.items():
        tag = advantage_sources.get(master) if master in ADVANTAGE_MASTERS else None
        if tag:
            by_tag.setdefault(tag, []).append(master)
        else:
            dims.append((weight, per_master_scores[master]))

    for members in by_tag.values():
        if len(members) >= 2:
            group_weight = max(contributing[m] for m in members)
            group_score = sum(per_master_scores[m] for m in members) / len(members)
            dims.append((group_weight, group_score))
        else:
            m = members[0]
            dims.append((contributing[m], per_master_scores[m]))
    return dims


def compute_overall_score(
    per_master_scores: dict[str, float],
    source: str,
    advantage_sources: Optional[dict[str, Optional[str]]] = None,
) -> Optional[float]:
    """Weighted average of each master's own 1-5 score under the source profile.

    - Only masters present in BOTH the profile and the input contribute.
    - Weights are renormalized over the contributing dimensions, so a missing
      master output degrades gracefully instead of skewing toward zero.
    - Scores for keys not in the profile (e.g. stray "scarcity" on a compounder
      run) are ignored.
    - ``advantage_sources`` (master → primary advantage tag) enables the §4.1
      same-source collapse; omit/None for no cap.
    - Returns None when no master contributes (caller treats as PASS).
    """
    weights = _weights_for(source)
    contributing = {
        master: weight
        for master, weight in weights.items()
        if master in per_master_scores
    }
    if not contributing:
        return None
    dims = _effective_dimensions(contributing, per_master_scores, advantage_sources)
    weight_sum = sum(w for w, _ in dims)
    if weight_sum == 0:
        return None
    return sum(w * s for w, s in dims) / weight_sum


def recommend(score: Optional[float]) -> str:
    """Map an authoritative score to BUY / HOLD / PASS via REC_THRESHOLDS."""
    if score is None:
        return REC_FALLBACK
    for threshold, label in REC_THRESHOLDS:
        if score >= threshold:
            return label
    return REC_FALLBACK


def score_divergence(
    llm_score: Optional[float],
    python_score: Optional[float],
) -> dict:
    """Compare the LLM's advisory score against the Python authoritative score.

    Returns {"divergent": bool, "delta": float|None}. When either score is
    missing, divergence is not flagged (delta None).
    """
    if llm_score is None or python_score is None:
        return {"divergent": False, "delta": None}
    delta = abs(llm_score - python_score)
    return {"divergent": delta > SCORE_DIVERGENCE_EPSILON, "delta": delta}
