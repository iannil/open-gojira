"""Research theme — investment research subject for serenity-skill workflow.

Distinct from `Theme` (macro portfolio allocation bucket).
ResearchTheme is a specific research subject like "AI 半导体" / "CPO" / "HBM".
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.core.datetime_utils import now


class ResearchTheme(Base):
    """A serenity research subject (specific direction, not macro theme).

    Field semantics:
    - name: research subject (e.g. "AI 半导体")
    - market: A_SHARE / HK / US / TW
    - auto_refresh_freq: manual / weekly / monthly (Q6 trigger config)
    - last_run_status: completed / failed / running — Q12 scheduler skips 'failed'
    - parent_theme_id: optional FK to Theme (macro line, e.g. "科技安全")
    """

    __tablename__ = "research_themes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    market: Mapped[str] = mapped_column(String, nullable=False, default="A_SHARE")
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="active", index=True
    )
    auto_refresh_freq: Mapped[str] = mapped_column(
        String, nullable=False, default="manual"
    )

    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )
    last_run_status: Mapped[str | None] = mapped_column(String, nullable=True)
    last_run_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    parent_theme_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("themes.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, onupdate=func.now(), nullable=True
    )
