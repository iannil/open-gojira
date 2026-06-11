"""Thesis variable sync service — auto-populates thesis variables from stored
financial data for held stocks.

Maps industry-specific thesis variables to FinancialStatement columns and
writes current values into ``Stock.thesis_variables_json``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.financial import FinancialStatement
from app.models.stock import Stock

logger = logging.getLogger(__name__)

# ── Industry → (variable_name → FinancialStatement column) ──────────────
# Only variables with source "lixinger" are mapped here.
# Variables with source "manual" are left untouched.

VARIABLE_TO_COLUMN: dict[str, dict[str, str]] = {
    "银行": {
        "不良贷款率": "npl_ratio",
        "拨备覆盖率": "provision_coverage_ratio",
        "净息差": "net_interest_margin",
        "核心一级资本充足率": "core_tier1_car",
    },
}

# ── Industry variable templates (kept from previous version) ─────────────

THESIS_VARIABLE_TEMPLATES: dict[str, list[dict]] = {
    "银行": [
        {"name": "不良贷款率", "unit": "%", "source": "lixinger"},
        {"name": "拨备覆盖率", "unit": "%", "source": "lixinger"},
        {"name": "净息差", "unit": "%", "source": "lixinger"},
        {"name": "核心一级资本充足率", "unit": "%", "source": "lixinger"},
    ],
    "煤化工": [
        {"name": "煤油比", "unit": "", "source": "manual"},
        {"name": "烯烃吨成本", "unit": "元/吨", "source": "manual"},
        {"name": "产能利用率", "unit": "%", "source": "manual"},
    ],
    "磷化工": [
        {"name": "磷矿价格", "unit": "元/吨", "source": "manual"},
        {"name": "磷矿石自给率", "unit": "%", "source": "manual"},
        {"name": "磷酸一铵价格", "unit": "元/吨", "source": "manual"},
    ],
    "黄金": [
        {"name": "全球央行净买入", "unit": "吨", "source": "manual"},
        {"name": "上海金交所金价", "unit": "元/克", "source": "manual"},
        {"name": "门店数量", "unit": "家", "source": "manual"},
    ],
    "药品零售": [
        {"name": "门店数量", "unit": "家", "source": "manual"},
        {"name": "同店增长率", "unit": "%", "source": "manual"},
        {"name": "处方外配比例", "unit": "%", "source": "manual"},
    ],
    "铝业": [
        {"name": "电价成本", "unit": "元/度", "source": "manual"},
        {"name": "氧化铝价格", "unit": "元/吨", "source": "manual"},
        {"name": "电解铝产能", "unit": "万吨", "source": "manual"},
    ],
}


def get_template_for_industry(industry: str | None) -> list[dict]:
    if not industry:
        return []
    return THESIS_VARIABLE_TEMPLATES.get(industry, [])


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


def sync_stock(
    db: Session,
    stock_code: str,
    *,
    audit: bool = True,
) -> dict:
    """Sync thesis variables for a single stock.

    Returns a summary dict: {synced, skipped, errors}.
    """
    stock = db.get(Stock, stock_code)
    if not stock or not stock.industry:
        return {"synced": 0, "skipped": 0, "errors": 0, "reason": "no_stock_or_industry"}

    template = get_template_for_industry(stock.industry)
    if not template:
        return {"synced": 0, "skipped": 0, "errors": 0, "reason": "no_template"}

    column_map = VARIABLE_TO_COLUMN.get(stock.industry, {})
    if not column_map:
        return {"synced": 0, "skipped": len(template), "errors": 0, "reason": "all_manual"}

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
        changed = existing.get("current_value") != value

        current_by_name[var_name] = {
            "name": var_name,
            "current_value": value,
            "target_condition": existing.get("target_condition"),
            "unit": tpl.get("unit"),
            "source": "lixinger",
            "synced_at": datetime.now(timezone.utc).isoformat()[:10],
        }
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
                "current_value": None,
                "target_condition": None,
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
