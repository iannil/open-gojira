"""Pydantic schemas for scheduler configuration and execution history."""

from pydantic import BaseModel


class SchedulerJobResponse(BaseModel):
    job_id: str
    cron_expr: str
    enabled: bool
    description: str | None = None
    next_run_time: str | None = None
    last_run_at: str | None = None
    last_run_status: str | None = None
    last_duration_ms: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


class SchedulerJobUpdate(BaseModel):
    cron_expr: str | None = None
    enabled: bool | None = None


class JobExecutionResponse(BaseModel):
    id: int
    job_id: str
    status: str
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    result_summary: str | None = None
    error_message: str | None = None


class JobRunResponse(BaseModel):
    job: str
    started_at: str
    finished_at: str
    result: dict | None = None
    execution_id: int
