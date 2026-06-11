"""Cashflow-goal singleton service.

Only stores user-entered intent (annual_expense, goal_multiple, currency, notes).
Derived metrics (weighted DYR, current passive cashflow, goal progress) live in
the future `cashflow_service` that joins holdings + valuation snapshots.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.cashflow_goal import CashflowGoal

SINGLETON_ID = 1


def get_or_create(db: Session) -> CashflowGoal:
    row = db.get(CashflowGoal, SINGLETON_ID)
    if row is None:
        row = CashflowGoal(id=SINGLETON_ID)
        db.add(row)
        db.flush()
    return row


def update(
    db: Session,
    *,
    annual_expense: Optional[float] = None,
    goal_multiple: Optional[float] = None,
    currency: Optional[str] = None,
    notes: Optional[str] = None,
    cash_reserve: Optional[float] = None,
) -> CashflowGoal:
    row = get_or_create(db)
    if annual_expense is not None:
        row.annual_expense = annual_expense
    if goal_multiple is not None:
        row.goal_multiple = goal_multiple
    if currency is not None:
        row.currency = currency
    if notes is not None:
        row.notes = notes
    if cash_reserve is not None:
        row.cash_reserve = cash_reserve
    db.flush()
    return row


def target_annual_cashflow(goal: CashflowGoal) -> float:
    return float(goal.annual_expense) * float(goal.goal_multiple)
