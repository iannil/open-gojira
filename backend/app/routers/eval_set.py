"""Eval Set API — trigger / view / compare LLM quality baselines."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import eval_set_service

router = APIRouter(prefix="/api/eval", tags=["eval"])


@router.get("/runs")
def list_runs(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """列出最近的 Eval Run."""
    return eval_set_service.list_runs(db, limit=limit)


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    """查看单个 Eval Run 详情（含每只股票结果）。"""
    result = eval_set_service.get_run_detail(db, run_id)
    if not result:
        raise HTTPException(status_code=404, detail="EvalRun not found")
    return result


@router.post("/runs")
def create_run(
    pipeline_type: str = Query("quality_screen", description="quality_screen | deep_research"),
    label: str | None = Query(None, description="可选标签"),
    limit: int | None = Query(None, ge=1, le=20, description="限制股票数"),
    db: Session = Depends(get_db),
):
    """创建一个新的 Eval Run（记录元数据，暂不触发 LLM 调用）。"""
    return eval_set_service.run_eval(db, pipeline_type=pipeline_type, label=label, limit=limit)


@router.get("/compare")
def compare_runs(
    run_id_1: int = Query(..., description="第一个 run ID"),
    run_id_2: int = Query(..., description="第二个 run ID"),
    db: Session = Depends(get_db),
):
    """对比两个 Eval Run，返回有差异的股票列表。"""
    result = eval_set_service.compare_runs(db, run_id_1, run_id_2)
    if not result:
        raise HTTPException(status_code=404, detail="One or both runs not found")
    return result


@router.post("/runs/{run_id}/items")
def update_item(
    run_id: int,
    stock_code: str = Query(...),
    status: str = Query(..., pattern="^(completed|failed)$"),
    score: float | None = Query(None),
    score_label: str | None = Query(None),
    duration_ms: int | None = Query(None),
    cost_usd: float | None = Query(None),
    conflict_count: int = Query(0),
    red_line_triggered: bool = Query(False),
    output_summary: str | None = Query(None),
    error_message: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """手动填充单个股票的结果（用于 LLM pipeline 回调或测试）。"""
    result = eval_set_service.update_item(
        db, run_id, stock_code,
        status=status,
        score=score,
        score_label=score_label,
        duration_ms=duration_ms,
        cost_usd=cost_usd,
        conflict_count=conflict_count,
        red_line_triggered=red_line_triggered,
        output_summary=output_summary,
        error_message=error_message,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Item not found")
    return result
