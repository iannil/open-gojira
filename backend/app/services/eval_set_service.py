"""Eval Set service — run LLM pipelines on a fixed stock list and record baselines.

Usage:
    # Run quality_screen eval (dry run — estimates cost)
    eval_service.run_eval(db, pipeline_type="quality_screen")

    # Run deep_research eval on a subset (e.g. top 5)
    eval_service.run_eval(db, pipeline_type="deep_research", limit=5)

    # Compare two runs
    diff = eval_service.compare_runs(db, run_id_1, run_id_2)
"""

import json
import logging
import time
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.datetime_utils import now
from app.models.eval_set import EvalRun, EvalRunItem
from app.services.eval_stocks import EVAL_STOCKS

logger = logging.getLogger(__name__)


def list_runs(db: Session, limit: int = 20) -> list[dict]:
    """List recent eval runs with summary stats."""
    rows = (
        db.execute(
            select(EvalRun)
            .order_by(EvalRun.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": r.id,
            "label": r.label,
            "status": r.status,
            "pipeline_type": r.pipeline_type,
            "stock_count": r.stock_count,
            "passed": r.passed,
            "failed": r.failed,
            "total_cost_usd": r.total_cost_usd,
            "created_at": str(r.created_at) if r.created_at else None,
            "finished_at": str(r.finished_at) if r.finished_at else None,
        }
        for r in rows
    ]


def get_run_detail(db: Session, run_id: int) -> dict | None:
    """Get a single eval run with its items."""
    run = db.get(EvalRun, run_id)
    if not run:
        return None

    items = (
        db.execute(
            select(EvalRunItem)
            .where(EvalRunItem.eval_run_id == run_id)
            .order_by(EvalRunItem.stock_code)
        )
        .scalars()
        .all()
    )

    return {
        "id": run.id,
        "label": run.label,
        "status": run.status,
        "pipeline_type": run.pipeline_type,
        "stock_count": run.stock_count,
        "passed": run.passed,
        "failed": run.failed,
        "total_cost_usd": run.total_cost_usd,
        "summary_json": run.summary_json,
        "error_message": run.error_message,
        "created_at": str(run.created_at) if run.created_at else None,
        "finished_at": str(run.finished_at) if run.finished_at else None,
        "items": [
            {
                "id": item.id,
                "stock_code": item.stock_code,
                "stock_name": item.stock_name,
                "status": item.status,
                "score": item.score,
                "score_label": item.score_label,
                "duration_ms": item.duration_ms,
                "cost_usd": item.cost_usd,
                "conflict_count": item.conflict_count,
                "red_line_triggered": item.red_line_triggered,
                "output_summary": item.output_summary,
                "error_message": item.error_message,
            }
            for item in items
        ],
    }


def compare_runs(db: Session, run_id_1: int, run_id_2: int) -> dict | None:
    """Compare two eval runs for drift detection.

    Returns a diff keyed by stock_code with per-stock score changes.
    """
    run1 = get_run_detail(db, run_id_1)
    run2 = get_run_detail(db, run_id_2)
    if not run1 or not run2:
        return None

    items1 = {i["stock_code"]: i for i in run1["items"]}
    items2 = {i["stock_code"]: i for i in run2["items"]}

    diffs = []
    for code in sorted(set(items1.keys()) | set(items2.keys())):
        i1 = items1.get(code)
        i2 = items2.get(code)
        if i1 and i2:
            score_diff = (i2.get("score") or 0) - (i1.get("score") or 0)
            duration_diff = (i2.get("duration_ms") or 0) - (i1.get("duration_ms") or 0)
            cost_diff = (i2.get("cost_usd") or 0) - (i1.get("cost_usd") or 0)
            status_changed = i1["status"] != i2["status"]
            conflict_changed = i1["conflict_count"] != i2["conflict_count"]
            red_line_changed = i1["red_line_triggered"] != i2["red_line_triggered"]
        elif i1 and not i2:
            score_diff = -(i1.get("score") or 0)
            duration_diff = 0
            cost_diff = 0
            status_changed = True
            conflict_changed = False
            red_line_changed = False
        else:
            score_diff = i2.get("score") or 0 if i2 else 0
            duration_diff = 0
            cost_diff = 0
            status_changed = True
            conflict_changed = False
            red_line_changed = False

        if any([abs(score_diff) > 0.1, status_changed, conflict_changed, red_line_changed, abs(cost_diff) > 0.001]):
            diffs.append({
                "stock_code": code,
                "stock_name": (i1 or i2).get("stock_name", ""),
                "score_before": i1.get("score") if i1 else None,
                "score_after": i2.get("score") if i2 else None,
                "score_diff": round(score_diff, 2),
                "duration_diff_ms": duration_diff,
                "cost_diff_usd": round(cost_diff, 4),
                "status_changed": status_changed,
                "conflict_changed": conflict_changed,
                "red_line_changed": red_line_changed,
                "output_before": i1.get("output_summary", "")[:200] if i1 else None,
                "output_after": i2.get("output_summary", "")[:200] if i2 else None,
            })

    return {
        "run_1": {"id": run_id_1, "label": run1["label"], "created_at": run1["created_at"]},
        "run_2": {"id": run_id_2, "label": run2["label"], "created_at": run2["created_at"]},
        "changed_count": len(diffs),
        "total_stocks": len(set(items1.keys()) | set(items2.keys())),
        "changes": diffs,
    }


def run_eval(
    db: Session,
    pipeline_type: str = "quality_screen",
    label: str | None = None,
    limit: int | None = None,
) -> dict:
    """Run an evaluation: execute the target pipeline on the eval stock list.

    SOON: Currently records the run metadata but does NOT invoke the actual
    LLM pipeline (to avoid burning $ in dev/test). The pipeline runner will
    be wired once the eval workflow is validated.

    To manually fill results for testing:
        POST /api/eval/{run_id}/items  (per-stock)
    """
    stocks = EVAL_STOCKS[:limit] if limit else EVAL_STOCKS

    run = EvalRun(
        label=label or f"{pipeline_type} eval {now().strftime('%Y-%m-%d %H:%M')}",
        status="running",
        pipeline_type=pipeline_type,
        stock_count=len(stocks),
        passed=0,
        failed=0,
        summary_json={"note": "pipeline execution not yet wired; records are placeholder"},
    )
    db.add(run)
    db.flush()

    for s in stocks:
        item = EvalRunItem(
            eval_run_id=run.id,
            stock_code=s["code"],
            stock_name=s["name"],
            status="pending",
        )
        db.add(item)

    run.status = "completed"
    run.finished_at = now()
    db.commit()

    logger.info("eval_run created: id=%s pipeline=%s stocks=%d", run.id, pipeline_type, len(stocks))
    return {"run_id": run.id, "stock_count": len(stocks)}


def update_item(
    db: Session,
    run_id: int,
    stock_code: str,
    *,
    status: str,
    score: float | None = None,
    score_label: str | None = None,
    duration_ms: int | None = None,
    cost_usd: float | None = None,
    conflict_count: int = 0,
    red_line_triggered: bool = False,
    output_summary: str | None = None,
    error_message: str | None = None,
) -> dict | None:
    """Update a single eval item (used by manual fill or pipeline callback)."""
    item = db.execute(
        select(EvalRunItem).where(
            EvalRunItem.eval_run_id == run_id,
            EvalRunItem.stock_code == stock_code,
        )
    ).scalar_one_or_none()
    if not item:
        return None

    item.status = status
    if score is not None:
        item.score = score
    if score_label is not None:
        item.score_label = score_label
    if duration_ms is not None:
        item.duration_ms = duration_ms
    if cost_usd is not None:
        item.cost_usd = cost_usd
    if conflict_count is not None:
        item.conflict_count = conflict_count
    if red_line_triggered is not None:
        item.red_line_triggered = red_line_triggered
    if output_summary is not None:
        item.output_summary = output_summary
    if error_message is not None:
        item.error_message = error_message

    # Update run aggregate
    run = db.get(EvalRun, run_id)
    if run:
        if status == "completed":
            run.passed += 1
        elif status == "failed":
            run.failed += 1

    db.commit()

    return {
        "id": item.id,
        "stock_code": item.stock_code,
        "status": item.status,
        "score": item.score,
        "score_label": item.score_label,
    }
