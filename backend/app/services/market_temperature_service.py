"""Market temperature service — "先判断大环境".

Computes a 0-100 temperature based on major index PE percentile.
- Temperature <= 30: 冷 (low market, good for buying)
- Temperature 30-70: 温 (normal range)
- Temperature >= 70: 热 (high market, cautious)

Uses CSI 300 (000300) PE percentile as the primary signal.
Result is cached in a simple module-level variable (refreshed daily).
"""

from __future__ import annotations

import logging
import threading
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cashflow_goal import CashflowGoal

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 4 * 3600  # 4 hours

_cache: dict[str, float | None] = {}
_cache_ts: float = 0.0
_cache_lock = threading.Lock()


def compute_temperature(db: Session) -> float | None:
    """Compute market temperature (0-100) based on index PE percentile.

    Strategy:
    1. Check if we have a cached temperature (4-hour TTL)
    2. If not, get PE percentile from CashflowGoal.current_index_pe_pct
    3. Convert PE percentile to temperature (PE percentile 0→temp 0, percentile 100→temp 100)

    Returns:
        Temperature 0-100, or None if data unavailable
    """
    global _cache_ts
    now = time.monotonic()

    with _cache_lock:
        if now - _cache_ts < _CACHE_TTL_SECONDS:
            cached_temp = _cache.get("temperature")
            if cached_temp is not None:
                return cached_temp

    row = db.execute(
        select(CashflowGoal).where(CashflowGoal.id == 1)
    ).scalar_one_or_none()

    if row is None or row.current_index_pe_pct is None:
        with _cache_lock:
            _cache["temperature"] = None
            _cache_ts = now
        return None

    temperature = float(row.current_index_pe_pct)

    with _cache_lock:
        _cache["temperature"] = temperature
        _cache_ts = now

    return temperature


def get_temperature_label(temperature: float | None) -> str:
    """Get human-readable temperature label.

    Args:
        temperature: Temperature 0-100, or None

    Returns:
        Label: "冷" (cold), "温" (warm), "热" (hot), or "未知" (unknown)
    """
    if temperature is None:
        return "未知"
    if temperature <= 30:
        return "冷"
    if temperature >= 70:
        return "热"
    return "温"


def clear_cache() -> None:
    """Clear the temperature cache (useful for testing)."""
    global _cache_ts
    with _cache_lock:
        _cache.clear()
        _cache_ts = 0.0
