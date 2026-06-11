"""Alert service — event-driven notifications.

Threshold-based rules (pe/pb/dyr/price cross) removed: Plan Evaluator covers
all threshold monitoring via ladder triggers. Only event-driven rules remain:
dividend_ex_date_near, financial_report_released, stop_profit.
"""

import logging
from datetime import datetime, timezone
from typing import Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.alert import AlertEvent, AlertRule
from app.models.holding import Holding
from app.models.stock import Stock
from app.schemas.alert import RULE_TYPES
from app.services.lixinger_client import LixingerError, get_lixinger_client
from app.core.events import bus, AlertTriggered

logger = logging.getLogger(__name__)


# ── Rule CRUD ─────────────────────────────────────────────────────────────


def list_rules(db: Session, enabled_only: bool = False) -> list[AlertRule]:
    q = db.query(AlertRule)
    if enabled_only:
        q = q.filter(AlertRule.enabled.is_(True))
    return q.order_by(AlertRule.id.asc()).all()


def create_rule(db: Session, data: dict) -> AlertRule:
    if data["rule_type"] not in RULE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown rule_type: {data['rule_type']}")
    if data.get("stock_code"):
        if not db.query(Stock).filter(Stock.code == data["stock_code"]).first():
            raise HTTPException(status_code=404, detail=f"Stock {data['stock_code']} not found")
    rule = AlertRule(
        rule_type=data["rule_type"],
        stock_code=data.get("stock_code"),
        params=data.get("params") or {},
        enabled=data.get("enabled", True),
        note=data.get("note"),
    )
    db.add(rule)
    db.flush()
    db.refresh(rule)
    return rule


def update_rule(db: Session, rule_id: int, data: dict) -> AlertRule:
    rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    for key in ("params", "enabled", "note"):
        if data.get(key) is not None:
            setattr(rule, key, data[key])
    db.flush()
    db.refresh(rule)
    return rule


def delete_rule(db: Session, rule_id: int) -> bool:
    rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
    if not rule:
        return False
    db.delete(rule)
    db.flush()
    return True


# ── Event listing / ack ───────────────────────────────────────────────────


def list_events(
    db: Session,
    acked: Optional[bool] = None,
    stock_code: Optional[str] = None,
    limit: int = 100,
) -> list[AlertEvent]:
    q = db.query(AlertEvent)
    if acked is not None:
        q = q.filter(AlertEvent.acked.is_(acked))
    if stock_code:
        q = q.filter(AlertEvent.stock_code == stock_code)
    return q.order_by(AlertEvent.fired_at.desc()).limit(limit).all()


def ack_event(db: Session, event_id: int) -> AlertEvent:
    ev = db.query(AlertEvent).filter(AlertEvent.id == event_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
    ev.acked = True
    ev.acked_at = _utcnow()
    db.flush()
    db.refresh(ev)
    return ev


def ack_all_events(db: Session) -> int:
    count = (
        db.query(AlertEvent)
        .filter(AlertEvent.acked.is_(False))
        .update({"acked": True, "acked_at": _utcnow()}, synchronize_session=False)
    )
    db.flush()
    return count


def unacked_count(db: Session) -> int:
    return db.query(AlertEvent).filter(AlertEvent.acked.is_(False)).count()


# ── Engine ────────────────────────────────────────────────────────────────


def _fetch_realtime(stock_codes: list[str]) -> dict[str, dict]:
    if not stock_codes:
        return {}
    try:
        client = get_lixinger_client()
        data = client.get_fundamentals(
            stock_codes=stock_codes,
            metrics=["pe_ttm", "pb", "sp", "dyr"],
        )
    except LixingerError:
        logger.warning("Lixinger fetch failed in alert engine", exc_info=True)
        return {}

    result: dict[str, dict] = {}
    for item in data:
        code = item.get("stockCode")
        if not code:
            continue
        result[code] = item
    return result


def _emit(
    db: Session,
    rule: AlertRule,
    *,
    title: str,
    detail: str,
    payload: dict,
    severity: str = "info",
) -> AlertEvent:
    event = AlertEvent(
        rule_id=rule.id,
        stock_code=rule.stock_code,
        rule_type=rule.rule_type,
        title=title,
        detail=detail,
        payload=payload,
        severity=severity,
    )
    db.add(event)
    try:
        from app.services import audit_log_service
        audit_log_service.write(
            db,
            entity_type="alert",
            event=rule.rule_type,
            summary=title,
            stock_code=rule.stock_code,
            payload=payload,
            actor="scheduler",
        )
    except Exception:  # noqa: BLE001
        logger.exception("audit_log on alert failed")
    db.flush()
    try:
        bus.emit_async(AlertTriggered(
            alert_event_id=event.id,
            rule_id=rule.id,
            stock_code=rule.stock_code,
            title=title,
            severity=severity,
        ))
    except Exception:
        logger.exception("EventBus emit_async AlertTriggered failed")
    return event


def _eval_dividend_ex_date_near(db: Session, rule: AlertRule) -> Optional[AlertEvent]:
    if not rule.stock_code:
        return None
    from datetime import date as _date, timedelta as _td

    from app.models.dividend import DividendRecord

    days_ahead = int(rule.params.get("days_ahead", 7))
    today = _date.today()
    cutoff = today + _td(days=days_ahead)
    upcoming = (
        db.query(DividendRecord)
        .filter(
            DividendRecord.stock_code == rule.stock_code,
            DividendRecord.ex_date >= today,
            DividendRecord.ex_date <= cutoff,
        )
        .order_by(DividendRecord.ex_date.asc())
        .first()
    )
    if not upcoming:
        return None
    days_left = (upcoming.ex_date - today).days
    return _emit(
        db,
        rule,
        title=f"{rule.stock_code} 除息日临近（{days_left} 天）",
        detail=f"除息日 {upcoming.ex_date} 每股派 {upcoming.amount_per_share}",
        payload={
            "ex_date": str(upcoming.ex_date),
            "days_left": days_left,
            "amount_per_share": upcoming.amount_per_share,
        },
        severity="info",
    )


def _eval_financial_report_released(db: Session, rule: AlertRule) -> Optional[AlertEvent]:
    if not rule.stock_code:
        return None
    from app.models.financial import FinancialStatement

    q = db.query(FinancialStatement).filter(FinancialStatement.stock_code == rule.stock_code)
    if rule.last_evaluated_at:
        q = q.filter(FinancialStatement.created_at > rule.last_evaluated_at)
    new_row = q.order_by(FinancialStatement.report_date.desc()).first()
    if not new_row:
        return None
    return _emit(
        db,
        rule,
        title=f"{rule.stock_code} 新财报入库",
        detail=f"报告期 {str(new_row.report_date)[:10]} ({new_row.report_type})",
        payload={
            "report_date": str(new_row.report_date)[:10],
            "report_type": new_row.report_type,
        },
        severity="info",
    )


def _eval_stop_profit(
    db: Session, rule: AlertRule, snapshot: Optional[dict]
) -> Optional[AlertEvent]:
    if not snapshot or not rule.stock_code:
        return None
    price = snapshot.get("sp")
    if price is None:
        return None
    holdings = (
        db.query(Holding)
        .filter(Holding.stock_code == rule.stock_code, Holding.sell_date.is_(None))
        .all()
    )
    if not holdings:
        return None
    hits = [h for h in holdings if h.stop_profit_price and float(price) >= h.stop_profit_price]
    if not hits:
        return None
    return _emit(
        db,
        rule,
        title=f"{rule.stock_code} 触发止盈价",
        detail=f"现价 {float(price):.2f} 已达 {len(hits)} 笔持仓止盈位",
        payload={
            "price": float(price),
            "holding_ids": [h.id for h in hits],
            "stop_prices": [h.stop_profit_price for h in hits],
        },
        severity="alert",
    )


def _should_dedupe(db: Session, rule: AlertRule, dedupe_hours: int = 20) -> bool:
    from datetime import timedelta

    cutoff = _utcnow() - timedelta(hours=dedupe_hours)
    recent = (
        db.query(AlertEvent)
        .filter(AlertEvent.rule_id == rule.id, AlertEvent.fired_at >= cutoff)
        .first()
    )
    return recent is not None


AUTO_HOLDING_NOTE_PREFIX = "[auto-holding]"


def sync_stop_profit_rules_from_holdings(db: Session) -> dict:
    holdings = db.query(Holding).filter(Holding.sell_date.is_(None)).all()

    desired: dict[str, float] = {}
    for h in holdings:
        if not h.stop_profit_price or h.stop_profit_price <= 0:
            continue
        prev = desired.get(h.stock_code)
        desired[h.stock_code] = (
            float(h.stop_profit_price) if prev is None else min(prev, float(h.stop_profit_price))
        )

    existing = (
        db.query(AlertRule)
        .filter(
            AlertRule.rule_type == "stop_profit",
            AlertRule.note.isnot(None),
            AlertRule.note.like(f"{AUTO_HOLDING_NOTE_PREFIX}%"),
        )
        .all()
    )

    created = updated = removed = 0
    seen: set[str] = set()
    for rule in existing:
        code = rule.stock_code or ""
        if code not in desired:
            db.delete(rule)
            removed += 1
            continue
        seen.add(code)
        target = desired[code]
        if float(rule.params.get("stop_price", -1)) != target or not rule.enabled:
            rule.params = {"stop_price": target}
            rule.enabled = True
            updated += 1

    for code, target in desired.items():
        if code in seen:
            continue
        db.add(
            AlertRule(
                rule_type="stop_profit",
                stock_code=code,
                params={"stop_price": target},
                enabled=True,
                note=f"{AUTO_HOLDING_NOTE_PREFIX} 来自持仓止盈价",
            )
        )
        created += 1

    db.commit()
    return {"created": created, "updated": updated, "removed": removed}


def evaluate_all_rules(db: Session) -> dict:
    rules = list_rules(db, enabled_only=True)
    if not rules:
        return {"evaluated_rules": 0, "new_events": 0}

    codes_needed = sorted({r.stock_code for r in rules if r.stock_code})
    realtime = _fetch_realtime(codes_needed)

    new_events = 0
    for rule in rules:
        snapshot = realtime.get(rule.stock_code) if rule.stock_code else None
        ev: Optional[AlertEvent] = None
        try:
            if _should_dedupe(db, rule):
                rule.last_evaluated_at = _utcnow()
                continue
            if rule.rule_type == "stop_profit":
                ev = _eval_stop_profit(db, rule, snapshot)
            elif rule.rule_type == "dividend_ex_date_near":
                ev = _eval_dividend_ex_date_near(db, rule)
            elif rule.rule_type == "financial_report_released":
                ev = _eval_financial_report_released(db, rule)
            rule.last_evaluated_at = _utcnow()
            if ev is not None:
                new_events += 1
        except Exception:
            logger.exception("Alert rule %s evaluation failed", rule.id)

    db.commit()
    return {"evaluated_rules": len(rules), "new_events": new_events}
