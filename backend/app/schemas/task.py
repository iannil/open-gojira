"""Pydantic schemas for the unified Task abstraction layer."""

from datetime import datetime

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    """Payload for creating or registering a Task definition."""
    task_id: str = Field(..., max_length=128, description="Unique identifier")
    type: str = Field("job", max_length=32)
    trigger_type: str = Field("cron", max_length=16)
    cron_expr: str | None = None
    event_source: str | None = None
    depends_on: list[str] | None = None
    retry_config: dict | None = None
    timeout_seconds: int | None = 300
    mutex_enabled: bool = True
    enabled: bool = True
    tags: list[str] | None = None
    description: str | None = None


class TaskUpdate(BaseModel):
    """Payload for updating an existing Task."""
    cron_expr: str | None = None
    enabled: bool | None = None
    timeout_seconds: int | None = None
    retry_config: dict | None = None
    description: str | None = None


class TaskResponse(BaseModel):
    """Full Task definition returned to the client."""
    task_id: str
    type: str
    status: str
    trigger_type: str
    cron_expr: str | None = None
    event_source: str | None = None
    depends_on: list[str] | None = None
    retry_config: dict | None = None
    timeout_seconds: int | None = None
    mutex_enabled: bool
    enabled: bool
    tags: list[str] | None = None
    description: str | None = None
    next_run_time: str | None = None
    last_run_at: str | None = None
    last_run_status: str | None = None
    last_duration_ms: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


class TaskRunResponse(BaseModel):
    """A single execution instance of a Task."""
    id: int
    task_id: str
    status: str
    progress: float = 0.0
    progress_message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    retry_count: int = 0
    max_retries: int = 0
    last_error: str | None = None
    result_summary: str | None = None
    worker_id: str | None = None
    triggered_by: str = "cron"
    trace_id: str | None = None
    created_at: str | None = None


class TaskRunLogResponse(BaseModel):
    """A single log entry for a TaskRun execution."""
    id: int
    run_id: int
    timestamp: str
    level: str
    message: str
    progress: float | None = None


class TaskRunDetailResponse(TaskRunResponse):
    """Extended TaskRun with link to parent Task definition."""
    task: TaskResponse | None = None
    log_count: int = 0


class TaskHealthResponse(BaseModel):
    """Health/status summary for the task scheduling subsystem."""
    engine_running: bool
    running_tasks: int
    queued_tasks: int
    failed_tasks_24h: int
    workers_active: int
    uptime_seconds: int | None = None


class TriggerTaskResponse(BaseModel):
    """Response after manually triggering a Task."""
    task_id: str
    run_id: int
    status: str
    message: str = "Task triggered"
