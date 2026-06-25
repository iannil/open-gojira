"""Theme scan report — serenity bottleneck-hunter output (theme-level).

trading-philosophy.md §2: the serenity engine produces a THEME-level result
(ranked value-chain layers → ranked companies), unlike ResearchReport which is
per-stock. Each ranked candidate carries a scarcity_score (1-5) that is later
handed into deep_research as the 卡点 dimension (reuse, §3).
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base
from app.core.datetime_utils import now


PIPELINE_THEME_SCAN = "theme_scan"

# Report status (mirrors research_report status vocabulary)
STATUS_COMPLETED = "completed"
STATUS_EMPTY = "empty"        # no scarce layer / no valid A-share candidate found


class ThemeScanReport(Base):
    __tablename__ = "theme_scan_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    theme: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # Step 1: 叙事 → 系统变化 (what physical/economic constraint drives demand)
    system_change: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Step 3: ranked scarce layers — [{"layer","scarcity_rationale","rank"}]
    ranked_layers_json: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Step 5: ranked candidates — [{"code","name","layer","chain_position",
    #   "scarcity_score","thesis","failure_conditions","evidence"}]
    ranked_candidates_json: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Full raw output of every step (feeds debugging / downstream).
    json_output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    markdown_output: Mapped[str | None] = mapped_column(Text, nullable=True)

    evidence_grade: Mapped[str | None] = mapped_column(String(1), nullable=True)  # A/B/C
    prompt_version: Mapped[str | None] = mapped_column(String, nullable=True)

    status: Mapped[str] = mapped_column(
        String, nullable=False, default=STATUS_COMPLETED, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now(), index=True)
