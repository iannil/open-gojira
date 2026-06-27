"""Data management endpoints — stock pool, sync, cleanup."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.data_management import (
    CleanupPreview,
    CleanupRequest,
    CleanupResult,
    DataStatusOverview,
    PipelineStartRequest,
    StockPoolAddRequest,
    StockPoolItem,
    StockPoolRemoveRequest,
    StockSearchResult,
    SyncTriggerRequest,
)
from app.services import data_management_service as svc

router = APIRouter(prefix="/api/data-management", tags=["data-management"])


# ── Stock Pool ───────────────────────────────────────────────────────────

@router.get("/universe", response_model=list[StockPoolItem])
def list_universe(db: Session = Depends(get_db)):
    return svc.list_stock_pool(db)


@router.post("/universe/search", response_model=list[StockSearchResult])
def search_stocks(keyword: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    return svc.search_stocks(db, keyword)


@router.post("/universe/add")
def add_to_pool(payload: StockPoolAddRequest, db: Session = Depends(get_db)):
    added = svc.add_to_pool(db, payload.stock_codes)
    return {"added": added}


@router.post("/universe/batch-remove")
def batch_remove(payload: StockPoolRemoveRequest, db: Session = Depends(get_db)):
    removed = svc.remove_from_pool(db, payload.stock_codes)
    return {"removed": removed}


# ── Data Status ──────────────────────────────────────────────────────────

@router.get("/status", response_model=DataStatusOverview)
def get_status(db: Session = Depends(get_db)):
    return svc.get_data_status(db)


# ── Sync ─────────────────────────────────────────────────────────────────

@router.post("/sync/{data_type}")
def trigger_sync(data_type: str, payload: SyncTriggerRequest, db: Session = Depends(get_db)):
    valid_types = {"valuations", "financials", "klines", "dividends", "universe_bootstrap"}
    if data_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid data type. Must be one of: {valid_types}")
    try:
        return svc.trigger_sync(db, data_type, payload.stock_codes, payload.years)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sync/{task_id}/status")
def get_sync_status(task_id: str, db: Session = Depends(get_db)):
    from app.services.pipelines.manager import PipelineManager
    mgr = PipelineManager(db)
    result = mgr.get_run(task_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return result


# ── Cleanup ──────────────────────────────────────────────────────────────

@router.get("/cleanup/{data_type}/preview", response_model=CleanupPreview)
def preview_cleanup(
    data_type: str,
    before_date: str | None = None,
    after_date: str | None = None,
    stock_codes: list[str] | None = Query(None),
    db: Session = Depends(get_db),
):
    valid_types = {"valuations", "financials", "klines", "dividends", "universe_bootstrap"}
    if data_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid data type. Must be one of: {valid_types}")
    return svc.preview_cleanup(db, data_type, before_date, after_date, stock_codes)


@router.post("/cleanup/{data_type}", response_model=CleanupResult)
def execute_cleanup(data_type: str, payload: CleanupRequest, db: Session = Depends(get_db)):
    valid_types = {"valuations", "financials", "klines", "dividends", "universe_bootstrap"}
    if data_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid data type. Must be one of: {valid_types}")
    return svc.execute_cleanup(db, data_type, payload.before_date, payload.after_date, payload.stock_codes)


# ── Pipeline ──────────────────────────────────────────────────────────────

@router.post("/pipeline/{pipeline_type}/start")
async def start_pipeline(pipeline_type: str, request: Request, db: Session = Depends(get_db)):
    from app.services.pipelines.manager import PipelineManager

    valid_types = {"valuations", "financials", "klines", "dividends", "universe_bootstrap"}
    if pipeline_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid pipeline type: {pipeline_type}")

    payload = await request.json()
    parsed = PipelineStartRequest(**payload)

    mgr = PipelineManager(db)
    try:
        # Map pipeline_type to corresponding @task for TaskEngine visibility
        _TASK_MAP = {
            "valuations": "daily_base_sync",
            "financials": "quarterly_financials_refresh",
            "klines": "daily_kline_sync",
            "dividends": "weekly_dividend_sync",
            "universe_bootstrap": "daily_universe_bootstrap",
        }
        task_id = _TASK_MAP.get(pipeline_type)
        if task_id:
            try:
                from app.routers.task import _get_engine as _task_engine
                engine = _task_engine()
                engine.trigger_task(task_id, db, triggered_by="api")
                db.commit()
                return {"status": "triggered", "task_id": task_id, "message": f"Triggered via TaskEngine"}
            except Exception:
                logger.warning("TaskEngine unavailable for %s, falling back to PipelineManager", pipeline_type)

        # Fallback: direct PipelineManager execution (background=False = sync)
        return mgr.start(
            pipeline_type=pipeline_type,
            stock_codes=parsed.stock_codes,
            force_full=parsed.force_full,
            years=parsed.years,
            granularity=parsed.granularity,
            background=False,
        )
    except ValueError as e:
        msg = str(e)
        if msg == "No stocks to sync":
            raise HTTPException(
                status_code=400,
                detail="没有可同步的股票。请先将股票添加到观察池后再启动同步。",
            )
        raise HTTPException(status_code=400, detail=msg)


@router.get("/pipeline/runs")
def list_pipeline_runs(
    pipeline_type: str | None = None,
    status: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    from app.services.pipelines.manager import PipelineManager
    mgr = PipelineManager(db)
    runs = mgr.list_runs(pipeline_type=pipeline_type, status=status, limit=limit)
    return {"runs": runs}


@router.get("/pipeline/runs/{run_id}")
def get_pipeline_run(run_id: str, db: Session = Depends(get_db)):
    from app.services.pipelines.manager import PipelineManager
    mgr = PipelineManager(db)
    result = mgr.get_run(run_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Pipeline run {run_id} not found")
    return result


@router.post("/pipeline/runs/{run_id}/retry")
def retry_pipeline_run(run_id: str, db: Session = Depends(get_db)):
    from app.services.pipelines.manager import PipelineManager
    mgr = PipelineManager(db)
    result = mgr.retry_failed(run_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Pipeline run {run_id} not found")
    return result


@router.post("/pipeline/runs/{run_id}/cancel")
def cancel_pipeline_run(run_id: str, db: Session = Depends(get_db)):
    from app.services.pipelines.manager import PipelineManager
    mgr = PipelineManager(db)
    mgr.cancel(run_id)
    return {"message": "cancelled"}


@router.get("/dead-letters/stats")
def dead_letter_stats(pipeline_type: str | None = None, db: Session = Depends(get_db)):
    from app.services.pipelines.dead_letter import DeadLetterQueue
    return DeadLetterQueue.get_stats(db, pipeline_type)


@router.get("/health")
def pipeline_health(db: Session = Depends(get_db)):
    from app.services.pipelines.manager import PipelineManager
    mgr = PipelineManager(db)
    return mgr.get_health()


@router.get("/api-usage")
def api_usage(db: Session = Depends(get_db)):
    from app.services.pipelines.manager import PipelineManager
    mgr = PipelineManager(db)
    return mgr.get_api_usage()


@router.get("/quality")
def get_quality(db: Session = Depends(get_db)):
    from app.services.data_quality_service import compute_quality
    return compute_quality(db)