"""K-line pipeline — incremental daily candlestick sync from Lixinger."""

from __future__ import annotations

import logging
from datetime import date, timedelta


from app.models.price_kline import PriceKline
from app.services.pipelines.base import BasePipeline, PipelineContext
from app.services.pipelines.checkpoint import CheckpointManager
from app.services.pipelines.manager import register_pipeline

logger = logging.getLogger(__name__)


def _parse_lx_date(raw) -> date | None:
    if not raw:
        return None
    s = str(raw)[:10]
    try:
        y, m, d = s.split("-")
        return date(int(y), int(m), int(d))
    except (ValueError, IndexError):
        return None


@register_pipeline
class KlinePipeline(BasePipeline):
    """Incremental K-line sync driven by checkpoints.

    For each stock: check checkpoint for last sync date, fetch only the
    gap from last_sync_date to today, upsert into price_klines.
    """

    pipeline_type = "klines"

    def extract(self, stock_code: str, ctx: PipelineContext) -> list[dict]:
        from app.services.lixinger_client import get_lixinger_client

        end = date.today()
        if ctx.force_full:
            start = end - timedelta(days=ctx.years * 365)
        else:
            last = CheckpointManager.get_last_date(self.db, self.pipeline_type, stock_code)
            if last:
                start = last - timedelta(days=5)
            else:
                start = end - timedelta(days=ctx.years * 365)

        client = get_lixinger_client()
        return client.get_kline(
            stock_code=stock_code,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )

    def transform(self, stock_code: str, raw: list[dict], ctx: PipelineContext) -> list[dict]:
        return [
            {
                "date": _parse_lx_date(item.get("date")),
                "open": item.get("open"),
                "high": item.get("high"),
                "low": item.get("low"),
                "close": item.get("close"),
                "volume": item.get("volume"),
                "turnover": item.get("amount") or item.get("turnover"),
            }
            for item in raw
        ]

    def validate(self, stock_code: str, data: list[dict], ctx: PipelineContext) -> list[dict]:
        valid = []
        for item in data:
            d = item.get("date")
            if not d:
                continue
            close = item.get("close")
            if close is not None and close <= 0:
                continue
            valid.append(item)
        return valid

    def load(self, stock_code: str, data: list[dict], ctx: PipelineContext) -> int:
        if not data:
            return 0

        dates_in_data = {item["date"] for item in data}
        existing_dates: set[date] = {
            d for (d,) in self.db.query(PriceKline.date)
            .filter(
                PriceKline.stock_code == stock_code,
                PriceKline.freq == "day",
                PriceKline.date.in_(dates_in_data),
            )
            .all()
        }

        inserted = 0
        latest_date = date(1970, 1, 1)
        for item in data:
            d = item["date"]
            if d in existing_dates:
                continue
            self.db.add(PriceKline(
                stock_code=stock_code,
                date=d,
                freq="day",
                open=item["open"],
                high=item["high"],
                low=item["low"],
                close=item["close"],
                volume=item["volume"],
                turnover=item["turnover"],
            ))
            inserted += 1
            if d > latest_date:
                latest_date = d

        if inserted:
            self.db.commit()
            CheckpointManager.save(self.db, self.pipeline_type, stock_code, latest_date)

        return inserted

    def verify(self, stock_code: str, ctx: PipelineContext) -> bool:
        latest = (
            self.db.query(PriceKline.date)
            .filter(PriceKline.stock_code == stock_code, PriceKline.freq == "day")
            .order_by(PriceKline.date.desc())
            .first()
        )
        if not latest:
            return False
        days_old = (date.today() - latest[0]).days
        return days_old <= 3
