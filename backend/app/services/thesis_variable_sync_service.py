"""Thesis variable sync service — auto-populates thesis variables from stored
financial data for held stocks.

T6.1 refactor: templates now live in the BusinessPattern table (seeded at startup
by builtin_seeder). The previous module-level ``THESIS_VARIABLE_TEMPLATES`` /
``VARIABLE_TO_COLUMN`` constants have been replaced:
- ``THESIS_VARIABLE_TEMPLATES`` → ``BusinessPattern.thesis_variables_json`` (DB)
- ``VARIABLE_TO_COLUMN`` → kept here, keyed by pattern **name** (only '银行' has
  lixinger-source variables today; other patterns are all 'manual')

A Stock must have ``business_pattern_id`` set (via auto-inference or manual
override) to participate in sync. Stocks without a pattern are skipped with
reason='no_pattern'.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.financial import FinancialStatement
from app.models.stock import Stock
from app.services.business_pattern_service import get_pattern

logger = logging.getLogger(__name__)

# ── Pattern name → (variable_name → FinancialStatement column) ────────
# Only variables with source "lixinger" are mapped here.
# Variables with source "manual" are left untouched (user-entered).
#
# Note: keyed by BusinessPattern.name (was: Stock.industry string).
# When adding a new lixinger-source variable, also update builtin_seeder.py
# to mark the variable as source='lixinger' in BUILTIN_BUSINESS_PATTERNS.

VARIABLE_TO_COLUMN: dict[str, dict[str, str]] = {
    "银行": {
        "不良贷款率": "npl_ratio",
        "拨备覆盖率": "provision_coverage_ratio",
        "净息差": "net_interest_margin",
        "核心一级资本充足率": "core_tier1_car",
    },
}


def get_template_for_pattern(db: Session, pattern_id: int | None) -> list[dict]:
    """Return the thesis variable template for a BusinessPattern id.

    Empty list if pattern_id is None or pattern has no thesis_variables_json.
    """
    if pattern_id is None:
        return []
    pattern = get_pattern(db, pattern_id)
    if pattern is None or not pattern.thesis_variables_json:
        return []
    try:
        data = json.loads(pattern.thesis_variables_json)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        logger.warning(
            "Failed to parse thesis_variables_json for pattern %s", pattern_id
        )
        return []


# ── Core sync logic ─────────────────────────────────────────────────────


def _latest_stmt(db: Session, stock_code: str) -> Optional[FinancialStatement]:
    return (
        db.query(FinancialStatement)
        .filter(
            FinancialStatement.stock_code == stock_code,
            FinancialStatement.report_type == "annual",
        )
        .order_by(FinancialStatement.report_date.desc())
        .limit(1)
        .first()
    )


def _current_variables(stock: Stock) -> list[dict]:
    if not stock.thesis_variables_json:
        return []
    try:
        return json.loads(stock.thesis_variables_json)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse thesis_variables_json for %s", stock.code)
        return []


def _set_variables(stock: Stock, variables: list[dict]) -> None:
    stock.thesis_variables_json = json.dumps(variables, ensure_ascii=False)


def _pattern_name(db: Session, pattern_id: int | None) -> str | None:
    if pattern_id is None:
        return None
    pattern = get_pattern(db, pattern_id)
    return pattern.name if pattern else None


def sync_stock(
    db: Session,
    stock_code: str,
    *,
    audit: bool = True,
) -> dict:
    """Sync thesis variables for a single stock from FinancialStatement.

    Returns a summary dict: {synced, skipped, errors}.
    """
    stock = db.get(Stock, stock_code)
    if stock is None:
        return {"synced": 0, "skipped": 0, "errors": 0, "reason": "no_stock"}

    if stock.business_pattern_id is None:
        return {"synced": 0, "skipped": 0, "errors": 0, "reason": "no_pattern"}

    template = get_template_for_pattern(db, stock.business_pattern_id)
    if not template:
        return {"synced": 0, "skipped": 0, "errors": 0, "reason": "no_template"}

    pattern_name = _pattern_name(db, stock.business_pattern_id)
    column_map = VARIABLE_TO_COLUMN.get(pattern_name or "", {})
    if not column_map:
        return {
            "synced": 0,
            "skipped": len(template),
            "errors": 0,
            "reason": "all_manual",
        }

    stmt = _latest_stmt(db, stock_code)
    if not stmt:
        return {"synced": 0, "skipped": len(template), "errors": 0, "reason": "no_financials"}

    current_vars = _current_variables(stock)
    current_by_name = {v["name"]: v for v in current_vars}
    synced = 0
    updated_keys: list[str] = []

    for tpl in template:
        if tpl.get("source") != "lixinger":
            continue
        var_name = tpl["name"]
        col_name = column_map.get(var_name)
        if not col_name:
            continue

        value = getattr(stmt, col_name, None)
        if value is None:
            continue

        existing = current_by_name.get(var_name, {})
        changed = existing.get("value") != value

        # v2 Q1' schema unification: write `value` (not `current_value`).
        # Preserve any existing threshold_*/direction/unit fields so that
        # user-entered thresholds survive sync re-runs. Other fields that
        # belong to the template are refreshed from tpl.
        merged: dict = {
            "name": var_name,
            "value": value,
            "unit": tpl.get("unit") or existing.get("unit"),
            "source": "lixinger",
            "synced_at": datetime.now(timezone.utc).isoformat()[:10],
        }
        # Preserve previously-set monitor fields (from manual edits or
        # legacy data). These are NOT managed by sync.
        for k in ("threshold_low", "threshold_high", "threshold_critical",
                  "direction", "target_condition"):
            if k in existing:
                merged[k] = existing[k]

        current_by_name[var_name] = merged
        synced += 1
        if changed:
            updated_keys.append(f"{var_name}={value}")

    if synced == 0:
        return {"synced": 0, "skipped": len(template), "errors": 0, "reason": "no_values"}

    # Ensure manual variables are preserved
    for tpl in template:
        if tpl.get("source") == "manual" and tpl["name"] not in current_by_name:
            current_by_name[tpl["name"]] = {
                "name": tpl["name"],
                "value": None,
                "unit": tpl.get("unit"),
                "source": "manual",
            }

    _set_variables(stock, list(current_by_name.values()))

    if audit and updated_keys:
        from app.services import audit_log_service
        audit_log_service.write(
            db,
            entity_type="stock",
            entity_id=stock_code,
            event="thesis_variables_synced",
            actor="system",
            stock_code=stock_code,
            summary=f"synced {synced} variables: {', '.join(updated_keys[:5])}",
        )

    return {"synced": synced, "skipped": 0, "errors": 0, "updated": updated_keys}


def sync_all_held(db: Session) -> dict:
    """Sync thesis variables for all currently held stocks."""
    from app.models.holding import Holding

    codes = {
        r[0]
        for r in db.query(Holding.stock_code).filter(Holding.sell_date.is_(None)).all()
    }
    totals = {"stocks": 0, "synced": 0, "skipped": 0, "errors": 0}
    for code in sorted(codes):
        try:
            result = sync_stock(db, code)
            totals["stocks"] += 1
            totals["synced"] += result.get("synced", 0)
            totals["skipped"] += 1 if result.get("reason") else 0
        except Exception:
            logger.exception("thesis_variable_sync: failed for %s", code)
            totals["errors"] += 1
    db.commit()
    logger.info("thesis_variable_sync: %s", totals)
    return totals
