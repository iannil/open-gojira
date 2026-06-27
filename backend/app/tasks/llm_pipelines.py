"""Native @task implementations for LLM pipeline jobs."""

import logging

from app.db.session import SessionLocal
from app.models.task import TaskRun
from app.services.task import TaskContext, task

logger = logging.getLogger(__name__)


@task(
    name="v2_quality_screen_weekly",
    cron="0 17 * * 6",
    retry=1,
    timeout=7200,
    tags=["llm", "screening"],
    description="v2: quality_screen_pipeline 全市场扫描 → watchlist",
)
def v2_quality_screen(ctx: TaskContext) -> dict:
    """Weekly quality_screen on full universe → watchlist."""
    from app.services.pipelines.llm import quality_screen_pipeline

    ctx.report_progress(0.0, "Starting quality screen")

    with SessionLocal() as db:
        try:
            summary = quality_screen_pipeline.screen_universe(db, limit=200)
            db.commit()
            ctx.report_progress(1.0, f"Quality screen complete: {summary}")
            return summary
        except Exception:
            db.rollback()
            logger.exception("v2_quality_screen failed")
            ctx.report_progress(1.0, "Failed")
            return {"error": "see logs"}


@task(
    name="v2_deep_research_weekly",
    cron="30 17 * * 6",
    retry=1,
    timeout=10800,
    tags=["llm", "research"],
    description="v2: deep_research_pipeline 对 watchlist 前 10 家深度研究",
)
def v2_deep_research(ctx: TaskContext) -> dict:
    """Weekly deep_research on top 10 watchlist stocks."""
    from app.services.pipelines.llm import deep_research_pipeline
    from app.models.stock_lifecycle import StockLifecycle
    from app.services import lifecycle_service

    ctx.report_progress(0.0, "Fetching watchlist candidates")

    with SessionLocal() as db:
        try:
            candidates = (
                db.query(StockLifecycle.stock_code)
                .filter(StockLifecycle.current_state == "watchlist")
                .order_by(StockLifecycle.entered_state_at.desc())
                .limit(10)
                .all()
            )
            codes = [c[0] for c in candidates]
            total = len(codes)
            results = {
                "attempted": total, "completed": 0,
                "skipped_cache": 0, "failed": 0,
            }

            for idx, code in enumerate(codes):
                if ctx.cancelled:
                    ctx.report_progress(1.0, "Cancelled")
                    return {**results, "cancelled": True}

                ctx.report_progress(
                    idx / total, f"Processing {code} ({idx + 1}/{total})",
                )

                if not lifecycle_service.needs_research(db, code, cache_days=30):
                    results["skipped_cache"] += 1
                    continue
                try:
                    deep_research_pipeline.run(code, db_session=db)
                    db.commit()
                    results["completed"] += 1
                except Exception:
                    db.rollback()
                    logger.exception("v2_deep_research failed for %s", code)
                    results["failed"] += 1

            db.commit()
            ctx.report_progress(1.0, f"Research complete: {results}")
            return results
        except Exception:
            logger.exception("v2_deep_research_job failed")
            return {"error": "see logs"}


@task(
    name="v2_thesis_tracker_weekly",
    cron="0 18 * * 6",
    retry=1,
    timeout=7200,
    tags=["llm", "thesis"],
    description="v2: thesis_tracker_pipeline 对持仓每周复核论文",
)
def v2_thesis_tracker(ctx: TaskContext) -> dict:
    """Weekly thesis_tracker on all active holdings."""
    from app.services.pipelines.llm import thesis_tracker_pipeline
    from app.services import position_service

    ctx.report_progress(0.0, "Fetching holdings")

    with SessionLocal() as db:
        try:
            codes = sorted(position_service.held_stock_codes(db))
            total = len(codes)
            results = {"attempted": total, "completed": 0, "failed": 0}

            for idx, code in enumerate(codes):
                if ctx.cancelled:
                    ctx.report_progress(1.0, "Cancelled")
                    return {**results, "cancelled": True}

                ctx.report_progress(
                    idx / total, f"Tracking {code} ({idx + 1}/{total})",
                )

                try:
                    thesis_tracker_pipeline.run(code, db_session=db)
                    db.commit()
                    results["completed"] += 1
                except Exception:
                    db.rollback()
                    logger.exception("v2_thesis_tracker failed for %s", code)
                    results["failed"] += 1

            db.commit()
            ctx.report_progress(1.0, f"Thesis tracking complete: {results}")
            return results
        except Exception:
            logger.exception("v2_thesis_tracker_job failed")
            return {"error": "see logs"}


# ── On-Demand Deep Research ─────────────────────────────────────────


@task(
    name="deep_research_on_demand",
    trigger_type="api",
    retry=1,
    timeout=10800,
    tags=["llm", "research", "ondemand"],
    description="手动触发的深度研究（来自 Reports/Universe 页面）",
)
def deep_research_on_demand(ctx: TaskContext) -> dict:
    """Run deep research for a stock, triggered on-demand from the UI.

    The ResearchReport placeholder is already created by the router before
    triggering this task. This function finds the running placeholder
    (by stock_code from ctx) and runs the pipeline.
    """
    import json
    from app.services.llm.client import GLMTier
    from app.services.pipelines.llm import deep_research_pipeline
    from app.models.research_report import (
        PIPELINE_DEEP_RESEARCH, STATUS_FAILED, STATUS_RUNNING, ResearchReport,
    )
    from app.models.stock import Stock

    # The caller (router) should pass input_data via engine.trigger_task
    # If there is active input_data stored in the DB, read it from there.
    # Otherwise, find the newest running report.
    with SessionLocal() as db:
        run = db.query(TaskRun).filter(TaskRun.id == ctx.run_id).first()
        input_data = json.loads(run.input_data) if run and run.input_data else {}
        stock_code = input_data.get("stock_code", "")

        if not stock_code:
            logger.error("deep_research_on_demand: no stock_code in input_data")
            return {"error": "no stock_code"}

        ctx.report_progress(0.0, f"Starting research for {stock_code}")

        # Find the running report
        report = (
            db.query(ResearchReport)
            .filter(
                ResearchReport.stock_code == stock_code,
                ResearchReport.status == STATUS_RUNNING,
            )
            .order_by(ResearchReport.created_at.desc())
            .first()
        )
        if not report:
            logger.error("deep_research_on_demand: no running report for %s", stock_code)
            return {"error": "no running report found"}

        source = input_data.get("source", "quality_screen")
        tier_str = input_data.get("model_tier", "sonnet")
        use_web_search = input_data.get("use_web_search", True)
        tier_map = {"sonnet": GLMTier.SONNET, "opus": GLMTier.OPUS, "haiku": GLMTier.HAIKU}
        tier = tier_map.get(tier_str.lower(), GLMTier.SONNET)

        ctx.report_progress(0.1, f"Running deep research for {stock_code}")

        try:
            deep_research_pipeline.run(
                stock_code,
                source=source,
                scarcity_score=input_data.get("scarcity_score"),
                failure_conditions=input_data.get("failure_conditions"),
                model_tier=tier,
                use_web_search=use_web_search,
                db_session=db,
                existing_report_id=report.id,
                on_progress=lambda p, m: ctx.report_progress(p, m),
            )
            db.commit()
            ctx.report_progress(1.0, f"Research complete for {stock_code}")
            return {"status": "completed", "stock_code": stock_code, "report_id": report.id}
        except Exception:
            db.rollback()
            logger.exception("deep_research_on_demand failed for %s", stock_code)
            # Mark the report failed
            r = db.query(ResearchReport).filter(ResearchReport.id == report.id).first()
            if r:
                r.status = STATUS_FAILED
                db.commit()
            ctx.report_progress(1.0, "Failed")
            return {"status": "failed", "stock_code": stock_code}


# ── On-Demand Theme Scan ──────────────────────────────────────────


@task(
    name="theme_scan_on_demand",
    trigger_type="api",
    retry=1,
    timeout=1800,
    tags=["llm", "theme_scan", "ondemand"],
    description="手动触发的主题扫描（来自 Engine 页面）",
)
def theme_scan_on_demand(ctx: TaskContext) -> dict:
    """Run theme_scan pipeline for a theme, triggered on-demand from the UI.

    The ThemeScanReport placeholder is already created by the router before
    triggering this task. This function reads the placeholder and updates it.
    """
    import json

    from app.services.llm.client import GLMTier
    from app.services.pipelines.llm import theme_scan_pipeline
    from app.models.theme_scan_report import (
        STATUS_FAILED,
        STATUS_RUNNING,
        ThemeScanReport,
    )

    with SessionLocal() as db:
        run = db.query(TaskRun).filter(TaskRun.id == ctx.run_id).first()
        input_data = json.loads(run.input_data) if run and run.input_data else {}
        report_id = input_data.get("report_id")
        theme = input_data.get("theme", "")

        if not report_id:
            logger.error("theme_scan_on_demand: no report_id in input_data")
            return {"error": "no report_id"}

        ctx.report_progress(0.0, f"Starting theme scan for 「{theme}」")

        tier_str = input_data.get("model_tier", "sonnet")
        use_web_search = input_data.get("use_web_search", True)
        tier_map = {"sonnet": GLMTier.SONNET, "opus": GLMTier.OPUS, "haiku": GLMTier.HAIKU}
        tier = tier_map.get(tier_str.lower(), GLMTier.SONNET)

        ctx.report_progress(0.1, f"Running theme scan pipeline for 「{theme}」")

        try:
            result = theme_scan_pipeline.run(
                theme,
                model_tier=tier,
                use_web_search=use_web_search,
                db_session=db,
                existing_report_id=report_id,
                on_progress=lambda p, m: ctx.report_progress(p, m),
            )
            db.commit()
            ctx.report_progress(1.0, f"Theme scan complete for 「{theme}」")
            return {
                "status": "completed",
                "theme": theme,
                "report_id": result.report_id,
                "evidence_grade": result.evidence_grade,
                "candidate_count": len(result.ranked_candidates),
            }
        except Exception:
            db.rollback()
            logger.exception("theme_scan_on_demand failed for theme=%s", theme)
            # Mark the placeholder report as failed
            r = db.query(ThemeScanReport).filter(
                ThemeScanReport.id == report_id
            ).first()
            if r:
                r.status = STATUS_FAILED
                db.commit()
            ctx.report_progress(1.0, "Failed")
            return {"status": "failed", "theme": theme}
