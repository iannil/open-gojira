"""Pipeline manager — orchestrates pipeline registration, execution, and querying."""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime
from typing import Type

from sqlalchemy.orm import Session

from app.core.datetime_utils import utcnow
from app.core.events import bus, DataSyncCompleted
from app.models.pipeline import PipelineRun
from app.services.pipelines.base import BasePipeline, PipelineStatus
from app.services.pipelines.dead_letter import DeadLetterQueue
from app.services.pipelines.metrics import MetricsCollector

logger = logging.getLogger(__name__)

_pipeline_registry: dict[str, Type[BasePipeline]] = {}
_cancelled_runs: set[str] = set()
_cancelled_runs_lock = threading.Lock()


# S3.5 — maps pipeline_type → data_freshness category. Pipelines not listed
# here (e.g. universe_bootstrap) do not update data_freshness. Categories
# must match the strings asserted by plan_runner's freshness gate.
_PIPELINE_FRESHNESS_CATEGORY: dict[str, str] = {
    "valuations": "valuation",
    "valuation": "valuation",  # alias for safety
    "klines": "kline",
    "kline": "kline",  # alias for safety
    "financials": "financial",
    "dividends": "dividend",
}


def _get_cancelled() -> frozenset[str]:
    """Thread-safe snapshot of cancelled run IDs."""
    with _cancelled_runs_lock:
        return frozenset(_cancelled_runs)


def register_pipeline(pipeline_cls: Type[BasePipeline]) -> Type[BasePipeline]:
    """Decorator to register a pipeline class by its pipeline_type."""
    _pipeline_registry[pipeline_cls.pipeline_type] = pipeline_cls
    return pipeline_cls


def get_registered_pipelines() -> dict[str, Type[BasePipeline]]:
    return dict(_pipeline_registry)


class PipelineManager:
    """Central orchestrator for pipeline operations."""

    def __init__(self, db: Session):
        self.db = db

    def start(
        self,
        pipeline_type: str,
        stock_codes: list[str] | None = None,
        force_full: bool = False,
        years: int = 5,
        background: bool = True,
    ) -> dict:
        """Start a pipeline run. Returns run metadata immediately."""
        cls = _pipeline_registry.get(pipeline_type)
        if not cls:
            raise ValueError(f"Unknown pipeline type: {pipeline_type}")

        if stock_codes is None:
            from app.services.data_management_service import get_watched_stock_codes
            from app.models.stock import Stock
            watched = get_watched_stock_codes(self.db)
            existing = {r[0] for r in self.db.query(Stock.code).filter(Stock.code.in_(watched)).all()}
            stock_codes = list(existing)

        if not stock_codes:
            # universe_bootstrap works with empty list (fetches all from API)
            if pipeline_type != "universe_bootstrap":
                raise ValueError("No stocks to sync")

        run_id = str(uuid.uuid4())[:8]
        config = json.dumps({
            "stock_codes": stock_codes,
            "force_full": force_full,
            "years": years,
        })

        run = PipelineRun(
            id=run_id,
            pipeline_type=pipeline_type,
            status=PipelineStatus.PENDING.value,
            config=config,
            total_items=len(stock_codes),
        )
        self.db.add(run)
        self.db.commit()

        if background:
            thread = threading.Thread(
                target=self._run_in_thread,
                args=(run_id, pipeline_type, stock_codes, force_full, years),
                daemon=True,
            )
            thread.start()
        else:
            self._execute(run_id, pipeline_type, stock_codes, force_full, years)

        return {
            "run_id": run_id,
            "pipeline_type": pipeline_type,
            "stock_count": len(stock_codes),
            "status": PipelineStatus.PENDING.value,
        }

    def _run_in_thread(
        self,
        run_id: str,
        pipeline_type: str,
        stock_codes: list[str],
        force_full: bool,
        years: int,
    ) -> None:
        """Background thread entry — owns its own DB session."""
        from app.db.session import SessionLocal
        with SessionLocal() as db:
            self._execute_with_db(db, run_id, pipeline_type, stock_codes, force_full, years)

    def _execute(
        self,
        run_id: str,
        pipeline_type: str,
        stock_codes: list[str],
        force_full: bool,
        years: int,
    ) -> None:
        self._execute_with_db(self.db, run_id, pipeline_type, stock_codes, force_full, years)

    def _execute_with_db(
        self,
        db: Session,
        run_id: str,
        pipeline_type: str,
        stock_codes: list[str],
        force_full: bool,
        years: int,
    ) -> None:
        cls = _pipeline_registry[pipeline_type]
        pipeline = cls(db, run_id=run_id, cancel_check=lambda: run_id in _get_cancelled())

        run = db.get(PipelineRun, run_id)
        if not run:
            return

        if run.status == PipelineStatus.CANCELLED.value:
            with _cancelled_runs_lock:
                _cancelled_runs.discard(run_id)
            return

        run.status = PipelineStatus.RUNNING.value
        run.started_at = utcnow()
        db.commit()

        try:
            result = pipeline.execute(stock_codes, force_full=force_full, years=years)

            run.status = result.status.value
            run.completed_items = result.completed_items
            run.failed_items = result.failed_items
            run.finished_at = utcnow()
            run.summary = json.dumps(result.summary, default=str)

            for sr in result.stock_results:
                if not sr.success and sr.error_type:
                    DeadLetterQueue.push(
                        db,
                        pipeline_run_id=run_id,
                        pipeline_type=pipeline_type,
                        stock_code=sr.stock_code,
                        error_type=sr.error_type,
                        error_message=sr.error or "Unknown error",
                    )

        except Exception as e:
            logger.exception("Pipeline %s run %s failed", pipeline_type, run_id)
            db.rollback()
            run.status = PipelineStatus.FAILED.value
            run.finished_at = utcnow()
            run.summary = json.dumps({"error": str(e)})

        try:
            db.commit()
        except Exception:
            db.rollback()
            db.commit()

        # S3.5 — update data_freshness table so plan_runner can gate on it.
        # Map pipeline_type → data_freshness category. Some pipelines (e.g.
        # universe_bootstrap) don't have a direct category and are skipped.
        try:
            from app.services.scheduler_alerting import record_pipeline_completion

            freshness_category = _PIPELINE_FRESHNESS_CATEGORY.get(pipeline_type)
            if freshness_category is not None:
                succeeded = run.status in (
                    PipelineStatus.COMPLETED.value,
                    PipelineStatus.COMPLETED_WITH_ERRORS.value,
                )
                record_pipeline_completion(
                    db,
                    freshness_category,
                    success=succeeded,
                    record_count=(
                        result.completed_items if result else 0
                    ) if succeeded else None,
                    error=(
                        None if succeeded
                        else f"pipeline status={run.status}"
                    ),
                )
                db.commit()
        except Exception:
            logger.exception(
                "Failed to record pipeline freshness for %s run %s",
                pipeline_type, run_id,
            )

        # Emit event for downstream handlers
        try:
            bus.emit(DataSyncCompleted(
                pipeline_type=pipeline_type,
                stock_codes=stock_codes,
                run_id=run_id,
                status=run.status,
                completed_items=result.completed_items if result else 0,
                failed_items=result.failed_items if result else 0,
            ))
        except Exception:
            logger.exception("EventBus emit DataSyncCompleted failed for run %s", run_id)

    def get_run(self, run_id: str) -> dict | None:
        run = self.db.get(PipelineRun, run_id)
        if not run:
            return None
        return self._run_to_dict(run)

    def list_runs(
        self,
        pipeline_type: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        q = self.db.query(PipelineRun)
        if pipeline_type:
            q = q.filter(PipelineRun.pipeline_type == pipeline_type)
        if status:
            q = q.filter(PipelineRun.status == status)
        q = q.order_by(PipelineRun.created_at.desc()).limit(limit)
        return [self._run_to_dict(r) for r in q.all()]

    def retry_failed(self, run_id: str) -> dict | None:
        """Retry all failed items from a specific run."""
        run = self.db.get(PipelineRun, run_id)
        if not run:
            return None

        summary = json.loads(run.summary) if run.summary else {}
        failed_codes = summary.get("failed_codes", [])
        if not failed_codes:
            return {"message": "No failed items to retry", "run_id": run_id}

        config = json.loads(run.config) if run.config else {}
        return self.start(
            pipeline_type=run.pipeline_type,
            stock_codes=failed_codes,
            force_full=config.get("force_full", False),
            years=config.get("years", 5),
        )

    def cancel(self, run_id: str) -> None:
        run = self.db.get(PipelineRun, run_id)
        if not run:
            raise ValueError(f"Pipeline run {run_id} not found")
        if run.status not in (PipelineStatus.PENDING.value, PipelineStatus.RUNNING.value):
            raise ValueError(f"Cannot cancel run in status '{run.status}'")
        run.status = PipelineStatus.CANCELLED.value
        self.db.commit()
        with _cancelled_runs_lock:
            _cancelled_runs.add(run_id)

    @staticmethod
    def recover_stale_runs(db: Session) -> int:
        """Mark stale running/pending runs as failed (server restarted mid-execution).

        Only marks runs older than 10 minutes to avoid mislabeling freshly created runs.
        """
        from datetime import timedelta
        stale_threshold = utcnow() - timedelta(minutes=10)
        stale_statuses = (PipelineStatus.RUNNING.value, PipelineStatus.PENDING.value)
        stale = db.query(PipelineRun).filter(
            PipelineRun.status.in_(stale_statuses),
            PipelineRun.created_at < stale_threshold,
        ).all()
        count = len(stale)
        for run in stale:
            run.status = PipelineStatus.FAILED.value
            if not run.finished_at:
                run.finished_at = utcnow()
            logger.warning("Recovered stale run %s (was %s)", run.id, run.status)
        if count:
            db.commit()
        return count

    def get_health(self) -> dict:
        """Get data health overview across all data types."""
        from sqlalchemy import func as sa_func
        from app.models.dividend import DividendRecord
        from app.models.financial import FinancialStatement
        from app.models.price_kline import PriceKline
        from app.models.valuation import ValuationSnapshot

        today = utcnow().date()
        result = {}

        for dtype, model, date_col in [
            ("valuations", ValuationSnapshot, ValuationSnapshot.date),
            ("klines", PriceKline, PriceKline.date),
            ("financials", FinancialStatement, FinancialStatement.report_date),
            ("dividends", DividendRecord, DividendRecord.ex_date),
        ]:
            row = self.db.query(
                sa_func.count(model.id).label("records"),
                sa_func.count(sa_func.distinct(model.stock_code)).label("stocks"),
                sa_func.max(date_col).label("latest"),
            ).first()

            latest = row.latest if row else None
            fresh = False
            if latest:
                # Normalize to date for comparison (FinancialStatement.report_date is DateTime)
                latest_date = latest.date() if isinstance(latest, datetime) else latest
                if dtype in ("valuations", "klines"):
                    fresh = (today - latest_date).days <= 1
                elif dtype == "financials":
                    fresh = (today - latest_date).days <= 90
                elif dtype == "dividends":
                    fresh = (today - latest_date).days <= 365

            result[dtype] = {
                "records": row.records or 0 if row else 0,
                "stocks": row.stocks or 0 if row else 0,
                "latest_date": str(latest.date() if isinstance(latest, datetime) else latest) if latest else None,
                "fresh": fresh,
            }

        return result

    def get_api_usage(self) -> dict:
        today = utcnow().date()
        return {
            "today": MetricsCollector.get_daily_summary(self.db, today),
            "month": MetricsCollector.get_monthly_summary(self.db),
            "trend": MetricsCollector.get_trend(self.db, 30),
        }

    @staticmethod
    def _run_to_dict(run: PipelineRun) -> dict:
        return {
            "run_id": run.id,
            "pipeline_type": run.pipeline_type,
            "status": run.status,
            "config": json.loads(run.config) if run.config else None,
            "total_items": run.total_items,
            "completed_items": run.completed_items,
            "failed_items": run.failed_items,
            "progress": int(
                (run.completed_items + run.failed_items) / max(1, run.total_items) * 100
            ),
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "summary": json.loads(run.summary) if run.summary else None,
            "created_at": run.created_at.isoformat() if run.created_at else None,
        }
