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
