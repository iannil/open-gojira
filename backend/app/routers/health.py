import logging

from fastapi import APIRouter
from sqlalchemy import text

from app.config import settings
from app.db.engine import engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health_check():
    checks = {"status": "ok", "checks": {}}

    # Database connectivity
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["checks"]["database"] = "ok"
    except Exception as e:
        logger.error("Health check: database failed: %s", e)
        checks["checks"]["database"] = "error"
        checks["status"] = "degraded"

    # Lixinger token configured
    checks["checks"]["lixinger_token"] = "configured" if settings.LIXINGER_TOKEN else "missing"
    if not settings.LIXINGER_TOKEN:
        checks["status"] = "degraded"

    return checks
