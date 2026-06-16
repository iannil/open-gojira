"""Serenity research module configuration.

Q8 cost & rate-limit hard caps (per single run).
"""
from __future__ import annotations

from typing import Any


# Cost estimate: blended price per 1K tokens (input + output average).
# GLM-4.x ~¥0.005/1K tokens. Used by budget check + cockpit monthly spend.
# Adjust if ZHIPU_MODEL switches to a different pricing tier.
COST_PER_1K_TOKENS_CNY: float = 0.005


SERENITY_RUN_CONFIG: dict[str, Any] = {
    # Q13: Triple hard constraint (max_tokens / max_searches / timeout)
    # Path B (2026-06-16): bumped to accommodate reasoning model + Path B
    # context (search_results JSON adds ~5K tokens to prompt). 32K output
    # gives LLM room for the structured submit_research JSON.
    "max_tokens": 32000,
    "max_searches": 30,  # alias of max_search_queries for backward compat
    "max_search_queries": 30,
    "max_query_generation_tokens": 2000,  # reasoning model needs room
    "timeout_seconds": 600,
    "temperature": 0.3,  # low temp for structured output stability
    # Q8 retry policy
    "retry_on_failure": 1,
    # Q10 rate limit (same theme within N minutes blocks trigger)
    "rate_limit_per_theme_minutes": 5,
    # Q8 monthly budget soft limit (CNY) — alert when exceeded, do not block
    "monthly_budget_cny": 100.0,
    # GLM model default (fallback when ZHIPU_MODEL not in .env)
    "default_model": "glm-4.7",
}
