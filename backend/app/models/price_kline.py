from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.core.datetime_utils import now


class PriceKline(Base):
    """Daily K-line (candlestick) data, cached from Lixinger.

    Stored per (stock_code, date, freq) where freq is 'day' / 'week' / 'month'.
    Adjusted with Lixinger's forward-adjustment (lxr_fc_rights) by default.
    """

    __tablename__ = "price_klines"
    __table_args__ = (
        UniqueConstraint("stock_code", "date", "freq", name="uq_price_kline"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String, nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    freq: Mapped[str] = mapped_column(String, nullable=False, default="day")

    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    turnover: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now()
    )
