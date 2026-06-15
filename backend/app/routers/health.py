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

    # Zhipu API key configured (serenity research module)
    checks["checks"]["zhipu_api_key"] = "configured" if settings.ZHIPU_API_KEY else "missing"
    if not settings.ZHIPU_API_KEY:
        checks["status"] = "degraded"

    return checks


@router.get("/health/zhipu")
def health_check_zhipu():
    """Deep probe for Zhipu AI (GLM) connectivity.

    Mirrors /api/health/lixinger pattern. Attempts a minimal API call to
    verify (a) API key is valid and (b) account has usable quota.
    """
    if not settings.ZHIPU_API_KEY:
        return {
            "status": "degraded",
            "error": "ZHIPU_API_KEY not configured",
            "hint": "Get one at https://open.bigmodel.cn/usercenter/apikeys",
        }

    try:
        from zhipuai import ZhipuAI

        client_kwargs = {"api_key": settings.ZHIPU_API_KEY}
        if settings.ZHIPU_BASE_URL:
            client_kwargs["base_url"] = settings.ZHIPU_BASE_URL
        client = ZhipuAI(**client_kwargs)

        # Minimal call: 1-token completion. Verifies auth + quota without
        # burning significant tokens (~0.001 CNY at GLM-4.7 pricing).
        response = client.chat.completions.create(
            model=settings.ZHIPU_MODEL or "glm-4.7",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            timeout=10,
        )
        usage = getattr(response, "usage", None)
        return {
            "status": "ok",
            "model": settings.ZHIPU_MODEL,
            "tokens_used": getattr(usage, "total_tokens", 0) if usage else 0,
        }
    except Exception as exc:
        msg = str(exc)
        # 429 code 1113 = quota exhausted
        if "1113" in msg or "429" in msg:
            return {
                "status": "degraded",
                "error": "quota_exhausted",
                "detail": msg[:300],
                "hint": "Recharge at https://open.bigmodel.cn/usercenter/overview",
            }
        return {
            "status": "degraded",
            "error": type(exc).__name__,
            "detail": msg[:300],
        }

