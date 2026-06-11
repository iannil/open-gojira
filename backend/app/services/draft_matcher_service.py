"""Draft matcher service — 智能回填建议.

When user marks a draft as executed, auto-suggest how to update holdings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.draft import Draft
from app.models.holding import Holding

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BackfillSuggestion:
    action: str  # "add_to_existing" | "create_new" | "reduce_position" | "close_position"
    holding_id: int | None
    stock_code: str
    side: str
    suggested_price: float | None
    suggested_quantity: int | None
    message: str

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "holding_id": self.holding_id,
            "stock_code": self.stock_code,
            "side": self.side,
            "suggested_price": self.suggested_price,
            "suggested_quantity": self.suggested_quantity,
            "message": self.message,
        }


def suggest(db: Session, draft_id: int) -> BackfillSuggestion | None:
    """Generate a backfill suggestion for a draft."""
    draft = db.get(Draft, draft_id)
    if not draft:
        return None

    code = draft.code

    if draft.side == "BUY":
        existing = db.execute(
            select(Holding).where(
                Holding.stock_code == code,
                Holding.sell_date.is_(None),
            )
        ).scalar_one_or_none()

        if existing:
            return BackfillSuggestion(
                action="add_to_existing",
                holding_id=existing.id,
                stock_code=code,
                side="BUY",
                suggested_price=None,
                suggested_quantity=None,
                message=f"已有持仓 (ID={existing.id}, {existing.quantity}股)，建议加仓",
            )
        return BackfillSuggestion(
            action="create_new",
            holding_id=None,
            stock_code=code,
            side="BUY",
            suggested_price=None,
            suggested_quantity=None,
            message=f"新建持仓：{code}",
        )

    if draft.side == "SELL":
        existing = db.execute(
            select(Holding).where(
                Holding.stock_code == code,
                Holding.sell_date.is_(None),
            )
        ).scalar_one_or_none()

        if not existing:
            return BackfillSuggestion(
                action="close_position",
                holding_id=None,
                stock_code=code,
                side="SELL",
                suggested_price=None,
                suggested_quantity=0,
                message=f"未找到 {code} 的持仓记录",
            )

        if draft.reduce_pct_of_position and draft.reduce_pct_of_position < 1.0:
            sell_qty = int(existing.quantity * draft.reduce_pct_of_position)
            return BackfillSuggestion(
                action="reduce_position",
                holding_id=existing.id,
                stock_code=code,
                side="SELL",
                suggested_price=None,
                suggested_quantity=sell_qty,
                message=f"建议减仓 {sell_qty} 股 (持仓 {existing.quantity} × {draft.reduce_pct_of_position:.0%})",
            )

        return BackfillSuggestion(
            action="close_position",
            holding_id=existing.id,
            stock_code=code,
            side="SELL",
            suggested_price=None,
            suggested_quantity=existing.quantity,
            message=f"建议清仓 {existing.quantity} 股",
        )

    return None
