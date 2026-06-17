"""Candidate CRUD schemas."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel


class CandidateResponse(BaseModel):
    id: int
    plan_id: int
    plan_name: str = ""
    stock_code: str
    stock_name: str = ""
    stock_industry: Optional[str] = None
    stock_security_theme: Optional[str] = None
    stock_quadrant: Optional[str] = None
    stock_tier: Optional[str] = None
    stock_qiu_score: int = 0
    stock_hq_region: Optional[str] = None
    dividend_payout_commitment_pct: Optional[float] = None
    """B4-4 N4 (invest3 §八): forward 分红承诺 0.0-1.0, null=未录入"""
    status: Literal["active", "removed"]
    first_seen_at: Any = None
    last_confirmed_at: Any = None
    last_eval: Optional[dict] = None
    pinned: bool
    notes: Optional[str] = None
    source: str = "rule_based"
    """'rule_based' (plan_runner output) | 'serenity' (research export)"""


class CandidateUpdate(BaseModel):
    pinned: Optional[bool] = None
    notes: Optional[str] = None
