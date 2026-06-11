from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DividendRecord(Base):
    __tablename__ = "dividends"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(
        String, ForeignKey("stocks.code"), nullable=False
    )
    ex_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount_per_share: Mapped[float] = mapped_column(Float, nullable=False)
    quantity_held: Mapped[int] = mapped_column(Integer, nullable=False)
    total_received: Mapped[float] = mapped_column(Float, nullable=False)
    reinvested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    # Relationships
    stock: Mapped["Stock"] = relationship(back_populates="dividends")  # noqa: F821
