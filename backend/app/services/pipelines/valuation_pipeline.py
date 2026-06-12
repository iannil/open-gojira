"""Valuation pipeline — batch-sync valuation snapshots from Lixinger."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any


from app.core.datetime_utils import utcnow
from app.models.valuation import ValuationSnapshot
from app.services.pipelines.base import BasePipeline, PipelineContext
from app.services.pipelines.manager import register_pipeline

logger = logging.getLogger(__name__)


def _extract_pct(raw) -> float | None:
    if raw is None:
        return None
    val = raw.get("cvpos") if isinstance(raw, dict) else raw
    if val is None:
        return None
    val = float(val)
    return val * 100.0 if val <= 1.0 else val


@register_pipeline
class ValuationPipeline(BasePipeline):
    """Sync valuation snapshots for a list of stocks.

    Valuations are batched (up to 100 stocks per API call). Each batch
    is processed as a unit: extract -> transform -> validate -> load -> verify.
    """

    pipeline_type = "valuations"
    BATCH_SIZE = 100

    def execute(self, stock_codes: list[str], **kwargs) -> Any:
        from app.services.pipelines.base import PipelineResult, PipelineStatus

        ctx = PipelineContext(
            run_id=self.run_id,
            pipeline_type=self.pipeline_type,
            stock_codes=stock_codes,
            started_at=utcnow(),
        )
        result = PipelineResult(
            run_id=self.run_id,
            pipeline_type=self.pipeline_type,
            status=PipelineStatus.RUNNING,
            total_items=len(stock_codes),
        )

        self._on_start(ctx)

        # Process in batches — each batch yields results for multiple stocks
        for start in range(0, len(stock_codes), self.BATCH_SIZE):
            batch = stock_codes[start : start + self.BATCH_SIZE]
            batch_results = self._process_batch(batch, ctx)
            for sr in batch_results:
                result.stock_results.append(sr)
                if sr.success:
                    result.completed_items += 1
                else:
                    result.failed_items += 1

        ctx.finished_at = utcnow()

        if result.failed_items == 0:
            result.status = PipelineStatus.COMPLETED
        elif result.completed_items > 0:
            result.status = PipelineStatus.COMPLETED_WITH_ERRORS
        else:
            result.status = PipelineStatus.FAILED

        result.summary = self._build_summary(result, ctx)
        self._on_finish(result, ctx)
        return result

    def _process_batch(self, batch: list[str], ctx: PipelineContext) -> list:
        from app.services.pipelines.base import StockResult

        try:
            raw = self.extract_batch(batch, ctx)
            transformed = self.transform_batch(batch, raw, ctx)
            valid = self.validate_batch(batch, transformed, ctx)
            self.load_batch(batch, valid, ctx)
        except Exception as e:
            self._logger.warning("Valuation batch failed for %s..%s: %s", batch[0], batch[-1], e)
            self.db.rollback()
            return [
                StockResult(stock_code=code, success=False, error=str(e))
                for code in batch
            ]

        return [
            StockResult(stock_code=code, success=True, records_affected=1)
            for code in batch
        ]

    def extract(self, stock_code: str, ctx: PipelineContext) -> Any:
        # Valuations use batch mode; single-stock extract is not used directly
        pass

    def extract_batch(self, batch: list[str], ctx: PipelineContext) -> list[dict]:
        from app.services.lixinger_client import get_lixinger_client
        client = get_lixinger_client()
        return client.get_fundamentals(
            stock_codes=batch,
            metrics=["pe_ttm", "pb", "dyr", "sp", "pe_ttm.y10.cvpos", "pb.y10.cvpos"],
        )

    def transform(self, stock_code: str, raw: Any, ctx: PipelineContext) -> Any:
        pass

    def transform_batch(self, batch: list[str], raw: list[dict], ctx: PipelineContext) -> dict[str, dict]:
        result = {}
        for item in raw:
            code = item.get("stockCode")
            if code:
                result[code] = {
                    "pe_ttm": item.get("pe_ttm"),
                    "pb": item.get("pb"),
                    "pe_percentile_10y": _extract_pct(item.get("pe_ttm.y10.cvpos")),
                    "pb_percentile_10y": _extract_pct(item.get("pb.y10.cvpos")),
                    "dividend_yield": item.get("dyr"),
                }
        return result

    def validate(self, stock_code: str, data: Any, ctx: PipelineContext) -> Any:
        pass

    def validate_batch(self, batch: list[str], data: dict[str, dict], ctx: PipelineContext) -> dict[str, dict]:
        """S3.5 — apply data_sanity rules before persisting.

        Records that fail sanity are dropped from the batch. High violation
        rate also emits a warning system_alert so the operator can
        investigate upstream API drift.
        """
        from app.services.data_sanity_service import (
            alert_on_high_violation_rate,
            validate_record,
        )

        valid: dict[str, dict] = {}
        invalid_entries: list[dict] = []
        for code in batch:
            d = data.get(code)
            if d is None:
                continue
            # Map transformed keys back to canonical Lixinger names that
            # data_sanity_service.SANITY_RULES expects (pe_ttm / pb / dyr / sp).
            probe = {
                "pe_ttm": d.get("pe_ttm"),
                "pb": d.get("pb"),
                "dyr": d.get("dividend_yield"),
            }
            violations = validate_record(probe)
            if violations:
                invalid_entries.append({
                    "record": probe, "id": code, "violations": violations,
                })
            else:
                valid[code] = d

        if invalid_entries:
            self._logger.warning(
                "Valuation batch sanity: %d/%d records rejected",
                len(invalid_entries), len(batch),
            )
            try:
                alert_on_high_violation_rate(
                    self.db, invalid_entries, len(batch),
                )
            except Exception:
                self._logger.exception(
                    "alert_on_high_violation_rate failed (non-fatal)",
                )

        return valid

    def load(self, stock_code: str, data: Any, ctx: PipelineContext) -> int:
        pass

    def load_batch(self, batch: list[str], data: dict[str, dict], ctx: PipelineContext) -> int:
        today = date.today()
        upserted = 0
        for code in batch:
            d = data.get(code)
            if d is None:
                continue
            existing = (
                self.db.query(ValuationSnapshot)
                .filter(ValuationSnapshot.stock_code == code, ValuationSnapshot.date == today)
                .first()
            )
            if existing:
                existing.pe_ttm = d["pe_ttm"]
                existing.pb = d["pb"]
                existing.pe_percentile_10y = d["pe_percentile_10y"]
                existing.pb_percentile_10y = d["pb_percentile_10y"]
                existing.dividend_yield = d["dividend_yield"]
            else:
                self.db.add(ValuationSnapshot(
                    stock_code=code,
                    date=today,
                    pe_ttm=d["pe_ttm"],
                    pb=d["pb"],
                    pe_percentile_10y=d["pe_percentile_10y"],
                    pb_percentile_10y=d["pb_percentile_10y"],
                    dividend_yield=d["dividend_yield"],
                ))
                upserted += 1
        self.db.commit()
        return upserted

    def verify(self, stock_code: str, ctx: PipelineContext) -> bool:
        today = date.today()
        return (
            self.db.query(ValuationSnapshot)
            .filter(ValuationSnapshot.stock_code == stock_code, ValuationSnapshot.date == today)
            .first()
            is not None
        )
