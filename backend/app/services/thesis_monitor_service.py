"""Thesis monitor service — 论点变量阈值越界检测.

Extends thesis_variables_json with threshold definitions and checks for
breaches. Aligns with invest1 "第一性原理" — each industry has one core variable.

Expected thesis_variables_json format (v2 Q1' unified schema):
{
  "variables": [
    {"name": "煤油比", "value": 3.5, "unit": "倍",
     "threshold_low": 2.0, "threshold_critical": 1.5, "direction": "above"}
  ]
}

Phase 2 #9 阶段 B v2 (2026-06-16): adds check_claim_variables() which
monitors research_claim_variables rows (LLM-proposed from serenity claim
signals). Independent data source from thesis_variables_json.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Callable

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.holding import Holding
from app.models.stock import Stock

logger = logging.getLogger(__name__)


class ThesisAlert(BaseModel):
    code: str
    stock_name: str
    variable_name: str
    current_value: float | None
    threshold_type: str  # "warning" | "critical"
    threshold_value: float
    direction: str  # "above" | "below"
    message: str


def parse_thesis_variables(raw: str | None) -> list[dict]:
    """Parse thesis_variables_json into a list of variable dicts."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data.get("variables", [])
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse thesis_variables_json: %s", raw[:100])
    return []


def check_variable(var: dict) -> str | None:
    """Check a single thesis variable against its thresholds.

    Returns: "critical", "warning", or None (within range).
    """
    value = var.get("value")
    if value is None:
        return None

    direction = var.get("direction", "above")
    threshold_critical = var.get("threshold_critical")
    threshold_low = var.get("threshold_low")
    threshold_high = var.get("threshold_high")

    if direction == "above":
        # Value should stay above threshold
        if threshold_critical is not None and value < threshold_critical:
            return "critical"
        if threshold_low is not None and value < threshold_low:
            return "warning"
    elif direction == "below":
        # Value should stay below threshold
        if threshold_critical is not None and value > threshold_critical:
            return "critical"
        if threshold_high is not None and value > threshold_high:
            return "warning"

    return None


def check_held_stocks(db: Session) -> list[ThesisAlert]:
    """Check thesis variables for all open holdings."""
    holdings = list(
        db.execute(
            select(Holding).where(Holding.sell_date.is_(None))
        ).scalars().all()
    )

    alerts: list[ThesisAlert] = []

    for h in holdings:
        stock = db.get(Stock, h.stock_code)
        if not stock or not stock.thesis_variables_json:
            continue

        variables = parse_thesis_variables(stock.thesis_variables_json)
        for var in variables:
            severity = check_variable(var)
            if severity is None:
                continue

            name = var.get("name", "未知变量")
            value = var.get("value")
            direction = var.get("direction", "above")

            if severity == "critical":
                threshold = var.get("threshold_critical", 0)
            else:
                threshold = var.get("threshold_low") or var.get("threshold_high", 0)

            if direction == "above" and severity:
                message = f"{stock.name}({h.stock_code}) {name}={value}，低于{severity}阈值{threshold}"
            else:
                message = f"{stock.name}({h.stock_code}) {name}={value}，超过{severity}阈值{threshold}"

            alerts.append(ThesisAlert(
                code=h.stock_code,
                stock_name=stock.name or h.stock_code,
                variable_name=name,
                current_value=value,
                threshold_type=severity,
                threshold_value=threshold,
                direction=direction,
                message=message,
            ))

    return alerts


# ───────────────────────────────────────────────────────────────────────────
# Phase 2 #9 阶段 B v2 — check_claim_variables (research_claim_variables)
# ───────────────────────────────────────────────────────────────────────────

# Dedup window for re-alerting the same breach (v2 Q6'-B1).
ALERT_DEDUP_HOURS = 24 * 7  # 7 days


class ClaimVariableMonitorSummary(BaseModel):
    """Summary of one check_claim_variables run."""
    checked: int = 0
    breached: int = 0      # freshly alerted this run
    suppressed: int = 0    # breached but within 7-day dedup window
    skipped_no_data: int = 0  # source returned None (data missing)
    failed: int = 0        # source raised
    alerts: list[dict] = []  # for caller (audit log) consumption


def _last_n_financial_values(
    db: Session, stock_code: str, column_name: str, n: int,
) -> list[float]:
    """Pull the most recent N annual financial values for a column.

    Ordered newest-first. Returns [] if no rows or column unknown.
    """
    from app.models.financial import FinancialStatement

    if n < 1:
        return []
    col = getattr(FinancialStatement, column_name, None)
    if col is None:
        return []
    rows = db.execute(
        select(col).where(
            FinancialStatement.stock_code == stock_code,
            FinancialStatement.report_type == "annual",
        ).order_by(FinancialStatement.report_date.desc()).limit(n)
    ).scalars().all()
    return [v for v in rows if v is not None]


def _last_n_valuation_values(
    db: Session, stock_code: str, column_name: str, n: int,
) -> list[float]:
    from app.models.valuation import ValuationSnapshot

    if n < 1:
        return []
    col = getattr(ValuationSnapshot, column_name, None)
    if col is None:
        return []
    rows = db.execute(
        select(col).where(ValuationSnapshot.stock_code == stock_code)
        .order_by(ValuationSnapshot.date.desc()).limit(n)
    ).scalars().all()
    return [v for v in rows if v is not None]


def _last_n_kline_price_drops_52w(
    db: Session, stock_code: str, n: int,
) -> list[float]:
    """52-week price drop percentage, sampled at n monthly-ish intervals.

    For v1 simplicity: compute from the most recent N distinct kline
    snapshots' 52-week high-to-current ratio. n=1 → only latest.

    Returns ratios as positive percentages (0..100), drop = (high - now)/high.
    """
    from app.models.price_kline import PriceKline

    if n < 1:
        return []
    # Use latest kline. 52-week high = max high over the trailing 252 trading days.
    latest = db.execute(
        select(PriceKline).where(PriceKline.stock_code == stock_code)
        .order_by(PriceKline.date.desc()).limit(252)
    ).scalars().all()
    if not latest:
        return []
    latest.reverse()  # oldest first within window
    high_52w = max((k.high or 0) for k in latest)
    current = latest[-1].close or 0
    if high_52w <= 0 or current <= 0:
        return []
    drop_pct = (high_52w - current) / high_52w * 100
    return [round(drop_pct, 2)]


# Source routing table — (source_key, fetcher)
# Each fetcher: (db, stock_code, n) -> list[float] (newest first)
SOURCE_DISPATCH: dict[str, Callable[[Session, str, int], list[float]]] = {
    "financial:NIM": lambda db, s, n: _last_n_financial_values(db, s, "net_interest_margin", n),
    "financial:NPL": lambda db, s, n: _last_n_financial_values(db, s, "npl_ratio", n),
    "financial:revenue_growth": lambda db, s, n: _last_n_financial_values(db, s, "revenue_growth", n),
    "financial:margin": lambda db, s, n: _last_n_financial_values(db, s, "gross_margin", n),
    "valuation:PE_percentile": lambda db, s, n: _last_n_valuation_values(db, s, "pe_percentile_10y", n),
    "valuation:PB_percentile": lambda db, s, n: _last_n_valuation_values(db, s, "pb_percentile_10y", n),
    "kline:price_drop_52w": _last_n_kline_price_drops_52w,
}


def _check_breach(
    values: list[float], threshold: float, breach_when: str,
    window_periods: int | None,
) -> bool:
    """Return True if breached per breach_when semantics + window.

    breach_when="lt": alert when value < threshold
    breach_when="gt": alert when value > threshold

    window_periods=None or 1: single-point (latest value) breach.
    window_periods≥2: require consecutive N periods all breached.
    """
    n = window_periods or 1
    if len(values) < n:
        return False  # insufficient data
    recent = values[:n]
    for v in recent:
        if breach_when == "lt" and v >= threshold:
            return False
        if breach_when == "gt" and v <= threshold:
            return False
    return True


def check_claim_variables(db: Session) -> ClaimVariableMonitorSummary:
    """Monitor all active research_claim_variables tied to open holdings.

    v2 decisions:
      - Q-new holdings filter: INNER JOIN Holding WHERE sell_date IS NULL
      - Q-new per-var try/except isolation
      - Q6'-B1 dedup: skip if last_alerted_at within ALERT_DEDUP_HOURS
      - Q-new multi-period: window_periods > 1 → check consecutive N breach
      - Q-new audit + EventBus: write audit_log + emit ThesisAlertTriggered
        on each fresh breach (caller handles notification dispatch via handler).

    Returns summary dict for caller observability. Side effects:
      - On fresh breach: UPDATE last_alerted_at = now(); emit event.
      - audit_log writes are performed in the EventBus handler so that
        notification_service.send() and audit happen together. This
        function only emits the event + updates last_alerted_at.
    """
    from app.core.datetime_utils import now
    from app.core.events import bus, ThesisAlertTriggered
    from app.models.research_claim_variable import ResearchClaimVariable

    summary = ClaimVariableMonitorSummary()

    # Active claim vars on currently-open holdings (v2 Q-new holdings filter).
    rows = db.execute(
        select(ResearchClaimVariable, Stock, Holding)
        .join(Stock, Stock.code == ResearchClaimVariable.stock_code)
        .join(Holding, Holding.stock_code == ResearchClaimVariable.stock_code)
        .where(
            ResearchClaimVariable.status == "active",
            Holding.sell_date.is_(None),
        )
    ).all()

    summary.checked = len(rows)
    dedup_cutoff = now() - timedelta(hours=ALERT_DEDUP_HOURS)

    for cv, stock, _holding in rows:
        fetcher = SOURCE_DISPATCH.get(cv.source)
        if fetcher is None:
            logger.warning(
                "check_claim_variables: unknown source=%r for cv_id=%s",
                cv.source, cv.id,
            )
            summary.failed += 1
            continue

        try:
            n = cv.window_periods or 1
            values = fetcher(db, cv.stock_code, n)
        except Exception:
            logger.exception(
                "check_claim_variables: fetch failed cv_id=%s source=%s stock=%s",
                cv.id, cv.source, cv.stock_code,
            )
            summary.failed += 1
            continue

        if not values:
            summary.skipped_no_data += 1
            continue

        n_required = cv.window_periods or 1
        if len(values) < n_required:
            # v2 Q-window: insufficient history for multi-period check
            summary.skipped_no_data += 1
            continue

        try:
            breached = _check_breach(
                values, cv.threshold_critical, cv.breach_when, cv.window_periods,
            )
        except Exception:
            logger.exception(
                "check_claim_variables: breach check failed cv_id=%s", cv.id,
            )
            summary.failed += 1
            continue

        if not breached:
            continue

        # Dedup: skip if alerted recently (v2 Q6'-B1).
        if cv.last_alerted_at is not None and cv.last_alerted_at > dedup_cutoff:
            summary.suppressed += 1
            continue

        latest = values[0]
        message = _format_alert_message(
            stock_name=stock.name or cv.stock_code,
            stock_code=cv.stock_code,
            variable_name=cv.variable_name,
            value=latest,
            threshold=cv.threshold_critical,
            breach_when=cv.breach_when,
            window=cv.window_periods,
            unit=cv.unit,
        )

        # Update dedup stamp + flush so subsequent dedup checks see it.
        cv.last_alerted_at = now()
        db.add(cv)
        db.flush()

        bus.emit(ThesisAlertTriggered(
            claim_var_id=cv.id,
            code=cv.stock_code,
            stock_name=stock.name or cv.stock_code,
            variable_name=cv.variable_name,
            current_value=latest,
            threshold_value=cv.threshold_critical,
            breach_when=cv.breach_when,
            window_periods=cv.window_periods,
            message=message,
        ))

        summary.breached += 1
        summary.alerts.append({
            "claim_var_id": cv.id,
            "stock_code": cv.stock_code,
            "stock_name": stock.name or cv.stock_code,
            "variable_name": cv.variable_name,
            "current_value": latest,
            "threshold": cv.threshold_critical,
            "breach_when": cv.breach_when,
            "window_periods": cv.window_periods,
            "message": message,
        })

    db.commit()

    logger.info(
        "check_claim_variables: checked=%s breached=%s suppressed=%s no_data=%s failed=%s",
        summary.checked, summary.breached, summary.suppressed,
        summary.skipped_no_data, summary.failed,
    )
    return summary


def _format_alert_message(
    *, stock_name: str, stock_code: str, variable_name: str,
    value: float, threshold: float, breach_when: str,
    window: int | None, unit: str | None,
) -> str:
    comparator = "<" if breach_when == "lt" else ">"
    win_str = f"连续 {window} 期 " if (window or 1) > 1 else ""
    unit_str = unit or ""
    return (
        f"{stock_name}({stock_code}) {variable_name}={value}{unit_str},"
        f" {win_str}{comparator} {threshold}{unit_str}"
    )
