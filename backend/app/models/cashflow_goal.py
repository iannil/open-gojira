from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.core.datetime_utils import now


class CashflowGoal(Base):
    """Singleton (id=1) — 自动驾驶舱的"导航目标" + 投资组合设置。

    存的是用户输入；加权 DYR、年化被动现金流、目标进度由 cashflow_service
    在读取时基于当前持仓与估值动态计算，不入库。

    Cashflow fields:
    - annual_expense: 年度开销基线（元）
    - goal_multiple:  目标倍数，默认 15×（文档建议 10–20×）
    - currency:       预留多币种支持，默认 CNY
    - notes:          自由文本备注

    Portfolio settings (merged from portfolio_settings):
    - cash_reserve: 待入场的现金子弹（元），用于计算空仓比与组合加权股息率
    - target_weighted_dyr: 目标组合加权股息率（小数，默认 0.045 = 4.5%）
    - position_plan_json: 仓位计划 JSON（可选）
    - current_index_pe_pct: 当前大盘PE百分位（手动维护）
    - quadrant_targets_json: 象限目标配置 JSON（可选）
    """

    __tablename__ = "cashflow_goals"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=False, default=1
    )
    annual_expense: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    goal_multiple: Mapped[float] = mapped_column(Float, nullable=False, default=15.0)
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="CNY")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Portfolio settings fields
    cash_reserve: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    target_weighted_dyr: Mapped[float] = mapped_column(Float, nullable=False, default=0.045)
    position_plan_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_index_pe_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    quadrant_targets_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, onupdate=func.now(), nullable=True
    )
