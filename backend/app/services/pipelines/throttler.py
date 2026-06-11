"""Adaptive throttler — dynamic rate limiting based on API budget and error rate."""

from __future__ import annotations

import logging
import random
import time
from collections import deque

logger = logging.getLogger(__name__)


class AdaptiveThrottler:
    """Adjusts wait time between API calls based on:
    - Remaining API budget (calls per period)
    - Recent error rate
    """

    def __init__(
        self,
        budget: int = 10000,
        period_hours: int = 24 * 30,
        min_interval: float = 0.2,
        max_interval: float = 2.0,
        error_window: int = 300,
        error_threshold: float = 0.1,
    ):
        self.budget = budget
        self.period_hours = period_hours
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.error_window = error_window
        self.error_threshold = error_threshold

        self._call_times: deque[float] = deque()
        self._error_times: deque[float] = deque()
        self._total_calls = 0
        self._total_errors = 0

    def acquire(self) -> float:
        """Wait before next API call. Returns actual wait time."""
        now = time.monotonic()
        self._prune_old(now)

        usage_ratio = len(self._call_times) / self.budget if self.budget > 0 else 0
        recent_errors = sum(1 for t in self._error_times if now - t < self.error_window)
        recent_calls = max(1, sum(1 for t in self._call_times if now - t < self.error_window))
        error_rate = recent_errors / recent_calls

        if usage_ratio > 0.8:
            wait = self.max_interval * 2
        elif error_rate > self.error_threshold:
            wait = self.max_interval
        else:
            wait = self.min_interval

        self._call_times.append(now)
        self._total_calls += 1
        if wait > 0:
            jittered = wait + random.uniform(0, 0.1)
            time.sleep(jittered)
            return jittered
        return 0.0

    def record_error(self) -> None:
        self._error_times.append(time.monotonic())
        self._total_errors += 1

    @property
    def stats(self) -> dict:
        return {
            "total_calls": self._total_calls,
            "total_errors": self._total_errors,
            "budget_used_pct": round(
                len(self._call_times) / self.budget * 100, 1
            ) if self.budget > 0 else 0,
            "recent_error_rate": round(
                len([t for t in self._error_times if time.monotonic() - t < self.error_window])
                / max(1, len([t for t in self._call_times if time.monotonic() - t < self.error_window]))
                * 100, 1
            ),
        }

    def _prune_old(self, now: float) -> None:
        period_seconds = self.period_hours * 3600
        while self._call_times and now - self._call_times[0] > period_seconds:
            self._call_times.popleft()
        while self._error_times and now - self._error_times[0] > self.error_window:
            self._error_times.popleft()
