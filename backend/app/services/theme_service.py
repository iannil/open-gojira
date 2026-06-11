"""Theme service — investment theme exposure analysis.

Functions:
- get_theme_exposure(db) — portfolio weight grouped by stock's security_theme
- get_theme_targets(db) — target vs actual weights with drift warnings
- get_theme_coverage(db) — which themes have active plans
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.holding import Holding
from app.models.plan import Plan
from app.models.stock import Stock
from app.models.theme import Theme

logger = logging.getLogger(__name__)


def get_theme_exposure(db: Session) -> list[dict[str, Any]]:
    """Compute portfolio weight grouped by theme (from Stock.security_theme).

    Returns list of {"theme": str, "weight_pct": float, "value": float, "count": int, "stock_codes": list[str]}.
    Stocks without a security_theme are grouped under "未分类".
    """
    from app.services.holding_service import _get_cached_price

    # Get all holdings with their stocks
    holdings = (
        db.query(
            Stock.security_theme,
            Holding.quantity,
            Stock.code,
        )
        .join(Stock, Holding.stock_code == Stock.code)
        .filter(Holding.quantity > 0)
        .all()
    )

    if not holdings:
        return []

    # Group by theme
    theme_groups: dict[str, list[dict]] = {}
    total_value = 0.0

    for security_theme, quantity, stock_code in holdings:
        price = _get_cached_price(stock_code)
        if price is None:
            logger.warning("Price unavailable for %s, excluding from theme exposure", stock_code)
            continue
        value = float(quantity) * price
        total_value += value

        theme_key = security_theme if security_theme else "未分类"
        if theme_key not in theme_groups:
            theme_groups[theme_key] = []
        theme_groups[theme_key].append({"value": value, "code": stock_code})

    # Build result
    result = []
    for theme_name, items in theme_groups.items():
        theme_value = sum(item["value"] for item in items)
        theme_weight = (
            (theme_value / total_value * 100) if total_value > 0 else 0.0
        )
        result.append(
            {
                "theme": theme_name,
                "weight_pct": round(theme_weight, 2),
                "value": round(theme_value, 2),
                "count": len(items),
                "stock_codes": [item["code"] for item in items],
            }
        )

    # Sort by weight descending
    result.sort(key=lambda x: x["weight_pct"], reverse=True)
    return result


def get_theme_targets(db: Session) -> list[dict[str, Any]]:
    """Compare target vs actual theme weights.

    Returns list of {"theme": str, "target_pct": float, "actual_pct": float, "drift_pct": float, "warning": str | None}.
    """
    # Get all themes
    themes = db.query(Theme).order_by(Theme.name).all()

    # Get current exposure
    exposure = get_theme_exposure(db)
    exposure_map = {item["theme"]: item["weight_pct"] for item in exposure}

    # Build comparison
    result = []
    for theme in themes:
        actual_pct = exposure_map.get(theme.name, 0.0)
        target_pct = theme.target_weight_pct
        drift_pct = actual_pct - target_pct

        # Warning if drift > 5%
        warning = None
        if abs(drift_pct) > 5.0:
            direction = "超配" if drift_pct > 0 else "低配"
            warning = f"{direction} {abs(drift_pct):.1f}%"

        result.append(
            {
                "theme": theme.name,
                "target_pct": round(target_pct, 2),
                "actual_pct": round(actual_pct, 2),
                "drift_pct": round(drift_pct, 2),
                "warning": warning,
            }
        )

    # Sort by absolute drift descending
    result.sort(key=lambda x: abs(x["drift_pct"]), reverse=True)
    return result


def get_theme_coverage(db: Session) -> list[dict[str, Any]]:
    """Get which themes have active plans with candidates.

    Returns list of {"theme": str, "active_plan_count": int, "stock_codes": list[str]}.
    """
    from app.models.candidate import Candidate
    from app.models.stock import Stock

    # Get active plans with their candidates' stock codes
    plans_with_candidates = (
        db.query(Plan.name, Candidate.stock_code, Stock.security_theme)
        .join(Candidate, Candidate.plan_id == Plan.id)
        .join(Stock, Stock.code == Candidate.stock_code)
        .filter(Plan.status == "active", Candidate.status == "active")
        .all()
    )

    # Group by plan name
    plan_groups: dict[str, list[str]] = {}
    for plan_name, stock_code, _ in plans_with_candidates:
        if plan_name not in plan_groups:
            plan_groups[plan_name] = []
        plan_groups[plan_name].append(stock_code)

    # Build result
    result = []
    for plan_name, stock_codes in plan_groups.items():
        result.append(
            {
                "theme": plan_name,
                "active_plan_count": len(stock_codes),
                "stock_codes": stock_codes,
            }
        )

    # Sort by plan count descending
    result.sort(key=lambda x: x["active_plan_count"], reverse=True)
    return result


def list_themes(db: Session) -> list[Theme]:
    """List all themes."""
    return db.query(Theme).order_by(Theme.name).all()


def get_theme(db: Session, theme_id: int) -> Theme | None:
    """Get a single theme by ID."""
    return db.query(Theme).filter(Theme.id == theme_id).first()


def create_theme(
    db: Session,
    name: str,
    description: str | None = None,
    target_weight_pct: float = 0.0,
) -> Theme:
    """Create a new theme."""
    theme = Theme(
        name=name,
        description=description,
        target_weight_pct=target_weight_pct,
    )
    db.add(theme)
    db.flush()
    db.refresh(theme)
    return theme


def update_theme(
    db: Session,
    theme_id: int,
    name: str | None = None,
    description: str | None = None,
    target_weight_pct: float | None = None,
) -> Theme | None:
    """Update an existing theme."""
    theme = get_theme(db, theme_id)
    if not theme:
        return None

    if name is not None:
        theme.name = name
    if description is not None:
        theme.description = description
    if target_weight_pct is not None:
        theme.target_weight_pct = target_weight_pct

    db.flush()
    db.refresh(theme)
    return theme


def delete_theme(db: Session, theme_id: int) -> bool:
    """Delete a theme."""
    theme = get_theme(db, theme_id)
    if not theme:
        return False

    db.delete(theme)
    db.flush()
    return True
