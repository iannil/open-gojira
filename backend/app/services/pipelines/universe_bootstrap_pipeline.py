"""Universe bootstrap pipeline — fetch and maintain the full A-share master list."""

from __future__ import annotations

import logging
from datetime import date as date_type
from typing import Any


from app.core.datetime_utils import utcnow
from app.models.stock import Stock
from app.services.pipelines.base import BasePipeline, PipelineContext, PipelineResult, PipelineStatus
from app.services.pipelines.manager import register_pipeline

logger = logging.getLogger(__name__)


def _parse_listed_date(raw) -> date_type | None:
    if not raw:
        return None
    s = str(raw)[:10]
    try:
        parts = s.split("-")
        return date_type(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return None


@register_pipeline
class UniverseBootstrapPipeline(BasePipeline):
    """Fetch the complete A-share stock list from Lixinger and upsert into stocks table.

    Unlike other pipelines that process per-stock data, this pipeline operates on
    the full company list as a single unit.
    """

    pipeline_type = "universe_bootstrap"

    def execute(self, stock_codes: list[str], **kwargs) -> PipelineResult:
        from app.services.pipelines.base import StockResult

        ctx = PipelineContext(
            run_id=self.run_id,
            pipeline_type=self.pipeline_type,
            stock_codes=[],
            started_at=utcnow(),
        )
        result = PipelineResult(
            run_id=self.run_id,
            pipeline_type=self.pipeline_type,
            status=PipelineStatus.RUNNING,
            total_items=1,
        )

        self._on_start(ctx)

        try:
            raw = self._fetch_all_companies()
            transformed = self._transform_companies(raw)
            stats = self._upsert_companies(transformed)
            self.db.commit()

            ctx.finished_at = utcnow()
            result.status = PipelineStatus.COMPLETED
            result.completed_items = 1
            result.stock_results.append(
                StockResult(stock_code="__universe__", success=True, detail=stats)
            )
            result.summary = {
                "total_fetched": stats["total_fetched"],
                "inserted": stats["inserted"],
                "updated": stats["updated"],
                "delisted": stats["delisted"],
                "reactivated": stats["reactivated"],
            }
        except Exception as e:
            self._logger.exception("Universe bootstrap failed: %s", e)
            ctx.finished_at = utcnow()
            result.status = PipelineStatus.FAILED
            result.failed_items = 1
            result.stock_results.append(
                StockResult(stock_code="__universe__", success=False, error=str(e))
            )

        self._on_finish(result, ctx)
        return result

    def _fetch_all_companies(self) -> list[dict]:
        from app.services.lixinger_client import get_lixinger_client

        client = get_lixinger_client()
        # get_company_list_all auto-paginates past Lixinger's silent 500-record
        # cap, returning the full ~5625-share universe. Replaces the manual
        # page loop previously inlined here (identical behaviour, less duplication).
        all_companies = client.get_company_list_all()
        self._logger.info("Fetched %d companies from Lixinger", len(all_companies))
        return all_companies

    def _transform_companies(self, raw: list[dict]) -> dict[str, dict]:
        result = {}
        for c in raw:
            code = c.get("stockCode", "").strip()
            if not code:
                continue
            name = c.get("name", "").strip()
            listed = _parse_listed_date(
                c.get("ipoDate") or c.get("listingDate") or c.get("listDate")
            )
            fs_type = c.get("fsTableType", "")
            result[code] = {
                "name": name,
                "listed_date": listed,
                "fs_type": fs_type,
                # S1.1 raw trading-status fields (stored verbatim for S2 derivation)
                "exchange": c.get("exchange"),
                "listing_status": c.get("listingStatus"),
                "fs_table_type": fs_type or None,
                "ipo_date": listed,  # ipoDate is the canonical source for both
            }
        return result

    def _upsert_companies(self, companies: dict[str, dict]) -> dict:
        now = utcnow()
        codes_in_response = set(companies.keys())

        existing_stocks = {
            s.code: s
            for s in self.db.query(Stock).all()
        }

        inserted = 0
        updated = 0
        delisted = 0
        reactivated = 0

        # Upsert: new stocks and name/industry changes
        for code, info in companies.items():
            name = info["name"] or code
            listed = info["listed_date"]

            existing = existing_stocks.get(code)
            fs_type = info.get("fs_type", "")
            exchange = info.get("exchange")
            listing_status = info.get("listing_status")
            fs_table_type = info.get("fs_table_type")
            ipo_date = info.get("ipo_date")
            if existing is None:
                self.db.add(Stock(
                    code=code,
                    name=name,
                    listed_date=listed,
                    # F20 (2026-06-18): stocks.industry currently stores Lixinger
                    # fsTableType (5 values), not real申万 industry. Lixinger /cn/company
                    # endpoint has no industry field; constituents endpoint returns 0.
                    # Field name kept as 'industry' for backward compatibility with
                    # existing strategy rules / holding_service industry cap. Will be
                    # migrated to real申万 industry when external data source is added.
                    industry=fs_type or None,
                    exchange=exchange,
                    listing_status=listing_status,
                    fs_table_type=fs_table_type,
                    ipo_date=ipo_date,
                    sync_source="bootstrap",
                ))
                inserted += 1
            else:
                changed = False
                if existing.name != name and name:
                    existing.name = name
                    changed = True
                if listed and existing.listed_date != listed:
                    existing.listed_date = listed
                    changed = True
                if fs_type and existing.industry != fs_type:
                    existing.industry = fs_type
                    changed = True
                if exchange and existing.exchange != exchange:
                    existing.exchange = exchange
                    changed = True
                if listing_status and existing.listing_status != listing_status:
                    existing.listing_status = listing_status
                    changed = True
                if fs_table_type and existing.fs_table_type != fs_table_type:
                    existing.fs_table_type = fs_table_type
                    changed = True
                if ipo_date and existing.ipo_date != ipo_date:
                    existing.ipo_date = ipo_date
                    changed = True
                if changed:
                    updated += 1

        # Delisting detection: bootstrap-sourced stocks absent from response
        for code, stock in existing_stocks.items():
            if code not in codes_in_response:
                if stock.sync_source in ("bootstrap", "delta") and stock.delisted_at is None:
                    stock.delisted_at = now
                    delisted += 1
            else:
                # Reactivate previously delisted stocks
                if stock.delisted_at is not None and stock.sync_source in ("bootstrap", "delta"):
                    stock.delisted_at = None
                    reactivated += 1

        self._logger.info(
            "Universe upsert: fetched=%d, inserted=%d, updated=%d, delisted=%d, reactivated=%d",
            len(companies), inserted, updated, delisted, reactivated,
        )

        # Re-infer business_pattern_id for all stocks (industry-driven).
        # Skip stocks with manual overrides (inferred_at IS NULL, id NOT NULL).
        try:
            from app.services.business_pattern_service import infer_all_stocks
            infer_summary = infer_all_stocks(self.db)
            self._logger.info(
                "Business pattern inference: %s", infer_summary
            )
        except Exception:
            self._logger.exception(
                "Business pattern inference failed (continuing)"
            )

        return {
            "total_fetched": len(companies),
            "inserted": inserted,
            "updated": updated,
            "delisted": delisted,
            "reactivated": reactivated,
        }

    # Unused per-stock stage methods (required by BasePipeline ABC)
    def extract(self, stock_code: str, ctx: PipelineContext) -> Any:
        pass

    def transform(self, stock_code: str, raw: Any, ctx: PipelineContext) -> Any:
        pass

    def validate(self, stock_code: str, data: Any, ctx: PipelineContext) -> Any:
        pass

    def load(self, stock_code: str, data: Any, ctx: PipelineContext) -> int:
        return 0
