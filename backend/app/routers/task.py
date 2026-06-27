"""REST API for the unified Task scheduling system."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as DBSession

from app.db.session import get_db
from app.models.task import Task as TaskModel, TaskRun
from app.schemas.task import (
    TaskHealthResponse,
    TaskResponse,
    TaskRunDetailResponse,
    TaskRunResponse,
    TaskUpdate,
    TriggerTaskResponse,
)
from app.services.task.dependency import DependencyChecker
from app.services.task.engine import TaskEngine
from app.services.task.registry import get_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

# Engine is set once during app startup (see main.py lifespan)
_engine: TaskEngine | None = None


def set_engine(engine: TaskEngine) -> None:
    """Inject the TaskEngine singleton (called from main.py lifespan)."""
    global _engine
    _engine = engine


def _get_engine() -> TaskEngine:
    if _engine is None:
        raise HTTPException(status_code=503, detail="TaskEngine not initialized")
    return _engine


# ── Health ─────────────────────────────────────────────────────────────


@router.get("/health", response_model=TaskHealthResponse)
def task_health(
    db: DBSession = Depends(get_db),
):
    """Get the health status of the task scheduling system."""
    engine = _get_engine()
    return engine.get_health(db)


# ── Task Definitions ───────────────────────────────────────────────────


@router.get("", response_model=list[TaskResponse])
def list_tasks(
    db: DBSession = Depends(get_db),
):
    """List all registered task definitions with last-run info."""
    engine = _get_engine()
    tasks = db.query(TaskModel).order_by(TaskModel.task_id).all()
    return [engine.enrich_task_response(t, db) for t in tasks]


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: str,
    db: DBSession = Depends(get_db),
):
    """Get a single task definition with details."""
    engine = _get_engine()
    task = db.query(TaskModel).filter(TaskModel.task_id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return engine.enrich_task_response(task, db)


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: str,
    body: TaskUpdate,
    db: DBSession = Depends(get_db),
):
    """Update a task's cron, timeout, retry config, or enabled flag."""
    engine = _get_engine()
    task = db.query(TaskModel).filter(TaskModel.task_id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    if body.cron_expr is not None:
        task.cron_expr = body.cron_expr
    if body.enabled is not None:
        task.enabled = body.enabled
    if body.timeout_seconds is not None:
        task.timeout_seconds = body.timeout_seconds
    if body.retry_config is not None:
        task.retry_config = json.dumps(body.retry_config)
    if body.description is not None:
        task.description = body.description

    db.flush()
    db.commit()
    return engine.enrich_task_response(task, db)


@router.post("/{task_id}/trigger", response_model=TriggerTaskResponse)
def trigger_task(
    task_id: str,
    db: DBSession = Depends(get_db),
):
    """Manually trigger a task."""
    engine = _get_engine()
    try:
        run = engine.trigger_task(task_id, db, triggered_by="api")
        db.commit()
        return TriggerTaskResponse(
            task_id=task_id,
            run_id=run.id,
            status=run.status,
            message="Task queued for execution",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{task_id}/pause", response_model=TaskResponse)
def pause_task(
    task_id: str,
    db: DBSession = Depends(get_db),
):
    """Pause a task (prevent future scheduled runs)."""
    engine = _get_engine()
    if not engine.pause_task(task_id, db):
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    db.commit()
    task = db.query(TaskModel).filter(TaskModel.task_id == task_id).first()
    return engine.enrich_task_response(task, db)


@router.post("/{task_id}/resume", response_model=TaskResponse)
def resume_task(
    task_id: str,
    db: DBSession = Depends(get_db),
):
    """Resume a paused task."""
    engine = _get_engine()
    if not engine.resume_task(task_id, db):
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    db.commit()
    task = db.query(TaskModel).filter(TaskModel.task_id == task_id).first()
    return engine.enrich_task_response(task, db)


# ── Task Runs ──────────────────────────────────────────────────────────


@router.get("/runs/list", response_model=list[TaskRunResponse])
def list_task_runs(
    task_id: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: DBSession = Depends(get_db),
):
    """List task execution runs with optional filtering."""
    engine = _get_engine()
    query = db.query(TaskRun)

    if task_id:
        query = query.filter(TaskRun.task_id == task_id)
    if status:
        query = query.filter(TaskRun.status == status)

    runs = query.order_by(TaskRun.created_at.desc()).limit(limit).all()
    return [engine.run_to_dict(r) for r in runs]


@router.get("/runs/{run_id}", response_model=TaskRunDetailResponse)
def get_task_run(
    run_id: int,
    db: DBSession = Depends(get_db),
):
    """Get a single task run with parent task details."""
    engine = _get_engine()
    run = db.query(TaskRun).filter(TaskRun.id == run_id).first()
    if run is None:
        raise HTTPException(status_code=404, detail=f"TaskRun {run_id} not found")

    result = engine.run_to_dict(run)
    task = db.query(TaskModel).filter(TaskModel.task_id == run.task_id).first()
    if task:
        result["task"] = engine.enrich_task_response(task, db)
    return result


@router.post("/runs/{run_id}/cancel", response_model=dict)
def cancel_task_run(
    run_id: int,
    db: DBSession = Depends(get_db),
):
    """Cancel a queued or running task run."""
    engine = _get_engine()
    if not engine.cancel_task_run(run_id, db):
        raise HTTPException(status_code=404, detail=f"TaskRun {run_id} not found")
    db.commit()
    return {"run_id": run_id, "status": "cancelled"}


@router.post("/runs/{run_id}/retry", response_model=TriggerTaskResponse)
def retry_task_run(
    run_id: int,
    db: DBSession = Depends(get_db),
):
    """Retry a failed task run by triggering its parent task."""
    run = db.query(TaskRun).filter(TaskRun.id == run_id).first()
    if run is None:
        raise HTTPException(status_code=404, detail=f"TaskRun {run_id} not found")

    engine = _get_engine()
    try:
        new_run = engine.trigger_task(run.task_id, db, triggered_by="retry")
        db.commit()
        return TriggerTaskResponse(
            task_id=run.task_id,
            run_id=new_run.id,
            status=new_run.status,
            message="Retry triggered",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


    return engine.get_health(db)
