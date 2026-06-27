import logging

from sqlalchemy import create_engine

from app.config import settings

logger = logging.getLogger(__name__)

# Production uses the default QueuePool which gives each thread its own
# connection. Verified by spike_sqlite_concurrency.py (S0.5).
# See docs/reports/spike-results-2026-06-12.md for details.

engine = create_engine(settings.DATABASE_URL)

logger.info(
    "Database engine created",
    extra={"database_url": settings.DATABASE_URL.split("://")[0] + "://***"},
)
