"""BusinessPattern service — CRUD + auto-inference logic.

Pure functions: infer_business_pattern(industry, patterns) for testability.
DB-bound: list/get/create/update/delete + infer_for_stock + infer_all_stocks.

Design (see docs/progress, T6.1):
- Context-type, not decision-type.
- Auto-inference: 1:1 → set; 1:0 or 1:多 → null (force manual).
- inferred_at != NULL protects against user override re-inference.
- Builtin patterns: name + first_principle + power_tier + thesis_variables +
  lixinger_industries + source_ref + theme_id read-only via service layer.
  description is editable.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.business_pattern import BusinessPattern
from app.models.stock import Stock

logger = logging.getLogger(__name__)


# ── Pure-function inference (unit-testable, no DB) ─────────────────────


def infer_business_pattern(
    industry: Optional[str], patterns: list[BusinessPattern]
) -> Optional[int]:
    """Return the unique BusinessPattern.id whose lixinger_industries contains industry.

    Returns None when:
    - industry is None/empty
    - no pattern covers the industry (1:0)
    - 2+ patterns cover the industry (1:多 ambiguous → force manual)
    """
    if not industry:
        return None
    matches: list[int] = []
    for p in patterns:
        if not p.lixinger_industries_json:
            continue
        try:
            industries = json.loads(p.lixinger_industries_json)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(industries, list):
            continue
        if industry in industries:
            matches.append(p.id)
    if len(matches) == 1:
        return matches[0]
    return None


# ── DB-bound operations ────────────────────────────────────────────────


def list_patterns(db: Session, *, include_builtin_only: bool = False) -> list[BusinessPattern]:
    """List all business patterns, ordered by name."""
    q = db.query(BusinessPattern)
    if include_builtin_only:
        q = q.filter(BusinessPattern.is_builtin.is_(True))
    return q.order_by(BusinessPattern.name).all()


def get_pattern(db: Session, pattern_id: int) -> Optional[BusinessPattern]:
    return db.query(BusinessPattern).filter(BusinessPattern.id == pattern_id).first()


def get_pattern_by_name(db: Session, name: str) -> Optional[BusinessPattern]:
    return db.query(BusinessPattern).filter(BusinessPattern.name == name).first()


def _serialize_thesis_variables(pattern: BusinessPattern) -> list[dict]:
    if not pattern.thesis_variables_json:
        return []
    try:
        data = json.loads(pattern.thesis_variables_json)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _serialize_lixinger_industries(pattern: BusinessPattern) -> list[str]:
    if not pattern.lixinger_industries_json:
        return []
    try:
        data = json.loads(pattern.lixinger_industries_json)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def create_pattern(
    db: Session,
    *,
    name: str,
    theme_id: int | None = None,
    description: str | None = None,
    first_principle_variable: str | None = None,
    power_tier_baseline: int = 0,
    thesis_variables: list[dict] | None = None,
    lixinger_industries: list[str] | None = None,
    source_ref: str | None = None,
    is_builtin: bool = False,
) -> BusinessPattern:
    """Create a new BusinessPattern. User-created patterns cannot carry source_ref."""
    if not is_builtin and source_ref:
        raise ValueError(
            "source_ref is reserved for builtin patterns; clear it for user-created."
        )
    pattern = BusinessPattern(
        name=name,
        theme_id=theme_id,
        description=description,
        first_principle_variable=first_principle_variable,
        power_tier_baseline=power_tier_baseline,
        thesis_variables_json=(
            json.dumps(thesis_variables or [], ensure_ascii=False)
        ),
        lixinger_industries_json=(
            json.dumps(lixinger_industries or [], ensure_ascii=False)
        ),
        source_ref=source_ref,
        is_builtin=is_builtin,
    )
    db.add(pattern)
    db.flush()
    db.refresh(pattern)
    return pattern


# Builtin pattern core fields — service layer refuses to modify these on builtin rows
_BUILTIN_LOCKED_FIELDS = frozenset({
    "name",
    "first_principle_variable",
    "power_tier_baseline",
    "thesis_variables_json",
    "lixinger_industries_json",
    "source_ref",
    "theme_id",
    "is_builtin",
})


def update_pattern(
    db: Session,
    pattern_id: int,
    *,
    name: str | None = None,
    theme_id: int | None = None,
    description: str | None = None,
    first_principle_variable: str | None = None,
    power_tier_baseline: int | None = None,
    thesis_variables: list[dict] | None = None,
    lixinger_industries: list[str] | None = None,
    source_ref: str | None = None,
) -> Optional[BusinessPattern]:
    """Update a BusinessPattern. Builtin rows: only description editable."""
    pattern = get_pattern(db, pattern_id)
    if pattern is None:
        return None

    if pattern.is_builtin:
        # Builtin rows: only description can be edited
        if any(
            v is not None
            for v in (
                name,
                theme_id,
                first_principle_variable,
                power_tier_baseline,
                thesis_variables,
                lixinger_industries,
                source_ref,
            )
        ):
            raise ValueError(
                "Builtin pattern core fields are read-only; only description is editable. "
                "Duplicate the pattern as user-created to customize."
            )
        if description is not None:
            pattern.description = description
    else:
        if name is not None:
            pattern.name = name
        if theme_id is not None:
            pattern.theme_id = theme_id
        if description is not None:
            pattern.description = description
        if first_principle_variable is not None:
            pattern.first_principle_variable = first_principle_variable
        if power_tier_baseline is not None:
            pattern.power_tier_baseline = power_tier_baseline
        if thesis_variables is not None:
            pattern.thesis_variables_json = json.dumps(
                thesis_variables, ensure_ascii=False
            )
        if lixinger_industries is not None:
            pattern.lixinger_industries_json = json.dumps(
                lixinger_industries, ensure_ascii=False
            )
        if source_ref is not None:
            pattern.source_ref = source_ref

    db.flush()
    db.refresh(pattern)
    return pattern


def delete_pattern(db: Session, pattern_id: int) -> bool:
    """Delete a BusinessPattern. Refuses builtin rows.

    Stocks referencing this pattern will have their business_pattern_id cleared
    (ON DELETE SET NULL behavior).
    """
    pattern = get_pattern(db, pattern_id)
    if pattern is None:
        return False
    if pattern.is_builtin:
        raise ValueError(
            "Builtin patterns cannot be deleted. Archive by clearing description instead."
        )
    # Clear references on stocks (set to NULL)
    db.query(Stock).filter(Stock.business_pattern_id == pattern_id).update(
        {Stock.business_pattern_id: None, Stock.business_pattern_inferred_at: None},
        synchronize_session=False,
    )
    db.delete(pattern)
    db.flush()
    return True


# ── Auto-inference on Stock ────────────────────────────────────────────


def infer_for_stock(
    db: Session,
    stock_code: str,
    *,
    force: bool = False,
) -> Optional[int]:
    """Re-infer business_pattern_id for a stock from its industry.

    Skips if Stock.business_pattern_inferred_at is None and not force
    (NULL means user has manually overridden — we protect their override).

    Returns the new pattern_id (may be None if ambiguous / no match).
    """
    stock = db.get(Stock, stock_code)
    if stock is None:
        return None

    if not force and stock.business_pattern_inferred_at is None and stock.business_pattern_id is not None:
        # User override: protect
        return stock.business_pattern_id

    patterns = list_patterns(db)
    new_id = infer_business_pattern(stock.industry, patterns)
    stock.business_pattern_id = new_id
    stock.business_pattern_inferred_at = (
        datetime.now(timezone.utc) if new_id is not None else None
    )
    db.flush()
    return new_id


def override_stock_pattern(
    db: Session,
    stock_code: str,
    pattern_id: int | None,
) -> Optional[Stock]:
    """User-driven override. Sets inferred_at=None to mark 'manual'."""
    stock = db.get(Stock, stock_code)
    if stock is None:
        return None
    if pattern_id is not None:
        # Verify the pattern exists
        if get_pattern(db, pattern_id) is None:
            raise ValueError(f"BusinessPattern {pattern_id} does not exist")
    stock.business_pattern_id = pattern_id
    stock.business_pattern_inferred_at = None  # NULL = manual override
    db.flush()
    db.refresh(stock)
    return stock


def infer_all_stocks(db: Session, *, force: bool = False) -> dict:
    """Batch re-infer for all stocks. Returns summary.

    By default skips stocks with business_pattern_inferred_at IS NULL
    (user overrides). With force=True, re-infers all stocks.

    Returns: {total, updated, protected, cleared}
    """
    stocks = db.query(Stock).all()
    patterns = list_patterns(db)
    total = len(stocks)
    updated = 0
    protected = 0
    cleared = 0
    for stock in stocks:
        if (
            not force
            and stock.business_pattern_inferred_at is None
            and stock.business_pattern_id is not None
        ):
            protected += 1
            continue
        new_id = infer_business_pattern(stock.industry, patterns)
        if new_id != stock.business_pattern_id:
            updated += 1
            if new_id is None:
                cleared += 1
            stock.business_pattern_id = new_id
            stock.business_pattern_inferred_at = (
                datetime.now(timezone.utc) if new_id is not None else None
            )
    db.flush()
    logger.info(
        "business_pattern_infer_all: total=%d updated=%d protected=%d cleared=%d",
        total, updated, protected, cleared,
    )
    return {
        "total": total,
        "updated": updated,
        "protected": protected,
        "cleared": cleared,
    }


def get_thesis_templates(db: Session, pattern_id: int) -> Optional[dict]:
    """Return thesis variable templates for a pattern (for 'load from template' UI)."""
    pattern = get_pattern(db, pattern_id)
    if pattern is None:
        return None
    return {
        "pattern_id": pattern.id,
        "pattern_name": pattern.name,
        "templates": _serialize_thesis_variables(pattern),
    }
