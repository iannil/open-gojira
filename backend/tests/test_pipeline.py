"""Tests for the pipeline engine — models, checkpoint, throttler, dead letter, metrics."""

import json
import time
from datetime import date, datetime

import pytest

# Import pipeline modules to trigger @register_pipeline decorators
import app.services.pipelines.valuation_pipeline  # noqa: F401
import app.services.pipelines.kline_pipeline  # noqa: F401
import app.services.pipelines.financial_pipeline  # noqa: F401
import app.services.pipelines.dividend_pipeline  # noqa: F401

from tests.conftest import TestSessionLocal


@pytest.fixture
def db():
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()

import pytest
from sqlalchemy.orm import Session

from app.models.pipeline import ApiUsageLog, DeadLetterRecord, PipelineCheckpoint, PipelineRun
from app.services.pipelines.base import BasePipeline, ErrorType, PipelineContext, PipelineResult, PipelineStatus
from app.services.pipelines.checkpoint import CheckpointManager
from app.services.pipelines.dead_letter import DeadLetterQueue
from app.services.pipelines.manager import PipelineManager, get_registered_pipelines
from app.services.pipelines.metrics import MetricsCollector
from app.services.pipelines.throttler import AdaptiveThrottler


class TestPipelineModels:
    def test_pipeline_run_create(self, db: Session):
        run = PipelineRun(
            id="test1234",
            pipeline_type="valuations",
            status="pending",
            total_items=10,
        )
        db.add(run)
        db.commit()
        found = db.get(PipelineRun, "test1234")
        assert found is not None
        assert found.pipeline_type == "valuations"
        assert found.total_items == 10

    def test_pipeline_checkpoint_unique(self, db: Session):
        # Use CheckpointManager which handles upsert correctly
        CheckpointManager.save(db, "klines", "000001", date(2026, 1, 1))
        CheckpointManager.save(db, "klines", "000001", date(2026, 6, 1))

        all_cps = db.query(PipelineCheckpoint).filter(
            PipelineCheckpoint.pipeline_type == "klines",
            PipelineCheckpoint.stock_code == "000001",
        ).all()
        assert len(all_cps) == 1
        assert all_cps[0].last_sync_date == date(2026, 6, 1)

    def test_dead_letter_record(self, db: Session):
        r = DeadLetterRecord(
            pipeline_run_id="r1",
            pipeline_type="financials",
            stock_code="600519",
            error_type="transient",
            error_message="timeout",
        )
        db.add(r)
        db.commit()
        assert db.query(DeadLetterRecord).count() == 1

    def test_api_usage_log(self, db: Session):
        log = ApiUsageLog(
            endpoint="/cn/company/fundamental/non_financial",
            stock_code="000001",
            duration_ms=150,
            cached=0,
        )
        db.add(log)
        db.commit()
        assert db.query(ApiUsageLog).count() == 1


class TestCheckpointManager:
    def test_get_nonexistent(self, db: Session):
        assert CheckpointManager.get(db, "klines", "999999") is None
        assert CheckpointManager.get_last_date(db, "klines", "999999") is None

    def test_save_and_get(self, db: Session):
        CheckpointManager.save(db, "klines", "000001", date(2026, 6, 1))
        cp = CheckpointManager.get(db, "klines", "000001")
        assert cp is not None
        assert cp.last_sync_date == date(2026, 6, 1)

    def test_save_updates(self, db: Session):
        CheckpointManager.save(db, "klines", "000002", date(2026, 1, 1))
        CheckpointManager.save(db, "klines", "000002", date(2026, 6, 1))
        assert CheckpointManager.get_last_date(db, "klines", "000002") == date(2026, 6, 1)

    def test_get_pending_codes(self, db: Session):
        CheckpointManager.save(db, "klines", "000001", date(2026, 6, 1))
        pending = CheckpointManager.get_pending_codes(db, "klines", ["000001", "000002"])
        assert pending == ["000002"]

    def test_reset(self, db: Session):
        CheckpointManager.save(db, "klines", "000003", date(2026, 6, 1))
        CheckpointManager.save(db, "klines", "000004", date(2026, 6, 1))
        count = CheckpointManager.reset(db, "klines")
        assert count == 2


class TestDeadLetterQueue:
    def test_push_and_get(self, db: Session):
        DeadLetterQueue.push(
            db, "run1", "financials", "600519",
            ErrorType.TRANSIENT, "timeout",
        )
        pending = DeadLetterQueue.get_pending(db)
        assert len(pending) == 1
        assert pending[0].stock_code == "600519"

    def test_mark_resolved(self, db: Session):
        r = DeadLetterQueue.push(
            db, "run2", "klines", "000001",
            ErrorType.PERMANENT, "invalid code",
        )
        DeadLetterQueue.mark_resolved(db, r.id)
        assert DeadLetterQueue.get_pending(db) == []

    def test_get_stats(self, db: Session):
        DeadLetterQueue.push(db, "run3", "klines", "000001", ErrorType.TRANSIENT, "err")
        stats = DeadLetterQueue.get_stats(db)
        assert stats["total"] >= 1
        assert stats["pending"] >= 1

    def test_exhausted_after_max_retries(self, db: Session):
        r = DeadLetterQueue.push(
            db, "run4", "klines", "000002",
            ErrorType.TRANSIENT, "err", max_retries=1,
        )
        DeadLetterQueue.mark_retry_attempt(db, r, success=False)
        db.refresh(r)
        assert r.status == "exhausted"


class TestMetricsCollector:
    def test_record_and_daily_summary(self, db: Session):
        MetricsCollector.record(db, "/test/ep1", duration_ms=100, cached=True)
        MetricsCollector.record(db, "/test/ep1", duration_ms=200, cached=False)
        MetricsCollector.record(db, "/test/ep2", duration_ms=50, error="fail")

        # called_at uses server_default=func.now() which may differ from date.today()
        # in UTC offset environments, so read the actual date from the DB.
        from app.models.pipeline import ApiUsageLog
        row = db.query(ApiUsageLog).first()
        actual_date = row.called_at.date() if row else date.today()

        summary = MetricsCollector.get_daily_summary(db, actual_date)
        assert summary["total_calls"] >= 3
        assert summary["total_cached_hits"] >= 1
        assert summary["total_errors"] >= 1

    def test_monthly_summary(self, db: Session):
        MetricsCollector.record(db, "/test/ep", duration_ms=100)
        summary = MetricsCollector.get_monthly_summary(db)
        assert summary["total_calls"] >= 1

    def test_trend(self, db: Session):
        MetricsCollector.record(db, "/test/ep", duration_ms=100)
        trend = MetricsCollector.get_trend(db, 7)
        assert len(trend) >= 1


class TestAdaptiveThrottler:
    def test_normal_interval(self):
        t = AdaptiveThrottler(min_interval=0.01, max_interval=0.05, budget=10000)
        wait = t.acquire()
        assert wait >= 0.01

    def test_backoff_on_errors(self):
        t = AdaptiveThrottler(min_interval=0.01, max_interval=0.1, budget=10000, error_threshold=0.0)
        t.record_error()
        wait = t.acquire()
        # Should use max_interval due to error rate
        assert wait >= 0.1

    def test_stats(self):
        t = AdaptiveThrottler(budget=100)
        t.acquire()
        assert t.stats["total_calls"] == 1


class TestBasePipelineThrottlerWireUp:
    """F4 wire-up regression: BasePipeline.execute must call acquire() per
    stock and record_error() on failure. Without this, full-speed concurrency
    trips the Lixinger circuit breaker (threshold=5) after a handful of 429s,
    silently fast-failing the entire pipeline run."""

    def _make_pipeline(self, db, throttler=None, fail_codes=None):
        from unittest.mock import MagicMock

        fail_codes = fail_codes or set()

        class _TestPipeline(BasePipeline):
            pipeline_type = "test"

            def extract(self, code, ctx):
                return [{"code": code}]

            def transform(self, code, raw, ctx):
                return raw

            def validate(self, code, data, ctx):
                return data

            def load(self, code, data, ctx):
                if code in fail_codes:
                    raise RuntimeError(f"injected failure for {code}")
                return len(data)

            def verify(self, code, ctx):
                return True

        return _TestPipeline(db, throttler=throttler)

    def test_acquire_called_per_stock(self, db):
        from unittest.mock import MagicMock

        mock = MagicMock(spec=AdaptiveThrottler)
        mock.acquire.return_value = 0.0
        p = self._make_pipeline(db, throttler=mock)
        p.execute(["000001", "000002", "000003"])
        assert mock.acquire.call_count == 3

    def test_record_error_on_failure(self, db):
        from unittest.mock import MagicMock

        mock = MagicMock(spec=AdaptiveThrottler)
        mock.acquire.return_value = 0.0
        p = self._make_pipeline(db, throttler=mock, fail_codes={"000002"})
        result = p.execute(["000001", "000002", "000003"])
        assert mock.record_error.call_count == 1
        assert result.failed_items == 1
        assert result.completed_items == 2

    def test_default_throttler_when_none_passed(self, db):
        p = self._make_pipeline(db, throttler=None)
        assert isinstance(p._throttler, AdaptiveThrottler)


class TestPipelineRegistry:
    def test_all_types_registered(self):
        registered = get_registered_pipelines()
        assert set(registered.keys()) == {"valuations", "klines", "financials", "dividends", "universe_bootstrap"}


class TestPipelineManager:
    def test_list_runs_empty(self, db: Session):
        mgr = PipelineManager(db)
        runs = mgr.list_runs()
        assert runs == []

    def test_get_run_not_found(self, db: Session):
        mgr = PipelineManager(db)
        assert mgr.get_run("nonexistent") is None

    def test_get_health(self, db: Session):
        mgr = PipelineManager(db)
        health = mgr.get_health()
        assert "valuations" in health
        assert "klines" in health
        assert "financials" in health
        assert "dividends" in health

    def test_invalid_pipeline_type(self, db: Session):
        mgr = PipelineManager(db)
        with pytest.raises(ValueError, match="Unknown pipeline type"):
            mgr.start("invalid_type")

    def test_no_stocks_to_sync(self, db: Session):
        mgr = PipelineManager(db)
        with pytest.raises(ValueError, match="No stocks to sync"):
            mgr.start("valuations", stock_codes=[])

    def test_start_records_granularity_in_config(self, db: Session):
        """Granularity arg (financials quarterly) is persisted to PipelineRun.config."""
        from app.models.pipeline import PipelineRun
        mgr = PipelineManager(db)
        result = mgr.start(
            "financials",
            stock_codes=["600519"],
            granularity="q",
            background=False,
        )
        run = db.query(PipelineRun).filter(PipelineRun.id == result["run_id"]).first()
        config = json.loads(run.config)
        assert config["granularity"] == "q"

    def test_start_default_granularity_is_none(self, db: Session):
        """When granularity not passed, config records null (financials defaults to 'y' in pipeline.extract)."""
        from app.models.pipeline import PipelineRun
        mgr = PipelineManager(db)
        result = mgr.start("financials", stock_codes=["600519"], background=False)
        run = db.query(PipelineRun).filter(PipelineRun.id == result["run_id"]).first()
        config = json.loads(run.config)
        assert config["granularity"] is None


class TestBasePipeline:
    def test_classify_transient_error(self):
        import httpx

        class TestPipeline(BasePipeline):
            pipeline_type = "test"

            def extract(self, stock_code, ctx): return []
            def transform(self, stock_code, raw, ctx): return raw
            def validate(self, stock_code, data, ctx): return data
            def load(self, stock_code, data, ctx): return 0

        p = TestPipeline(None)
        assert p._classify_error(httpx.TimeoutException("timeout")) == ErrorType.TRANSIENT
        assert p._classify_error(httpx.NetworkError("conn")) == ErrorType.TRANSIENT

    def test_classify_permanent_error(self):
        import httpx

        class TestPipeline(BasePipeline):
            pipeline_type = "test"

            def extract(self, stock_code, ctx): return []
            def transform(self, stock_code, raw, ctx): return raw
            def validate(self, stock_code, data, ctx): return data
            def load(self, stock_code, data, ctx): return 0

        p = TestPipeline(None)
        resp = httpx.Response(401)
        err = httpx.HTTPStatusError("unauthorized", request=httpx.Request("POST", "http://x"), response=resp)
        assert p._classify_error(err) == ErrorType.PERMANENT
