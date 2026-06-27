"""Native @task implementations for core data sync jobs.

Phase 2: Converted from _compat.py wrappers to direct Task implementations.
         Each task uses TaskContext for progress reporting and cancellation support.
"""

import logging

from app.db.session import SessionLocal
from app.services.task import TaskContext, task

logger = logging.getLogger(__name__)


# ── Helper ────────────────────────────────────────────────────────────

def _run_pipeline(pipeline_type: str, stock_codes: list[str]) -> dict:
    """Run a pipeline synchronously and return its result dict."""
    from app.services.pipelines.manager import PipelineManager

    with SessionLocal() as db:
        mgr = PipelineManager(db)
        result = mgr.start(
            pipeline_type=pipeline_type,
            stock_codes=stock_codes,
            background=False,
        )
        return result


# ── Universe Bootstrap ────────────────────────────────────────────────


@task(
    name="daily_universe_bootstrap",
    cron="0 15 * * 1-5",
    retry=2,
    timeout=1800,
    tags=["data", "universe"],
    description="全A股列表增量同步（新股/退市检测）",
)
def daily_universe_bootstrap(ctx: TaskContext) -> dict:
    """Sync the full A-share stock list: detect new listings and delistings."""
    ctx.report_progress(0.0, "Starting universe bootstrap")
    result = _run_pipeline("universe_bootstrap", [])
    ctx.report_progress(1.0, "Universe bootstrap complete")
    return {
        "result": str(result),
        "completed_items": result.get("completed_items", 0),
    }



# ── Base Sync ────────────────────────────────────────────────────────


@task(
    name="daily_base_sync",
    cron="15 15 * * 1-5",
    retry=2,
    timeout=3600,
    depends_on=["daily_universe_bootstrap"],
    tags=["data", "valuation"],
    description="全量基础估值同步（PE/PB/股息率/百分位）",
)
def daily_base_sync(ctx: TaskContext) -> dict:
    """Base tier sync: valuation data for all A-shares."""
    from app.services.data_management_service import get_all_active_stock_codes
    from app.services.pipelines.manager import PipelineManager

    ctx.report_progress(0.0, "Fetching active stock codes")

    with SessionLocal() as db:
        all_codes = get_all_active_stock_codes(db)
        if not all_codes:
            ctx.report_progress(1.0, "No stocks to sync")
            return {"synced": 0, "codes": 0}

        total = len(all_codes)
        ctx.report_progress(0.1, f"Starting sync for {total} stocks")

        mgr = PipelineManager(db)
        result = mgr.start(
            pipeline_type="valuations",
            stock_codes=all_codes,
            background=False,
        )

        ctx.report_progress(1.0, "Sync complete")
        return {
            "synced": result.get("completed_items", 0),
            "codes": total,
            "result": str(result),
        }


# ── Daily Snapshot ────────────────────────────────────────────────────


@task(
    name="daily_snapshot",
    cron="0 17 * * 1-5",
    retry=2,
    timeout=1800,
    tags=["data", "snapshot"],
    description="每日估值快照（PE/PB/股息率）",
)
def daily_snapshot(ctx: TaskContext) -> dict:
    """Fetch realtime fundamentals for every watched code, persist snapshots."""
    from datetime import date

    from app.models.stock_lifecycle import (
        STATE_CANDIDATE,
        STATE_RESEARCHED,
        STATE_SIGNALED,
        STATE_WATCHLIST,
        StockLifecycle,
    )
    from app.models.valuation import ValuationSnapshot
    from app.services.lixinger_client import LixingerError, get_lixinger_client

    ctx.report_progress(0.0, "Fetching watchlist codes")

    with SessionLocal() as db:
        codes = [
            r[0]
            for r in db.query(StockLifecycle.stock_code)
            .filter(
                StockLifecycle.current_state.in_(
                    (STATE_WATCHLIST, STATE_RESEARCHED, STATE_CANDIDATE, STATE_SIGNALED)
                )
            )
            .all()
        ]
        if not codes:
            ctx.report_progress(1.0, "No watchlist items to snapshot")
            return {"snapshots": 0, "codes": 0}

        ctx.report_progress(0.2, f"Fetching fundamentals for {len(codes)} codes")

        try:
            client = get_lixinger_client()
            data = client.get_fundamentals(
                stock_codes=codes,
                metrics=[
                    "pe_ttm", "pb", "dyr", "sp",
                    "pe_ttm.y10.cvpos", "pb.y10.cvpos",
                ],
            )
        except LixingerError:
            logger.exception("daily_snapshot: lixinger failure")
            ctx.report_progress(1.0, "Lixinger API failed")
            return {"snapshots": 0, "codes": len(codes), "error": "lixinger"}

        today = date.today()
        count = 0
        total = len(data)

        for idx, item in enumerate(data):
            if ctx.cancelled:
                ctx.report_progress(1.0, "Cancelled during snapshot")
                return {"snapshots": count, "codes": len(codes), "cancelled": True}

            code = item.get("stockCode")
            if not code:
                continue

            pe_pct = _extract_pct(item.get("pe_ttm.y10.cvpos"))
            pb_pct = _extract_pct(item.get("pb.y10.cvpos"))

            existing = (
                db.query(ValuationSnapshot)
                .filter(
                    ValuationSnapshot.stock_code == code,
                    ValuationSnapshot.date == today,
                )
                .first()
            )
            if existing:
                existing.pe_ttm = item.get("pe_ttm")
                existing.pb = item.get("pb")
                existing.pe_percentile_10y = pe_pct
                existing.pb_percentile_10y = pb_pct
                existing.dividend_yield = item.get("dyr")
            else:
                db.add(
                    ValuationSnapshot(
                        stock_code=code,
                        date=today,
                        pe_ttm=item.get("pe_ttm"),
                        pb=item.get("pb"),
                        pe_percentile_10y=pe_pct,
                        pb_percentile_10y=pb_pct,
                        dividend_yield=item.get("dyr"),
                    )
                )
                count += 1

            if idx % 50 == 0:
                db.flush()
                ctx.report_progress(
                    0.2 + 0.7 * (idx + 1) / total,
                    f"Processed {idx + 1}/{total} codes",
                )

        db.commit()
        ctx.report_progress(1.0, f"Snapshot complete: {count} new records")
        return {"snapshots": count, "codes": len(codes)}


# ── K-Line Sync ───────────────────────────────────────────────────────


@task(
    name="daily_kline_sync",
    cron="15 17 * * 1-5",
    retry=3,
    timeout=3600,
    depends_on=["daily_base_sync"],
    tags=["data", "kline"],
    description="日K线同步（关注+持仓股）",
)
def daily_kline_sync(ctx: TaskContext) -> dict:
    """Incrementally pull daily K-line for watchlist + held codes."""
    from app.services.kline_service import get_klines

    ctx.report_progress(0.0, "Fetching watched and held codes")

    with SessionLocal() as db:
        codes = _watched_and_held_codes(db)
        if not codes:
            ctx.report_progress(1.0, "No codes to sync")
            return {"synced": 0, "codes": 0}

        total = len(codes)
        ok = 0

        for idx, code in enumerate(codes):
            if ctx.cancelled:
                ctx.report_progress(1.0, "Cancelled")
                return {"synced": ok, "codes": total, "cancelled": True}

            try:
                get_klines(db, code, refresh=True)
                ok += 1
            except Exception:
                logger.exception("daily_kline_sync: failed for %s", code)

            if idx % 20 == 0:
                ctx.report_progress((idx + 1) / total, f"Synced {ok}/{total}")

        db.commit()
        ctx.report_progress(1.0, f"K-line sync complete: {ok}/{total}")
        return {"synced": ok, "codes": total}


# ── Prev Close Sync ───────────────────────────────────────────────────


@task(
    name="daily_prev_close_sync",
    cron="20 17 * * 1-5",
    retry=2,
    timeout=600,
    depends_on=["daily_base_sync"],
    tags=["data", "prev_close"],
    description="prev_close同步（持仓+候选股，涨跌停校验用）",
)
def daily_prev_close_sync(ctx: TaskContext) -> dict:
    """Sync prev_close for held + candidate codes (used for price-band validation)."""
    from app.services.kline_service import get_klines

    ctx.report_progress(0.0, "Fetching held and candidate codes")

    with SessionLocal() as db:
        codes = _watched_held_and_candidate_codes(db)
        if not codes:
            ctx.report_progress(1.0, "No codes to sync")
            return {"synced": 0, "codes": 0}

        total = len(codes)
        ok = 0

        for idx, code in enumerate(codes):
            if ctx.cancelled:
                ctx.report_progress(1.0, "Cancelled")
                return {"synced": ok, "codes": total, "cancelled": True}

            try:
                kline = get_klines(db, code, refresh=True)
                if kline:
                    ok += 1
            except Exception:
                logger.exception("daily_prev_close_sync: failed for %s", code)

            if idx % 30 == 0:
                ctx.report_progress((idx + 1) / total, f"Synced {ok}/{total}")

        db.commit()
        ctx.report_progress(1.0, f"Prev close sync complete: {ok}/{total}")
        return {"synced": ok, "codes": total}


# ── Pipeline Stale Sweep ──────────────────────────────────────────────


@task(
    name="pipeline_stale_sweep",
    cron="*/15 * * * *",
    retry=1,
    timeout=300,
    tags=["housekeeping"],
    description="周期性清理 stuck pipeline runs（后台线程死亡但 status=running 的孤儿记录）",
)
def pipeline_stale_sweep(ctx: TaskContext) -> dict:
    """Recover pipeline runs stuck in running/pending state."""
    from app.services.pipelines.manager import PipelineManager

    ctx.report_progress(0.0, "Checking for stale pipeline runs")

    with SessionLocal() as db:
        recovered = PipelineManager.recover_stale_runs(db)
        db.commit()

    ctx.report_progress(1.0, f"Recovered {recovered} stale runs")
    return {"recovered": recovered}


# ── Shared Helpers ────────────────────────────────────────────────────


def _extract_pct(raw) -> float | None:
    """Extract a percentage value from lixinger API response."""
    if raw is None:
        return None
    try:
        return round(float(raw) * 100, 2)
    except (ValueError, TypeError):
        return None


def _watched_and_held_codes(db) -> list[str]:
    """Codes the user actively cares about: watchlist + open holdings."""
    from app.models.stock_lifecycle import (
        STATE_CANDIDATE,
        STATE_RESEARCHED,
        STATE_SIGNALED,
        STATE_WATCHLIST,
        StockLifecycle,
    )
    from app.services import position_service

    watch = {
        r[0]
        for r in db.query(StockLifecycle.stock_code)
        .filter(
            StockLifecycle.current_state.in_(
                (STATE_WATCHLIST, STATE_RESEARCHED, STATE_CANDIDATE, STATE_SIGNALED)
            )
        )
        .all()
    }
    return sorted(watch | position_service.held_stock_codes(db))


def _watched_held_and_candidate_codes(db) -> list[str]:
    """Extend watched+held with candidate codes (for prev_close sync)."""
    base = set(_watched_and_held_codes(db))
    return sorted(base)


# ── Monthly Dividend Sync ────────────────────────────────────────────


@task(
    name="monthly_dividend_sync",
    cron="0 3 1 * *",
    retry=2,
    timeout=1800,
    tags=["data", "dividend"],
    description="月度分红记录同步",
)
def monthly_dividend_sync(ctx: TaskContext) -> dict:
    """Refresh historical dividend records for watchlist + held codes."""
    from app.services.dividend_service import fetch_and_store_from_lixinger

    ctx.report_progress(0.0, "Fetching codes")

    with SessionLocal() as db:
        codes = _watched_and_held_codes(db)
        total = len(codes)
        total_inserted = 0
        ok = 0

        for idx, code in enumerate(codes):
            if ctx.cancelled:
                ctx.report_progress(1.0, "Cancelled")
                return {"inserted": total_inserted, "codes": total, "ok": ok}

            try:
                total_inserted += fetch_and_store_from_lixinger(db, code, years=10)
                ok += 1
            except Exception:
                logger.exception("monthly_dividend_sync: failed for %s", code)

            if idx % 50 == 0:
                ctx.report_progress(idx / total, f"Processed {idx}/{total}")

        db.commit()
        ctx.report_progress(1.0, f"Complete: {total_inserted} records")
        return {"inserted": total_inserted, "codes": total, "ok": ok}


# ── Weekly Dividend Sync ─────────────────────────────────────────────


@task(
    name="weekly_dividend_sync",
    cron="0 9 * * 1",
    retry=2,
    timeout=600,
    tags=["data", "dividend"],
    description="周度分红历史同步（持仓+关注+候选股）",
)
def weekly_dividend_sync(ctx: TaskContext) -> dict:
    """Weekly pull of dividend history for held/watched/candidate stocks."""
    from app.services.corp_action_sync_service import sync_dividends_batch

    ctx.report_progress(0.0, "Fetching codes")

    with SessionLocal() as db:
        codes = _watched_held_and_candidate_codes(db)
        if not codes:
            ctx.report_progress(1.0, "No codes")
            return {"new_count": 0, "codes": 0}

        new = sync_dividends_batch(db, codes)
        db.commit()
        ctx.report_progress(1.0, f"Synced {new} records")
        return {"new_count": new, "codes": len(codes)}


# ── Quarterly Financials Refresh ─────────────────────────────────────


@task(
    name="quarterly_financials_refresh",
    cron="0 4 25-31 3,4,8,10 *",
    retry=2,
    timeout=3600,
    tags=["data", "financial"],
    description="季报财报数据刷新",
)
def quarterly_financials_refresh(ctx: TaskContext) -> dict:
    """Quarterly financials refresh tied to A-share reporting windows."""
    from app.services.financial_service import fetch_and_store_financials

    ctx.report_progress(0.0, "Fetching codes")

    with SessionLocal() as db:
        codes = _watched_and_held_codes(db)
        total = len(codes)
        ok = 0

        for idx, code in enumerate(codes):
            if ctx.cancelled:
                ctx.report_progress(1.0, "Cancelled")
                return {"refreshed": ok, "codes": total}

            try:
                fetch_and_store_financials(db, code, years=5)
                ok += 1
            except Exception:
                logger.exception("quarterly_financials_refresh: failed for %s", code)

            if idx % 30 == 0:
                ctx.report_progress(idx / total, f"Refreshed {ok}/{total}")

        db.commit()
        ctx.report_progress(1.0, f"Refreshed {ok}/{total}")
        return {"refreshed": ok, "codes": total}


# ── Quarterly Shareholders Refresh ───────────────────────────────────


@task(
    name="quarterly_shareholders_refresh",
    cron="30 4 5 1,4,7,10 *",
    retry=2,
    timeout=1800,
    tags=["data", "shareholder"],
    description="季度股东数据刷新",
)
def quarterly_shareholders_refresh(ctx: TaskContext) -> dict:
    """Refresh majority shareholders + shareholder-count."""
    from app.services.shareholders_service import (
        get_majority_shareholders, get_shareholders_num,
    )

    ctx.report_progress(0.0, "Fetching codes")

    with SessionLocal() as db:
        codes = _watched_and_held_codes(db)
        total = len(codes)
        ok = 0

        for idx, code in enumerate(codes):
            if ctx.cancelled:
                ctx.report_progress(1.0, "Cancelled")
                return {"refreshed": ok, "codes": total}

            try:
                get_majority_shareholders(code)
                get_shareholders_num(code)
                ok += 1
            except Exception:
                logger.exception("shareholders refresh: failed for %s", code)

            if idx % 50 == 0:
                ctx.report_progress(idx / total, f"Refreshed {ok}/{total}")

        ctx.report_progress(1.0, f"Refreshed {ok}/{total}")
        return {"refreshed": ok, "codes": total}


# ── Corp Action Apply ────────────────────────────────────────────────


@task(
    name="daily_corp_action_apply",
    cron="0 9 * * 1-5",
    retry=1,
    timeout=600,
    tags=["housekeeping", "corp_action"],
    description="每日公司行为应用",
)
def daily_corp_action_apply(ctx: TaskContext) -> dict:
    """Apply pending corp_actions whose ex_date <= today."""
    from datetime import date
    from app.services.corp_action_processor_service import process_pending_corp_actions

    ctx.report_progress(0.0, "Applying corp actions")

    with SessionLocal() as db:
        count = process_pending_corp_actions(db, as_of=date.today())
        db.commit()

    ctx.report_progress(1.0, f"Applied {count} actions")
    return {"applied_count": count}


# ── Daily Index Sync ─────────────────────────────────────────────────


@task(
    name="daily_index_sync",
    cron="0 19 * * 1-5",
    retry=2,
    timeout=1800,
    tags=["data", "index"],
    description="沪深300 日 K 线同步（组合评价基准对比用）",
)
def daily_index_sync(ctx: TaskContext) -> dict:
    """Sync benchmark index (沪深300) klines."""
    from app.services import index_service

    ctx.report_progress(0.0, "Syncing index klines")

    with SessionLocal() as db:
        try:
            result = index_service.sync_index_klines(db)
            db.commit()
            ctx.report_progress(1.0, "Sync complete")
            return result
        except Exception:
            db.rollback()
            logger.exception("daily_index_sync failed")
            ctx.report_progress(1.0, "Failed")
            return {"error": "see logs"}


# ── Alert Evaluation ────────────────────────────────────────────────


@task(
    name="alert_evaluation",
    cron="30 17 * * 1-5",
    retry=1,
    timeout=600,
    tags=["housekeeping", "alert"],
    description="警报规则评估",
)
def alert_evaluation(ctx: TaskContext) -> dict:
    """Evaluate all enabled alert rules."""
    from app.services import alert_service

    ctx.report_progress(0.0, "Evaluating alerts")

    with SessionLocal() as db:
        result = alert_service.evaluate_all_rules(db)

    ctx.report_progress(1.0, "Alert evaluation complete")
    return result
