"""Research schemas — request/response models for the research router.

Covers serenity-skill workflow entities:
- ResearchTheme (research subject, e.g. "AI 半导体")
- ResearchRun (single execution)
- ValueChainLayer (8 standard layers per run)
- ScarceLayer (3-5 ranked bottlenecks)
- ResearchCompanyUniverse (≥20 candidates)
- ResearchEvidence (≥25 sources, 4-grade ladder)
- ResearchCompanyRanking (Top 3-7 priority picks)
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ── Enumerations (as Literal for type safety) ────────────────────────────
Market = Literal["A_SHARE", "HK", "US", "TW", "JP", "KR", "EU", "GLOBAL"]
AutoRefreshFreq = Literal["manual", "weekly", "monthly"]
RunStatus = Literal["running", "completed", "failed"]
TriggeredBy = Literal["manual", "scheduler"]
Classification = Literal[
    "controls", "supplies", "benefits", "weak", "story"
]
ExpansionDifficulty = Literal["high", "medium", "low"]
SourceType = Literal[
    "filing", "announcement", "transcript", "patent",
    "standard", "regulator_doc", "media", "trade_pub", "social_lead",
]
EvidenceGrade = Literal["strong", "medium", "weak", "lead"]


# ── ResearchTheme ────────────────────────────────────────────────────────
class ResearchThemeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    market: Market = "A_SHARE"
    auto_refresh_freq: AutoRefreshFreq = "manual"
    parent_theme_id: int | None = None


class ResearchThemeUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    market: Market | None = None
    status: Literal["active", "archived"] | None = None
    auto_refresh_freq: AutoRefreshFreq | None = None
    parent_theme_id: int | None = None


class ResearchThemeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    market: str
    status: str
    auto_refresh_freq: str
    last_run_at: datetime | None
    last_run_status: str | None
    last_run_error: str | None
    parent_theme_id: int | None
    created_at: datetime
    updated_at: datetime | None


# ── Child entity responses ──────────────────────────────────────────────
class ValueChainLayerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    layer_index: int = Field(..., ge=1, le=8)
    name: str
    description: str | None


class ScarceLayerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rank: int = Field(..., ge=1)
    layer_ref_id: int
    layer_name: str | None = None  # joined from ValueChainLayer
    scarcity_reason_md: str
    expansion_difficulty: str


class ResearchCompanyUniverseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stock_code: str
    classification: str
    layer_ref_id: int | None
    layer_name: str | None = None  # joined
    note: str | None


class ResearchEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stock_code: str | None
    source_type: str
    source_url: str
    source_title: str
    published_at: date | None
    grade: str
    summary_md: str


class ResearchCompanyRankingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rank: int = Field(..., ge=1, le=7)
    stock_code: str
    constrains_what: str
    chain_position: str
    rank_reason_md: str
    evidence_summary_md: str
    main_risk_md: str


# ── ResearchRun (aggregates all child entities) ──────────────────────────
class ResearchRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    research_theme_id: int
    status: str
    scope_market: str
    scope_time_window: str
    triggered_by: str
    llm_provider: str
    llm_token_input: int
    llm_token_output: int
    llm_search_count: int
    attempt_count: int
    system_change_md: str | None
    failure_conditions_md: str | None
    next_steps_md: str | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None

    # Children (populated by service layer with joins)
    value_chain_layers: list[ValueChainLayerResponse] = Field(default_factory=list)
    scarce_layers: list[ScarceLayerResponse] = Field(default_factory=list)
    company_universe: list[ResearchCompanyUniverseResponse] = Field(default_factory=list)
    evidence: list[ResearchEvidenceResponse] = Field(default_factory=list)
    company_ranking: list[ResearchCompanyRankingResponse] = Field(default_factory=list)


class ResearchRunSummaryResponse(BaseModel):
    """Lightweight run view for list endpoints (no children)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    research_theme_id: int
    status: str
    triggered_by: str
    llm_provider: str
    llm_token_input: int
    llm_token_output: int
    llm_search_count: int
    started_at: datetime
    completed_at: datetime | None
    company_count: int = 0
    evidence_count: int = 0
    ranking_count: int = 0


# ── Trigger / Export requests ────────────────────────────────────────────
class ResearchRunTriggerRequest(BaseModel):
    """Manual trigger of a serenity run. Returns immediately with run_id (Q10 async)."""

    market: Market | None = None  # override theme default if provided
    time_window: str = "3-12M"


class ResearchExportRequest(BaseModel):
    """Export ranked companies to Watchlist or Candidate (Q3 D / Q11 no Checklist)."""

    target: Literal["watchlist", "candidate"]
    rank_max: int = Field(3, ge=1, le=7)  # export Top N
    watchlist_group_id: int | None = None  # required if target=watchlist


class ResearchExportResponse(BaseModel):
    exported_count: int
    skipped_codes: list[str] = Field(default_factory=list)  # already exists / invalid
    target: str
    target_id: int | None = None  # watchlist_group_id if applicable


class StockResearchAppearance(BaseModel):
    """Reverse-link entry for StockDetail panel (Q14)."""

    research_theme_id: int
    research_theme_name: str
    run_id: int
    run_started_at: datetime
    rank: int | None  # null if in universe but not ranked
    classification: str | None  # null if only in ranking
    constrains_what: str | None
    main_risk_md: str | None
