from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.core.datetime_utils import now


class AuditLog(Base):
    """自动驾驶舱"黑匣子" —— 只记关键事件，事后复盘只读。

    与旧的 `action_logs` 表并存到 Step 4 才删除；新代码统一写本表。

    设计要点：结构化字段，便于按"对象 × 事件"过滤。

    entity_type: plan | draft | holding | alert | cashflow_goal | stock
    event:       created | updated | deleted | triggered | invalidated
                 | executed | filled | acked | gate_passed | gate_failed
    actor:       user | scheduler | evaluator | system
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    entity_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    event: Mapped[str] = mapped_column(String, nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String, nullable=False, default="system")
    stock_code: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    summary: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now(), index=True
    )
