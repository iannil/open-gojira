"""Research evidence — sourced facts supporting a research run (≥25)."""

from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ResearchEvidence(Base):
    """Evidence collected by LLM via web_search (target ≥25 per run).

    Grade ladder (per serenity-skill evidence-ladder.md):
    - strong: 年报/季报/公告/问询函/招投标/环评/专利/官方订单
    - medium: 公司 IR / 财报电话会议 / 权威财经媒体 / 行业期刊
    - weak:   行业协会 / 标准 / 技术论文 / 二手转述
    - lead:   KOL / 社交媒体线索 (不作证明,仅线索)

    source_type values:
    - filing / announcement / transcript / patent / standard /
      regulator_doc / media / trade_pub / social_lead
    """

    __tablename__ = "research_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    research_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("research_runs.id"), nullable=False, index=True
    )
    stock_code: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("stocks.code"),
        nullable=True,
        index=True,  # Q14: reverse-link query optimization
    )
    # nullable: scarce-layer evidence may not bind to a specific company

    source_type: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_title: Mapped[str] = mapped_column(String, nullable=False)
    published_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    grade: Mapped[str] = mapped_column(String, nullable=False, index=True)
    summary_md: Mapped[str] = mapped_column(Text, nullable=False)
