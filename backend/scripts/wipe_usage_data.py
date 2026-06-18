"""Wipe all user-produced usage data from the local DB.

Usage:
    cd backend
    source .venv/bin/activate
    python scripts/wipe_usage_data.py [--dry-run]

Scope (per 2026-06-18 decision, "pragmatic"):
    CLEAR — user action state + test activity:
        candidates, drafts, holdings, trades, cash_adjustments, cash_balance,
        watchlist_items, watchlist_groups, alert_rules, alert_events,
        system_alerts, notification_channels, audit_logs, backtest_runs,
        research_runs, research_claims, research_claim_variables,
        research_evidence, research_search_results, research_company_ranking,
        research_company_universe, research_themes, job_executions,
        holding_risk_rules, plan_exec_history

    KEEP — Lixinger reference + seed config + process metadata:
        stocks, price_klines, valuations, dividends, financial_statements,
        historical_financials, historical_klines, historical_valuations,
        corp_actions, trading_calendar, data_freshness,
        strategies, plans, plan_templates, themes, business_patterns,
        cashflow_goals, broker_fee_configs,
        pipeline_runs, pipeline_checkpoints, dead_letter_records,
        scheduler_jobs, api_usage_logs,
        scarce_layers, value_chain_layers

Behaviour:
    - Single SQLAlchemy transaction (commit at end; rollback on any error).
    - DELETEs in dependency order (children before parents).
    - Resets sqlite_sequence for cleared tables (next insert id=1).
    - Prints before/after row counts to stdout.

Safety:
    - Caller must stop the backend first (avoids APScheduler races).
    - Caller should snapshot backend/data/gojira.db beforehand.
    - --dry-run prints what would happen without committing.
"""
from __future__ import annotations

import argparse
import sys
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal


# Tables to clear, in dependency-safe order (children first).
CLEAR_TABLES: list[str] = [
    "alert_events",
    "research_claim_variables",
    "research_evidence",
    "research_search_results",
    "research_claims",
    "research_company_ranking",
    "research_company_universe",
    "research_runs",
    "research_themes",
    "job_executions",
    "drafts",
    "candidates",
    "holding_risk_rules",
    "trades",
    "holdings",
    "cash_adjustments",
    "cash_balance",
    "audit_logs",
    "backtest_runs",
    "watchlist_items",
    "watchlist_groups",
    "alert_rules",
    "system_alerts",
    "notification_channels",
    "plan_exec_history",
]


def _count(db: Session, table: str) -> int:
    return db.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions but do not commit.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        print("=" * 60)
        print("Wipe usage data — scope: pragmatic")
        print(f"Mode: {'DRY-RUN' if args.dry_run else 'COMMIT'}")
        print("=" * 60)

        print("\nBefore counts:")
        before = {}
        for t in CLEAR_TABLES:
            try:
                n = _count(db, t)
            except Exception as e:
                print(f"  {t:35s} ERROR: {e}")
                continue
            before[t] = n
            print(f"  {t:35s} {n:>8}")

        if args.dry_run:
            print("\n[DRY-RUN] No changes made.")
            return 0

        print("\nDeleting (children → parents)...")
        for t in CLEAR_TABLES:
            result = db.execute(text(f'DELETE FROM "{t}"'))
            print(f"  {t:35s} deleted {result.rowcount:>8}")

        print("\nResetting sqlite_sequence...")
        has_seq = db.execute(
            text(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
            )
        ).first()
        if not has_seq:
            print("  (sqlite_sequence table does not exist — using INTEGER PRIMARY KEY, no reset needed)")
        else:
            names_sql = ", ".join(f"'{t}'" for t in CLEAR_TABLES)
            existing = db.execute(
                text(f"SELECT name FROM sqlite_sequence WHERE name IN ({names_sql})")
            ).fetchall()
            if not existing:
                print("  (no matching sequences to reset)")
            for (name,) in existing:
                db.execute(text("DELETE FROM sqlite_sequence WHERE name = :n"), {"n": name})
                print(f"  reset sequence: {name}")

        db.commit()
        print("\nCommit OK.")

        print("\nAfter counts:")
        for t in CLEAR_TABLES:
            try:
                n = _count(db, t)
            except Exception:
                continue
            print(f"  {t:35s} {n:>8}")

        print("\nDone.")
        return 0
    except Exception as e:
        db.rollback()
        print(f"\nERROR: {e}", file=sys.stderr)
        print("Transaction rolled back. No changes made.", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
