from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Holding(Base):
    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(
        String, ForeignKey("stocks.code"), nullable=False
    )
    buy_date: Mapped[date] = mapped_column(Date, nullable=False)
    buy_price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    sell_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sell_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_profit_price: Mapped[float] = mapped_column(Float, nullable=False)
    trade_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    sell_thesis: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_holdings_stock_sell", "stock_code", "sell_date"),
    )

    # Relationships
    stock: Mapped["Stock"] = relationship(back_populates="holdings")  # noqa: F821
