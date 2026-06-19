"""Time utilities — project default timezone is Asia/Shanghai (Beijing).

Historical context (2026-06-19): project previously stored naive UTC across
all timestamp columns, which made direct SQL reads confusing (+8h offset
from local experience). Going forward, all timestamp writes are naive
Beijing time. The legacy `utcnow()` is kept for backward compat (and is
effectively dead — 0 production callers).

DB-migration side: alembic revision shifts existing rows +8h so historical
reads remain consistent with new writes.
"""

from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9 fallback (project requires 3.14, so unreachable)
    ZoneInfo = None  # type: ignore[assignment]


BEIJING_TZ = ZoneInfo("Asia/Shanghai") if ZoneInfo else timezone.utc


def utcnow() -> datetime:
    """DEPRECATED: returns naive UTC. Kept for backward compat (0 callers).

    New code should use `now()` which returns naive Beijing (project default
    since 2026-06-19). See module docstring.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def now() -> datetime:
    """Project-default current time as naive Beijing (Asia/Shanghai).

    Use everywhere a timestamp is written to the DB. Naive (no tzinfo)
    matches the legacy `utcnow()` signature so callers don't have to think
    about timezone-awareness, just the timezone itself.
    """
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)


def now_utc() -> datetime:
    """Current time as naive UTC. For external APIs that require UTC
    (e.g. ISO 8601 with 'Z' suffix). Prefer `now()` for DB writes."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── SQL-layer helpers (L10 mitigation 2026-06-19) ─────────────────────────
# SQLite built-in functions (`datetime('now')`, `CURRENT_TIMESTAMP`,
# `func.now()` in SQLAlchemy) all return UTC. Our DB stores naive Beijing.
# Any raw SQL or ORM filter that compares a column to "now" must use these
# helpers instead, otherwise the comparison is off by 8h.
#
# Example:
#   BAD:  SELECT * FROM pipeline_runs WHERE started_at > datetime('now','-30s')
#   GOOD: SELECT * FROM pipeline_runs WHERE started_at > beijing_now_minus(seconds=30)

BEIJING_NOW_SQL = "datetime('now', '+8 hours')"  # raw SQL expression


def beijing_now_sql() -> str:
    """Raw SQL expression returning current Beijing time. Use in WHERE clauses
    that compare against timestamp columns stored as naive Beijing."""
    return BEIJING_NOW_SQL


def beijing_now_minus_sql(**kwargs) -> str:
    """Raw SQL expression: current Beijing time minus a delta.

    Args:
        seconds / minutes / hours / days: any combination, all added together
            (use negative to go back in time, but prefer this helper for clarity).
    """
    parts: list[str] = ["'+8 hours'"]
    if "seconds" in kwargs:
        parts.append(f"'-{int(kwargs['seconds'])} seconds'")
    if "minutes" in kwargs:
        parts.append(f"'-{int(kwargs['minutes'])} minutes'")
    if "hours" in kwargs:
        parts.append(f"'-{int(kwargs['hours'])} hours'")
    if "days" in kwargs:
        parts.append(f"'-{int(kwargs['days'])} days'")
    mods = ", ".join(parts)
    return f"datetime('now', {mods})"
