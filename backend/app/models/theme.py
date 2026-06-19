"""Theme model — investment theme (投资主线)."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.core.datetime_utils import now


class Theme(Base):
    """Investment theme (投资主线) — top-down macro category.

    Maps to invest2.md "安全主线": 能源安全, 资源安全, 金融安全, 粮食安全.
    Each theme has a target portfolio allocation weight.
    """

    __tablename__ = "themes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_weight_pct: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, onupdate=func.now(), nullable=True
    )
