import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.core.exceptions import EntityNotFound, DuplicateEntity, BusinessRuleViolation, InvalidState
from app.core.observability import (
    configure_logging,
    get_logger,
    set_trace_id,
    _generate_id,
    _emit_obs_log,
)
from app.db.base import Base
from app.db.engine import engine
from app.models import *  # noqa: F401,F403 — ensure all models register with Base.metadata
from app.routers import (
    alerts, audit_log, cashflow_goal, candidates as candidates_router,
    cockpit as cockpit_router, data_management, dividend,
    drafts as drafts_router, financial, health, market,
    observability as observability_router,
    plans as plans_router, portfolio,
    review as review_router, scheduler as scheduler_router,
    stocks, strategies as strategies_router, theme as theme_router, valuation,
    watchlist,
)
from app.scheduler import shutdown_scheduler, start_scheduler

logger = logging.getLogger(__name__)


def _run_alembic_upgrade() -> None:
    """Apply any pending Alembic revisions on top of the current schema.

    `Base.metadata.create_all` covers fresh DBs; this picks up post-initial
    column additions (and future migrations) for DBs created before a
    revision landed. Idempotent — Alembic skips revisions already stamped.
    """
    from pathlib import Path
    from alembic import command
    from alembic.config import Config

    project_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    try:
        command.upgrade(cfg, "head")
    except Exception:
        logger.exception("Alembic upgrade failed; continuing with create_all schema")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Configure structured logging
    configure_logging()
    log = get_logger("gojira.main")
    log.info("Application_Starting")

    # Create all tables for a fresh DB, then apply Alembic revisions.
    Base.metadata.create_all(bind=engine)
    _run_alembic_upgrade()

    # Seed built-in strategies and plans
    from app.db.session import SessionLocal
    from app.services.builtin_seeder import seed_all
    try:
        with SessionLocal() as db:
            seed_all(db)
    except Exception:
        logger.exception("Builtin seeding failed")

    # Eagerly load pipelines to register all @register_pipeline decorators
    # and avoid import deadlocks when endpoints are called concurrently.
    import app.services.pipelines  # noqa: F401
    import app.core.event_handlers  # noqa: F401 — register all event handlers

    start_scheduler()

    yield

    shutdown_scheduler()
    from app.core.events import shutdown_executor
    shutdown_executor(wait=True, timeout=10.0)
    log.info("Application_Stopping")


app = FastAPI(
    title="Gojira Investment System",
    lifespan=lifespan,
)

# ── Rate Limiting ─────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ── Request Tracing Middleware ────────────────────────────────────────────
@app.middleware("http")
async def request_tracing_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Request-ID") or _generate_id()
    set_trace_id(trace_id)

    # Record request details
    sid = _generate_id()
    request_body = None
    if request.method in ("POST", "PUT", "PATCH"):
        try:
            raw = await request.body()
            request_body = raw[:1024].decode("utf-8", errors="replace") if raw else None
        except Exception:
            request_body = "<unreadable>"

    # Sanitize sensitive fields before logging
    if request_body:
        import re
        request_body = re.sub(
            r'("(?:token|password|secret|api_key|apikey)"\s*:\s*")[^"]*(")',
            r'\1***\2',
            request_body,
            flags=re.IGNORECASE,
        )

    req_event = {
        "span_id": sid,
        "method": request.method,
        "path": str(request.url.path),
        "query": str(request.query_params) or None,
        "request_body": request_body,
    }
    log = get_logger("gojira.http")
    log.info("HTTP_Request", **req_event)
    _emit_obs_log({"event": "HTTP_Request", **req_event})

    start = time.monotonic()
    response = await call_next(request)
    duration_ms = (time.monotonic() - start) * 1000

    resp_event = {
        "span_id": sid,
        "method": request.method,
        "path": str(request.url.path),
        "status": response.status_code,
        "duration_ms": round(duration_ms, 2),
    }
    log.info("HTTP_Response", **resp_event)
    _emit_obs_log({"event": "HTTP_Response", **resp_event})

    response.headers["X-Request-ID"] = trace_id
    return response


# ── Domain Exception Handlers ─────────────────────────────────────────────
@app.exception_handler(EntityNotFound)
async def entity_not_found_handler(request: Request, exc: EntityNotFound):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(DuplicateEntity)
async def duplicate_entity_handler(request: Request, exc: DuplicateEntity):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(BusinessRuleViolation)
async def business_rule_handler(request: Request, exc: BusinessRuleViolation):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(InvalidState)
async def invalid_state_handler(request: Request, exc: InvalidState):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


# ── Global Exception Handler ─────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log = get_logger("gojira.exceptions")
    log.error(
        "Unhandled_Exception",
        path=str(request.url),
        method=request.method,
        error_type=type(exc).__name__,
        error_message=str(exc),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ── CORS ─────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

# ── Routes ───────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(stocks.router)
app.include_router(valuation.router)
app.include_router(portfolio.router)
app.include_router(dividend.router)
app.include_router(market.router)
app.include_router(financial.router)
app.include_router(watchlist.router)
app.include_router(alerts.router)
app.include_router(scheduler_router.router)
app.include_router(cashflow_goal.router)
app.include_router(audit_log.router)
app.include_router(plans_router.router)
app.include_router(drafts_router.router)
app.include_router(strategies_router.router)
app.include_router(candidates_router.router)
app.include_router(cockpit_router.router)
app.include_router(review_router.router)
app.include_router(theme_router.router)
app.include_router(data_management.router)
app.include_router(observability_router.router)
