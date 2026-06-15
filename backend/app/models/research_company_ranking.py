"""Company ranking — top priority picks per run (3-7)."""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ResearchCompanyRanking(Base):
    """Top 3-7 ranked companies in a research run.

    Each row carries: what it constrains / chain position / rank reason /
    evidence summary / main risk. Distinct from ResearchCompanyUniverse
    (broad list) — this is the curated priority list.
    """

    __tablename__ = "research_company_ranking"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    research_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("research_runs.id"), nullable=False, index=True
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    stock_code: Mapped[str] = mapped_column(
        String,
        ForeignKey("stocks.code"),
        nullable=False,
        index=True,  # Q14: reverse-link query optimization
    )
    constrains_what: Mapped[str] = mapped_column(String, nullable=False)
    chain_position: Mapped[str] = mapped_column(String, nullable=False)
    rank_reason_md: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_summary_md: Mapped[str] = mapped_column(Text, nullable=False)
    main_risk_md: Mapped[str] = mapped_column(Text, nullable=False)
