"""Decision audit service — Tier 2 metrics recording.

Records every executed/confirmed draft as a DecisionAudit row for
P&L tracking at 30/90/365-day intervals (decision 16).

Usage:
    from app.services.decision_audit_service import record_decision
    record_decision(db, draft=draft, trade=trade)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.datetime_utils import now
from app.models.decision_audit import DecisionAudit
from app.models.draft import Draft
from app.models.trade import Trade

logger = logging.getLogger(__name__)


def record_decision(
    db: Session,
    *,
    draft: Draft,
    trade: Optional[Trade] = None,
    approved_by: str = "user",
    additional: Optional[dict[str, Any]] = None,
) -> DecisionAudit:
    """Record a decision audit entry when a draft is executed/confirmed.

    Args:
        draft: The executed draft
        trade: Optional Trade that was created from the draft
        approved_by: Who approved the draft (default "user")
        additional: Extra fields to merge into the record

    Returns:
        The created DecisionAudit row.
    """
    action = draft.side  # BUY | SELL
    executed_price = trade.price if trade else (draft.target_price or None)

    entry = DecisionAudit(
        draft_id=draft.id,
        approved_at=now(),
        approved_by=approved_by,
        stock_code=draft.code,
        action=action,
        target_price=draft.target_price or None,
        executed_price=executed_price,
        quantity=trade.quantity if trade else draft.suggested_quantity,
        # Status fields are left as None — filled by periodic refresh job
        status_30d=None,
        status_90d=None,
        status_365d=None,
        benchmark_diff_pct=None,
        thesis_status_now=getattr(draft, "thesis_status", None),
    )
    db.add(entry)
    db.flush()
    logger.info(
        "decision_audit: recorded draft_id=%s code=%s action=%s",
        draft.id, draft.code, action,
    )
    return entry
