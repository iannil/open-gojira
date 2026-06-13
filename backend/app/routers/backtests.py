"""Backtest API — submit + query.

v1: synchronous execution (suitable for small datasets / single-strategy
replays). Larger runs will require async + worker (deferred to v2).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.backtest_run import BacktestRun
from app.schemas.backtest import BacktestResponse, BacktestSubmit
from app.services.backtest_engine import run_backtest

router = APIRouter(prefix="/api/backtests", tags=["backtests"])


@router.post("", response_model=BacktestResponse, status_code=201)
def submit(payload: BacktestSubmit, db: Session = Depends(get_db)):
    """Submit + synchronously execute a backtest.

    v1: blocks until completion. Result returned inline.
    """
    run = BacktestRun(
        config_json=payload.model_dump(),
        status="pending",
    )
    db.add(run)
    db.flush()
    run_id = run.id
    db.commit()
    db.refresh(run)

    # Sync execution — exceptions bubble up as 500 (caught by global handler).
    # On failure, the run is marked failed inside run_backtest.
    try:
        run_backtest(db, run_id)
    except Exception:
        # run_backtest already recorded status=failed; commit + re-raise
        db.commit()
        raise
    db.commit()
    refreshed = db.get(BacktestRun, run_id)
    if refreshed is None:  # pragma: no cover — defensive
        raise HTTPException(500, "Backtest run vanished")
    return refreshed


@router.get("", response_model=list[BacktestResponse])
def list_runs(limit: int = 20, db: Session = Depends(get_db)):
    """List recent backtest runs, newest first."""
    return list(
        db.execute(
            select(BacktestRun)
            .order_by(desc(BacktestRun.created_at), desc(BacktestRun.id))
            .limit(limit)
        ).scalars().all()
    )


@router.get("/{run_id}", response_model=BacktestResponse)
def get_run(run_id: int, db: Session = Depends(get_db)):
    r = db.get(BacktestRun, run_id)
    if not r:
        raise HTTPException(404, f"backtest {run_id} not found")
    return r
