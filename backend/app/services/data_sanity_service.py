"""Data sanity service — validate Lixinger records before persisting.

Catches obvious data quality issues (NaN, zero, negative where positive
expected, unreasonably large values) before they pollute strategy_engine
and generate phantom drafts.

Used by:
- Pipeline transform stage: validate each record before upsert
- Manual data sync endpoints: validate before commit
- Backtest engine: validate historical records

Records that fail are routed to dead_letter pipeline for review.
"""
import math
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.services.system_alert_service import create_alert


# Field → predicate(value) → True if valid, False if violation.
# None values are skipped (not all records have all fields).
SANITY_RULES: dict[str, Callable[[Any], bool]] = {
    # Valuation
    "pe_ttm": lambda v: isinstance(v, (int, float)) and not math.isnan(v) and 0 < v < 1000,
    "pb": lambda v: isinstance(v, (int, float)) and not math.isnan(v) and 0 < v < 100,
    "pb_wo_gw": lambda v: isinstance(v, (int, float)) and not math.isnan(v) and 0 < v < 100,
    "ps_ttm": lambda v: isinstance(v, (int, float)) and not math.isnan(v) and 0 < v < 500,
    "pcf_ttm": lambda v: isinstance(v, (int, float)) and not math.isnan(v) and -1000 < v < 1000,

    # Dividend yield (0 is fine — non-dividend payers)
    "dyr": lambda v: isinstance(v, (int, float)) and not math.isnan(v) and 0 <= v < 0.30,

    # Market cap & price
    "mc": lambda v: isinstance(v, (int, float)) and not math.isnan(v) and v > 0,
    "mc_om": lambda v: isinstance(v, (int, float)) and not math.isnan(v) and v > 0,
    "cmc": lambda v: isinstance(v, (int, float)) and not math.isnan(v) and v > 0,
    "sp": lambda v: isinstance(v, (int, float)) and not math.isnan(v) and v > 0,

    # Financial statement sanity
    "bs.ta.t": lambda v: isinstance(v, (int, float)) and not math.isnan(v) and v > 0,
    "ps.toi.t": lambda v: isinstance(v, (int, float)) and not math.isnan(v) and v >= 0,
    "ps.np.t": lambda v: isinstance(v, (int, float)) and not math.isnan(v),
}


def validate_record(record: dict) -> list[str]:
    """Return list of violation messages for fields failing sanity.

    Empty list means record is valid (or has no fields covered by rules).
    Fields absent from record or with None value are skipped.
    """
    violations = []
    for field, rule in SANITY_RULES.items():
        if field not in record:
            continue
        value = record[field]
        if value is None:
            continue
        try:
            ok = rule(value)
        except (TypeError, ValueError):
            ok = False
        if not ok:
            violations.append(f"{field}={value!r} violates sanity rule")
    return violations


def is_valid_record(record: dict) -> bool:
    """Boolean shortcut for validate_record."""
    return not validate_record(record)


def validate_batch(
    records: list[dict],
    id_field: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """Split records into (valid, invalid) lists.

    Args:
        records: List of dicts to validate.
        id_field: If given, invalid entries include the record's ID for
                  dead_letter tracing.

    Returns:
        (valid_records, invalid_entries)
        invalid_entries is list of {"record": dict, "violations": [...]}.
    """
    valid, invalid = [], []
    for rec in records:
        violations = validate_record(rec)
        if violations:
            entry = {"record": rec, "violations": violations}
            if id_field and id_field in rec:
                entry["id"] = rec[id_field]
            invalid.append(entry)
        else:
            valid.append(rec)
    return valid, invalid


def get_violations_summary(invalid_entries: list[dict]) -> dict:
    """Aggregate stats for logging / alerting.

    Returns: {"total_records": N, "total_violations": M, "by_field": {...}}
    """
    by_field: dict[str, int] = {}
    total_violations = 0
    for entry in invalid_entries:
        for v in entry["violations"]:
            field = v.split("=")[0]
            by_field[field] = by_field.get(field, 0) + 1
            total_violations += 1
    return {
        "total_records": len(invalid_entries),
        "total_violations": total_violations,
        "by_field": by_field,
    }


def alert_on_high_violation_rate(
    db: Session,
    invalid_entries: list[dict],
    total_attempted: int,
    threshold_pct: float = 0.05,
) -> None:
    """Emit warning system_alert if violation rate exceeds threshold.

    E.g. if >5% of records fail sanity, something is systematically wrong.
    """
    if total_attempted == 0:
        return
    rate = len(invalid_entries) / total_attempted
    if rate > threshold_pct:
        summary = get_violations_summary(invalid_entries)
        create_alert(
            db,
            severity="warning",
            category="data",
            message=(
                f"High data sanity violation rate: {rate:.1%} "
                f"({len(invalid_entries)}/{total_attempted} records)"
            ),
            detail=summary,
        )
