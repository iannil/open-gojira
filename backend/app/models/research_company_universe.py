"""Research company universe — broad candidate list per run (≥20)."""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ResearchCompanyUniverse(Base):
    """Companies considered in a research run (target ≥20).

    classification values:
    - controls: 控制稀缺层
    - supplies: 供应稀缺层
    - benefits: 受益主题但定价权弱
    - weak:     暴露弱 / 故事为主
    - story:    纯故事,证据不足
    """

    __tablename__ = "research_company_universe"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    research_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("research_runs.id"), nullable=False, index=True
    )
    stock_code: Mapped[str] = mapped_column(
        String,
        ForeignKey("stocks.code"),
        nullable=False,
        index=True,  # Q14: reverse-link query optimization
    )
    classification: Mapped[str] = mapped_column(String, nullable=False)
    layer_ref_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("value_chain_layers.id"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
