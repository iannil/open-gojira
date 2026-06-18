"""Base pipeline abstraction — five-stage data sync framework."""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.core.datetime_utils import utcnow
from app.services.pipelines.throttler import AdaptiveThrottler

logger = logging.getLogger(__name__)


class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ErrorType(str, Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    DATA_ANOMALY = "data_anomaly"


@dataclass
class StockResult:
    stock_code: str
    success: bool
    records_affected: int = 0
    error: str | None = None
    error_type: ErrorType | None = None
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineContext:
    run_id: str
    pipeline_type: str
    stock_codes: list[str]
    force_full: bool = False
    years: int = 5
    started_at: datetime | None = None
    finished_at: datetime | None = None
    stock_results: list[StockResult] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    run_id: str
    pipeline_type: str
    status: PipelineStatus
    total_items: int = 0
    completed_items: int = 0
    failed_items: int = 0
    stock_results: list[StockResult] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def progress(self) -> int:
        if self.total_items == 0:
            return 0
        return int((self.completed_items + self.failed_items) / self.total_items * 100)


class BasePipeline(ABC):
    """Abstract five-stage pipeline for data synchronization.

    Stages: Extract -> Transform -> Validate -> Load -> Verify
    Each stage receives and returns structured data. Override the
    stage methods to implement data-type-specific logic.
    """

    pipeline_type: str = ""

    def __init__(
        self,
        db: Session,
        run_id: str | None = None,
        cancel_check: Any = None,
        throttler: AdaptiveThrottler | None = None,
    ):
        self.db = db
        self.run_id = run_id or str(uuid.uuid4())[:8]
        self._cancel_check = cancel_check
        self._throttler = throttler or AdaptiveThrottler()
        self._logger = logging.getLogger(f"pipeline.{self.pipeline_type}")

    def execute(self, stock_codes: list[str], **kwargs) -> PipelineResult:
        """Run the full pipeline for all stock codes."""
        ctx = PipelineContext(
            run_id=self.run_id,
            pipeline_type=self.pipeline_type,
            stock_codes=stock_codes,
            started_at=utcnow(),
            **kwargs,
        )
        result = PipelineResult(
            run_id=self.run_id,
            pipeline_type=self.pipeline_type,
            status=PipelineStatus.RUNNING,
            total_items=len(stock_codes),
        )

        self._logger.info(
            "pipeline_start run_id=%s type=%s stocks=%d",
            self.run_id, self.pipeline_type, len(stock_codes),
        )
        self._on_start(ctx)

        for code in stock_codes:
            if self._cancel_check and self._cancel_check():
                result.status = PipelineStatus.CANCELLED
                self._logger.info("Pipeline cancelled after %d items", result.completed_items + result.failed_items)
                break
            # F4 wire-up: throttle between stocks to avoid Lixinger 429.
            # Without this the loop fires at full CPU speed and the circuit
            # breaker (threshold=5) trips after just a few 429s.
            self._throttler.acquire()
            sr = self._process_single(code, ctx)
            if not sr.success:
                self._throttler.record_error()
            result.stock_results.append(sr)
            if sr.success:
                result.completed_items += 1
            else:
                result.failed_items += 1

        ctx.finished_at = utcnow()

        if result.status == PipelineStatus.CANCELLED:
            pass
        elif result.failed_items == 0:
            result.status = PipelineStatus.COMPLETED
        elif result.completed_items > 0:
            result.status = PipelineStatus.COMPLETED_WITH_ERRORS
        else:
            result.status = PipelineStatus.FAILED

        result.summary = self._build_summary(result, ctx)
        self._on_finish(result, ctx)
        return result

    def _process_single(self, stock_code: str, ctx: PipelineContext) -> StockResult:
        """Execute all five stages for a single stock."""
        try:
            raw = self.extract(stock_code, ctx)
            transformed = self.transform(stock_code, raw, ctx)
            valid = self.validate(stock_code, transformed, ctx)
            self.load(stock_code, valid, ctx)
            verify_ok = self.verify(stock_code, ctx)
            return StockResult(
                stock_code=stock_code,
                success=True,
                records_affected=len(valid) if isinstance(valid, list) else 1,
                detail={"verify_passed": verify_ok},
            )
        except Exception as e:
            self._logger.warning("Pipeline failed for %s: %s", stock_code, e)
            error_type = self._classify_error(e)
            return StockResult(
                stock_code=stock_code,
                success=False,
                error=str(e),
                error_type=error_type,
            )

    @abstractmethod
    def extract(self, stock_code: str, ctx: PipelineContext) -> Any:
        """Fetch raw data from Lixinger API."""

    @abstractmethod
    def transform(self, stock_code: str, raw: Any, ctx: PipelineContext) -> Any:
        """Normalize raw data into internal format."""

    @abstractmethod
    def validate(self, stock_code: str, data: Any, ctx: PipelineContext) -> Any:
        """Check data quality — filter out invalid records."""

    @abstractmethod
    def load(self, stock_code: str, data: Any, ctx: PipelineContext) -> int:
        """Persist data to database (upsert). Returns rows affected."""

    def verify(self, stock_code: str, ctx: PipelineContext) -> bool:
        """Post-load consistency check. Optional — default passes."""
        return True

    def _on_start(self, ctx: PipelineContext) -> None:
        """Hook called before processing starts."""

    def _on_finish(self, result: PipelineResult, ctx: PipelineContext) -> None:
        """Hook called after all stocks are processed."""

    def _classify_error(self, error: Exception) -> ErrorType:
        """Classify an error for retry decision."""
        import httpx

        if isinstance(error, (httpx.TimeoutException, httpx.NetworkError)):
            return ErrorType.TRANSIENT
        if isinstance(error, httpx.HTTPStatusError):
            if error.response.status_code in (429, 502, 503, 504):
                return ErrorType.TRANSIENT
            if error.response.status_code in (401, 403):
                return ErrorType.PERMANENT
        msg = str(error).lower()
        if any(kw in msg for kw in ("timeout", "connection", "network")):
            return ErrorType.TRANSIENT
        if any(kw in msg for kw in ("invalid", "not found", "unauthorized")):
            return ErrorType.PERMANENT
        return ErrorType.DATA_ANOMALY

    def _build_summary(self, result: PipelineResult, ctx: PipelineContext) -> dict:
        failed = [sr for sr in result.stock_results if not sr.success]
        return {
            "total": result.total_items,
            "completed": result.completed_items,
            "failed": result.failed_items,
            "failed_codes": [sr.stock_code for sr in failed],
            "failed_errors": {sr.stock_code: sr.error for sr in failed},
            "duration_seconds": (
                (ctx.finished_at - ctx.started_at).total_seconds()
                if ctx.started_at and ctx.finished_at
                else None
            ),
        }
