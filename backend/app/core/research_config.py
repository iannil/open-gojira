"""Serenity research module configuration.

Q8 cost & rate-limit hard caps (per single run).
"""
from __future__ import annotations

from typing import Any


SERENITY_RUN_CONFIG: dict[str, Any] = {
    # Q13: Triple hard constraint (max_tokens / max_searches / timeout)
    "max_tokens": 16000,
    "max_searches": 30,
    "timeout_seconds": 300,
    "temperature": 0.3,  # low temp for structured output stability
    # Q8 retry policy
    "retry_on_failure": 1,
    # Q10 rate limit (same theme within N minutes blocks trigger)
    "rate_limit_per_theme_minutes": 5,
    # Q8 monthly budget soft limit (CNY) — alert when exceeded, do not block
    "monthly_budget_cny": 100.0,
    # GLM model default (configurable via .env ZHIPU_MODEL)
    "default_model": "glm-4.7",
}
