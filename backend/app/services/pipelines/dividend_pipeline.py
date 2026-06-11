"""Dividend pipeline — sync historical dividend records from Lixinger."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional


from app.models.dividend import DividendRecord
from app.services.pipelines.base import BasePipeline, PipelineContext
from app.services.pipelines.checkpoint import CheckpointManager
from app.services.pipelines.manager import register_pipeline

logger = logging.getLogger(__name__)


def _parse_lx_date(value) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                return None
    return None


@register_pipeline
class DividendPipeline(BasePipeline):
    """Sync historical dividend records from Lixinger.

    Fetches up to N years of dividend history per stock and upserts
    into the dividends table. Historical records use quantity_held=0.
    """

    pipeline_type = "dividends"

    def extract(self, stock_code: str, ctx: PipelineContext) -> list[dict]:
        from app.services.lixinger_client import get_lixinger_client

        years = ctx.extra.get("years", 10)
        start = (date.today() - timedelta(days=int(365.25 * years))).isoformat()

        client = get_lixinger_client()
        return client.get_dividend(stock_code=stock_code, start_date=start)

    def transform(self, stock_code: str, raw: list[dict], ctx: PipelineContext) -> list[dict]:
        results = []
        for row in raw:
            ex_date = _parse_lx_date(row.get("exDate")) or _parse_lx_date(row.get("date"))
            amount = row.get("dividend")
            if not ex_date or amount is None:
                continue
            results.append({
                "stock_code": stock_code,
                "ex_date": ex_date,
                "amount_per_share": float(amount),
                "quantity_held": 0,
                "total_received": 0.0,
                "reinvested": False,
            })
        return results

    def validate(self, stock_code: str, data: list[dict], ctx: PipelineContext) -> list[dict]:
        return [d for d in data if d.get("ex_date") and d.get("amount_per_share") is not None]

    def load(self, stock_code: str, data: list[dict], ctx: PipelineContext) -> int:
        if not data:
            return 0

        existing_dates: set[date] = {
            r.ex_date
            for r in self.db.query(DividendRecord.ex_date)
            .filter(
                DividendRecord.stock_code == stock_code,
                DividendRecord.quantity_held == 0,
            )
            .all()
            if r.ex_date
        }

        inserted = 0
        latest_date = date(1970, 1, 1)
        for item in data:
            ex_date = item["ex_date"]
            if ex_date in existing_dates:
                continue
            self.db.add(DividendRecord(**item))
            existing_dates.add(ex_date)
            inserted += 1
            if ex_date > latest_date:
                latest_date = ex_date

        if inserted:
            self.db.commit()
            CheckpointManager.save(self.db, self.pipeline_type, stock_code, latest_date)

        return inserted

    def verify(self, stock_code: str, ctx: PipelineContext) -> bool:
        latest = (
            self.db.query(DividendRecord.ex_date)
            .filter(DividendRecord.stock_code == stock_code)
            .order_by(DividendRecord.ex_date.desc())
            .first()
        )
        if not latest:
            return False
        days_old = (date.today() - latest[0]).days
        return days_old <= 400
