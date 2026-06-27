from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.datetime_utils import now
from app.db.base import Base


class Task(Base):
    """Task definition — represents a schedulable unit of work.

    Analogous to the former scheduler_jobs table but extended with
    dependency, retry, timeout, and event-trigger support.
    """

    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    type: Mapped[str] = mapped_column(String(32), default="job", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    trigger_type: Mapped[str] = mapped_column(
        String(16), default="cron", nullable=False
    )
    cron_expr: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    depends_on: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="JSON array of task_id's"
    )
    retry_config: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment='JSON: {"max_retries":3,"backoff":"exponential"}'
    )
    timeout_seconds: Mapped[int | None] = mapped_column(Integer, default=300)
    mutex_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tags: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="JSON array of tag strings"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now(), onupdate=func.now()
    )


class TaskRun(Base):
    """A single execution instance of a Task."""

    __tablename__ = "task_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String(128), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), default="queued", nullable=False, index=True
    )
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    progress_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    triggered_by: Mapped[str] = mapped_column(
        String(32), default="cron", nullable=False
    )
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_data: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="JSON serialized input parameters for this run"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now(), index=True
    )
