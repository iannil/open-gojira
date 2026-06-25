"""Deep-research scoring configuration (declarative).

Per docs/standards/trading-philosophy.md §3 + §4.1 (hybrid scoring,
grill 2026-06-25): the LLM's overall_score is advisory; Python recomputes the
authoritative score from each master's own 1-5 score using these profile
weights, then derives BUY/HOLD/PASS from REC_THRESHOLDS.

Profile is selected by a candidate's sourcing engine (§3, by sourcing path):
  - "quality_screen" → COMPOUNDER profile (value-compounder engine)
  - "theme_scan"     → THEME profile (serenity bottleneck engine)
"""
from __future__ import annotations

# Sourcing-engine identifiers — also the keys of PROFILE_WEIGHTS.
SOURCE_QUALITY_SCREEN = "quality_screen"
SOURCE_THEME_SCAN = "theme_scan"

# Default profile when a stock's provenance is unknown. Until theme_scan exists,
# every researched stock arrives via quality_screen, so compounder is correct.
DEFAULT_SOURCE = SOURCE_QUALITY_SCREEN


# Per-master weights by profile. Each profile's weights sum to 1.0 over the
# masters it includes; the scorer renormalizes over whichever masters are
# actually present in a given run (robust to a missing master output).
PROFILE_WEIGHTS: dict[str, dict[str, float]] = {
    # Value-compounder profile — the established 段25/巴30/芒20/李25 weighting
    # (synthesis.md prose, now authoritative here).
    SOURCE_QUALITY_SCREEN: {
        "duan": 0.25,
        "buffett": 0.30,
        "munger": 0.20,
        "lilu": 0.25,
    },
    # Theme/bottleneck profile — 李录 down-weighted (10yr-certainty must not veto
    # emerging plays) and serenity 卡点 ("scarcity") added as a 5th dimension.
    # NOTE: DRAFT numbers. The "scarcity" dimension is not produced until
    # theme_scan_pipeline exists (Phase 2 milestone, task #7); finalize then.
    SOURCE_THEME_SCAN: {
        "duan": 0.22,
        "buffett": 0.26,
        "munger": 0.18,
        "lilu": 0.10,
        "scarcity": 0.24,
    },
}


# Controlled vocabulary for the "持久优势" axis (§4.1 same-source cap). A master
# whose score is advantage-driven tags ONE primary advantage_source from this
# enum so Python can detect overlap by exact match. Reuses Buffett's moat
# taxonomy + serenity's chain scarcity.
ADVANTAGE_SOURCES: tuple[str, ...] = (
    "brand",              # 品牌溢价
    "network_effect",     # 网络效应
    "cost_advantage",     # 规模/工艺成本优势
    "switching_cost",     # 转换成本
    "regulatory_barrier", # 牌照/特许/监管壁垒
    "intangible_assets",  # 专利/配方/无形资产
    "chain_scarcity",     # 产业链稀缺层/卡点 (serenity)
)

# Only these masters assess the advantage axis and are eligible for same-source
# collapse. 芒格 (risk) and 李录 (certainty/longevity) are different axes and
# never collapse, even if a stray tag appears on them.
ADVANTAGE_MASTERS: frozenset[str] = frozenset({"duan", "buffett", "scarcity"})


# Recommendation thresholds on the 1.0-5.0 authoritative score, highest first.
# score >= threshold → label; falls through to PASS. Mirrors synthesis.md.
REC_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (4.0, "BUY"),
    (3.0, "HOLD"),
)
REC_FALLBACK = "PASS"

# If |llm_advisory_score - python_authoritative_score| exceeds this, emit an
# observability log (prompt-drift signal). Does not block the run.
SCORE_DIVERGENCE_EPSILON = 0.5
