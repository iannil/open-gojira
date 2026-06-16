"""Research claim — structured breakdown of failure_conditions / next_steps.

Phase 2 #9 (Q19, 2026-06-16): LLM now outputs structured claims instead of
bare text strings. Each claim has 4 core fields (subject / predicate /
signal / outcome) plus reverse-link metadata (stock_codes / layer_index).

Why: bare text failure_conditions_md is hard to monitor or render. With
structured claims, UI can display cards consistently, and future Phase 2 #9
"monitor" stage can read the `signal` field as a metric key directly.

Old `ResearchRun.failure_conditions_md` is kept as derived fallback for
backward compatibility (UI shows md when no claims exist, e.g. legacy runs).
"""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ResearchClaim(Base):
    """One structured failure_condition OR next_step row.

    `type` discriminates:
    - "failure_condition": what scenario invalidates the thesis
    - "next_step": what user should verify to confirm/deny the thesis

    Both share the same 4-field core (subject/predicate/signal/outcome)
    because the semantic structure is isomorphic — see Q2 grill decision.
    """

    __tablename__ = "research_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    research_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("research_runs.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # "failure_condition" | "next_step"

    position: Mapped[int] = mapped_column(Integer, nullable=False)
    # Original list ordering (0-based)

    # ── Core 4 fields ───────────────────────────────────────────────────
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    # 主体 — what entity the claim is about
    # e.g. "银行IT预算" / "央行数字人民币运营数据"

    predicate: Mapped[str] = mapped_column(Text, nullable=False)
    # 动作/事件 — what happens to the subject
    # e.g. "大幅缩减" / "跟踪"

    signal: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 可观察信号 — measurable signal tied to the claim (nullable; LLM may omit)
    # e.g. "订单下滑超20%" / "钱包开立数"

    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    # 后果/验证目标 — what breaks (failure) or what gets confirmed (next_step)
    # e.g. "信创替代进度明显放缓" / "验证第4层芯片需求增速"

    # ── Reverse-link metadata ──────────────────────────────────────────
    stock_codes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON array of A-share 6-digit codes mentioned in the claim
    # e.g. '["300348", "300674"]'
    # Empty array "[]" when no specific companies cited.

    layer_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Value chain layer 1-8 the claim affects (nullable when not applicable)
