"""Cycle assessment service — 逆向仓位法核心.

Computes market cycle position based on index PE percentile.
Maps to invest3 "先判断大环境" + "逆向仓位法":
  - PE 分位 0-10%  -> extreme_low  -> 建议 80-100% 仓位
  - PE 分位 10-30% -> low          -> 建议 60-80% 仓位
  - PE 分位 30-70% -> mid          -> 建议 40-60% 仓位
  - PE 分位 70-90% -> high         -> 建议 20-40% 仓位
  - PE 分位 90-100%-> extreme_high -> 建议 0-20% 仓位
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cashflow_goal import CashflowGoal
from app.services.lixinger_client import get_lixinger_client, LixingerError

logger = logging.getLogger(__name__)

CSI300_CODE = "000300"

# Cycle position thresholds (PE percentile boundaries)
CYCLE_THRESHOLDS = [
    (10, "extreme_low"),
    (30, "low"),
    (70, "mid"),
    (90, "high"),
    (101, "extreme_high"),
]

# Position advice per cycle position
POSITION_ADVICE: dict[str, tuple[float, float, str]] = {
    "extreme_low":  (0.80, 1.00, "极度低估，可重仓甚至满仓"),
    "low":          (0.60, 0.80, "低估区间，可积极配置"),
    "mid":          (0.40, 0.60, "中等估值，正常持有"),
    "high":         (0.20, 0.40, "估值偏高，主动减仓"),
    "extreme_high": (0.00, 0.20, "极度高估，尽量空仓"),
}


class CycleAssessment(BaseModel):
    """Market cycle assessment model with PE/PB percentiles and position advice."""

    pe_pct_10y: float | None
    pb_pct_10y: float | None
    dyr_index: float | None
    cycle_position: str
    position_min: float
    position_max: float
    position_advice: str

    def to_dict(self) -> dict:
        """Convert to dict for API response compatibility.

        Note: This method provides backward compatibility. New code should use .model_dump().
        """
        return {
            "pe_pct_10y": self.pe_pct_10y,
            "pb_pct_10y": self.pb_pct_10y,
            "dyr_index": self.dyr_index,
            "cycle_position": self.cycle_position,
            "position_range": [self.position_min, self.position_max],
            "position_advice": self.position_advice,
        }


def classify_cycle(pe_pct: float | None) -> str:
    if pe_pct is None:
        return "mid"
    for threshold, label in CYCLE_THRESHOLDS:
        if pe_pct < threshold:
            return label
    return "extreme_high"


def compute_index_percentile(history: list[dict]) -> dict:
    """Calculate PE/PB percentile from index fundamental history.

    Args:
        history: List of {"date": str, "pe_ttm.mcw": float, "pb.mcw": float, ...}

    Returns:
        {"pe_pct_10y": float|None, "pb_pct_10y": float|None, "current_pe": float|None, ...}
    """
    if not history:
        return {
            "pe_pct_10y": None,
            "pb_pct_10y": None,
            "current_pe": None,
            "current_pb": None,
            "current_dyr": None,
        }

    pe_values = [
        float(e["pe_ttm.mcw"]) for e in history
        if e.get("pe_ttm.mcw") is not None
    ]
    pb_values = [
        float(e["pb.mcw"]) for e in history
        if e.get("pb.mcw") is not None
    ]

    latest = history[-1]
    current_pe = (
        float(latest["pe_ttm.mcw"]) if latest.get("pe_ttm.mcw") is not None else None
    )
    current_pb = (
        float(latest["pb.mcw"]) if latest.get("pb.mcw") is not None else None
    )
    current_dyr = (
        float(latest["dyr.mcw"]) if latest.get("dyr.mcw") is not None else None
    )

    pe_pct = None
    if current_pe is not None and pe_values:
        pe_pct = round(sum(1 for v in pe_values if v <= current_pe) / len(pe_values) * 100, 1)

    pb_pct = None
    if current_pb is not None and pb_values:
        pb_pct = round(sum(1 for v in pb_values if v <= current_pb) / len(pb_values) * 100, 1)

    return {
        "pe_pct_10y": pe_pct,
        "pb_pct_10y": pb_pct,
        "current_pe": current_pe,
        "current_pb": current_pb,
        "current_dyr": current_dyr,
    }


def assess_cycle(db: Session) -> CycleAssessment:
    """Assess current market cycle position.

    Strategy:
    1. Try to fetch 10y index PE history from Lixinger and compute percentile
    2. Fallback to CashflowGoal.current_index_pe_pct (manual override)
    3. Classify cycle position and return position advice
    """
    pe_pct: float | None = None
    pb_pct: float | None = None
    dyr: float | None = None

    # Try Lixinger first
    try:
        client = get_lixinger_client()
        start = (date.today() - timedelta(days=10 * 365)).strftime("%Y-%m-%d")
        end = date.today().strftime("%Y-%m-%d")
        history = client.get_index_fundamental(
            stock_codes=[CSI300_CODE],
            start_date=start,
            end_date=end,
            metrics=["pe_ttm.mcw", "pb.mcw", "dyr.mcw"],
        )
        if history:
            pct = compute_index_percentile(history)
            pe_pct = pct["pe_pct_10y"]
            pb_pct = pct["pb_pct_10y"]
            dyr = pct["current_dyr"]
            logger.info("Cycle assessment from Lixinger: PE pct=%.1f, PB pct=%.1f", pe_pct, pb_pct)
    except LixingerError:
        logger.warning("Lixinger index fundamental failed, falling back to manual PE pct")

    # Fallback to CashflowGoal manual value
    if pe_pct is None:
        row = db.execute(
            select(CashflowGoal).where(CashflowGoal.id == 1)
        ).scalar_one_or_none()
        if row and row.current_index_pe_pct is not None:
            pe_pct = float(row.current_index_pe_pct)
            logger.info("Cycle assessment from manual PE pct: %.1f", pe_pct)

    # Classify and advise
    cycle_position = classify_cycle(pe_pct)
    pos_min, pos_max, advice = POSITION_ADVICE[cycle_position]

    # Persist PE percentile to CashflowGoal for frontend consumption
    if pe_pct is not None:
        _update_cashflow_goal_pe_pct(db, pe_pct)

    return CycleAssessment(
        pe_pct_10y=pe_pct,
        pb_pct_10y=pb_pct,
        dyr_index=dyr,
        cycle_position=cycle_position,
        position_min=pos_min,
        position_max=pos_max,
        position_advice=advice,
    )


def _update_cashflow_goal_pe_pct(db: Session, pe_pct: float) -> None:
    """Persist computed PE percentile to CashflowGoal for frontend use.

    Caller is responsible for committing the transaction.
    """
    row = db.execute(
        select(CashflowGoal).where(CashflowGoal.id == 1)
    ).scalar_one_or_none()
    if row:
        row.current_index_pe_pct = pe_pct
