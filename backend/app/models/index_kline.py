"""Index Kline — 指数日 K 线 (沪深300等基准)。

Persists daily index kline data fetched from Lixinger, enabling
benchmark-relative performance calculations (Phase 6 Tier 2).
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.core.datetime_utils import now


class IndexKline(Base):
    """日频指数行情 (e.g. 沪深300 000300)。"""

    __tablename__ = "index_klines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    index_code: Mapped[str] = mapped_column(String, nullable=False)
    """指数代码, e.g. 000300 (沪深300), 000001 (上证指数)。"""

    date: Mapped[date] = mapped_column(Date, nullable=False)

    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now(), index=True
    )

    __table_args__ = (
        UniqueConstraint("index_code", "date", name="uq_index_kline_code_date"),
        Index("ix_index_kline_code_date", "index_code", "date"),
    )
