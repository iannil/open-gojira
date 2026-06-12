import logging

from sqlalchemy import create_engine, event

from app.config import settings

logger = logging.getLogger(__name__)

# ⚠️ DO NOT use poolclass=pool.StaticPool in production code.
# StaticPool shares a single DBAPI connection across threads, breaking
# transaction isolation and producing phantom data corruption under
# concurrent writes. It is ONLY acceptable in test fixtures
# (see tests/conftest.py) for in-memory SQLite test isolation.
#
# Production uses the default QueuePool which gives each thread its own
# connection. Verified by spike_sqlite_concurrency.py (S0.5).
# See docs/reports/spike-results-2026-06-12.md for details.

# SQLite requires check_same_thread=False for multi-threaded use;
# PostgreSQL does not accept this argument.
_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

_engine_kwargs = {}
if _is_sqlite:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, **_engine_kwargs)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):
    """Set SQLite performance pragmas. No-op for other database backends."""
    if not _is_sqlite:
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


logger.info(
    "Database engine created",
    extra={"database_url": settings.DATABASE_URL.split("://")[0] + "://***"},
)
