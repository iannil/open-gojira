import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.rate_limit import limiter

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
    alerts, audit_log,
    cash as cash_router,
    cockpit as cockpit_router, corp_actions as corp_actions_router,
    data_management, dividend,
    drafts as drafts_router, eval_set as eval_set_router,
    fee_configs as fee_configs_router, financial,
    health, market,
    metrics as metrics_router,
    notifications as notifications_router,
    observability as observability_router,
    portfolio,
    research_v2 as research_v2_router,
    task as task_router,
    risk_rules as risk_rules_router,
    scheduler as scheduler_router,
    stocks,
    system_alerts as system_alerts_router,
    theme_scan as theme_scan_router,
    trades as trades_router,
    valuation,
)

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

    from app.db.session import SessionLocal

    # Eagerly load pipelines to register all @register_pipeline decorators
    # and avoid import deadlocks when endpoints are called concurrently.
    import app.services.pipelines  # noqa: F401
    import app.core.event_handlers  # noqa: F401 — register all event handlers

    # F15 (2026-06-18): recover any pipeline runs stuck in running/pending
    # state. Previous uvicorn process was killed mid-execution → background
    # thread died but pipeline_runs.status never advanced. Without this,
    # stuck runs pollute the UI forever (24h+ observed in production DB).
    try:
        from app.services.pipelines.manager import PipelineManager
        with SessionLocal() as db:
            recovered = PipelineManager.recover_stale_runs(db)
            db.commit()
        if recovered:
            log.info("Recovered %d stale pipeline runs on startup", recovered)
    except Exception:
        logger.exception("recover_stale_runs failed on startup")

    # Recover orphaned research reports: any report stuck in "running" state
    # is presumed dead (server restart / crash killed the in-memory task).
    try:
        from app.models.research_report import ResearchReport, STATUS_RUNNING
        with SessionLocal() as db:
            orphaned = (
                db.query(ResearchReport)
                .filter(ResearchReport.status == STATUS_RUNNING)
                .all()
            )
            for r in orphaned:
                r.status = "failed"
                r.markdown_output = (
                    "**报告未完成** — 服务重启导致研究任务中断。\n\n"
                    "请重新触发深度研究以生成完整报告。"
                )
            db.commit()
        if orphaned:
            log.info("Recovered %d orphaned research reports on startup", len(orphaned))
    except Exception:
        logger.exception("recover_orphaned_research failed on startup")

    # Start the unified TaskEngine
    from app.services.task.engine import TaskEngine
    from app.routers.task import set_engine

    # Import all @task definitions to register them with TaskRegistry
    import app.tasks  # noqa: F401

    task_engine = TaskEngine(tick_interval=1.0, cron_check_interval=60, max_sync_workers=4)
    set_engine(task_engine)
    task_engine.start()

    yield

    task_engine.shutdown(wait=True, timeout=10.0)
    from app.core.events import shutdown_executor
    shutdown_executor(wait=True, timeout=10.0)
    log.info("Application_Stopping")


app = FastAPI(
    title="Gojira Investment System",
    lifespan=lifespan,
)

# ── Rate Limiting ─────────────────────────────────────────────────────────
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
app.include_router(alerts.router)
app.include_router(scheduler_router.router)
app.include_router(audit_log.router)
app.include_router(drafts_router.router)
app.include_router(cockpit_router.router)
app.include_router(data_management.router)
app.include_router(observability_router.router)
app.include_router(trades_router.router)
app.include_router(cash_router.router)
app.include_router(fee_configs_router.router)
app.include_router(system_alerts_router.router)
app.include_router(corp_actions_router.router)
app.include_router(notifications_router.router)
app.include_router(risk_rules_router.router)
app.include_router(research_v2_router.router)
app.include_router(theme_scan_router.router)
app.include_router(metrics_router.router)
app.include_router(task_router.router)
app.include_router(eval_set_router.router)
