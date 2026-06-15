"""Value chain layer — one of 8 standard layers per serenity-skill workflow."""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ValueChainLayer(Base):
    """A layer in the value chain for a research run.

    layer_index convention (per serenity-skill deep-research-workflow.md):
      1 = downstream customers / capex source
      2 = system integrators / OEMs
      3 = modules / subsystems
      4 = chips / devices / critical components
      5 = process / assembly / packaging / testing
      6 = equipment / metrology
      7 = materials / consumables / specialty inputs
      8 = physical infrastructure
    """

    __tablename__ = "value_chain_layers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    research_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("research_runs.id"), nullable=False, index=True
    )
    layer_index: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
