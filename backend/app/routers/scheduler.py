"""Scheduler admin endpoints — job config, manual trigger, execution history."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.scheduler import JOB_REGISTRY, list_jobs, reschedule_job, run_job_now
from app.schemas.scheduler import (
    JobExecutionResponse,
    JobRunResponse,
    SchedulerJobResponse,
    SchedulerJobUpdate,
)
from app.services.scheduler_config_service import (
    cron_to_trigger,
    list_executions,
    update_config,
)

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


@router.get("/jobs", response_model=list[SchedulerJobResponse])
def api_list_jobs():
    return list_jobs()


@router.get("/jobs/{job_id}", response_model=SchedulerJobResponse)
def api_get_job(job_id: str):
    jobs = {j["job_id"]: j for j in list_jobs()}
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return jobs[job_id]


@router.put("/jobs/{job_id}", response_model=SchedulerJobResponse)
def api_update_job(job_id: str, payload: SchedulerJobUpdate, db: Session = Depends(get_db)):
    if job_id not in JOB_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown job: {job_id}")
    if payload.cron_expr is not None:
        try:
            cron_to_trigger(payload.cron_expr)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Invalid cron expression: {e}")
    if payload.cron_expr is None and payload.enabled is None:
        raise HTTPException(status_code=422, detail="No fields to update")

    job = update_config(db, job_id, cron_expr=payload.cron_expr, enabled=payload.enabled)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job config not found: {job_id}")
    db.commit()

    reschedule_job(job_id)

    jobs = {j["job_id"]: j for j in list_jobs()}
    return jobs[job_id]


@router.post("/jobs/{job_id}/run", response_model=JobRunResponse)
def api_run_job(job_id: str):
    try:
        return run_job_now(job_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}/executions", response_model=list[JobExecutionResponse])
def api_job_executions(job_id: str, limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)):
    rows = list_executions(db, job_id=job_id, limit=limit)
    return [
        JobExecutionResponse(
            id=r.id,
            job_id=r.job_id,
            status=r.status,
            started_at=str(r.started_at) if r.started_at else None,
            finished_at=str(r.finished_at) if r.finished_at else None,
            duration_ms=r.duration_ms,
            result_summary=r.result_summary,
            error_message=r.error_message,
        )
        for r in rows
    ]


@router.get("/executions", response_model=list[JobExecutionResponse])
def api_all_executions(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)):
    rows = list_executions(db, limit=limit)
    return [
        JobExecutionResponse(
            id=r.id,
            job_id=r.job_id,
            status=r.status,
            started_at=str(r.started_at) if r.started_at else None,
            finished_at=str(r.finished_at) if r.finished_at else None,
            duration_ms=r.duration_ms,
            result_summary=r.result_summary,
            error_message=r.error_message,
        )
        for r in rows
    ]
