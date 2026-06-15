"""Scarce layer — bottleneck layer identified by serenity analysis."""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ScarceLayer(Base):
    """A scarce (bottleneck) layer ranking for a research run.

    3-5 rows per run, ranked by scarcity (rank=1 most scarce).
    """

    __tablename__ = "scarce_layers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    research_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("research_runs.id"), nullable=False, index=True
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    layer_ref_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("value_chain_layers.id"), nullable=False
    )
    scarcity_reason_md: Mapped[str] = mapped_column(Text, nullable=False)
    expansion_difficulty: Mapped[str] = mapped_column(String, nullable=False)
    # "high" / "medium" / "low"
