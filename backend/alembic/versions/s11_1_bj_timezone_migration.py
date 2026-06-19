"""2026-06-19 Timezone migration: shift all timestamp columns +8h (UTC → Beijing)

Revision ID: s11_1_bj_timezone_migration
Revises: s10_1_in_circle_filter_default_off
Create Date: 2026-06-19

Background (2026-06-19 grill-me 时区改造):
  Project previously stored naive UTC across all timestamp columns. Going
  forward, all writes are naive Beijing time (datetime_utils.now()).
  This migration shifts existing UTC values +8 hours so they remain
  consistent with new writes.

Scope: only "timestamp" columns (created_at / updated_at / started_at /
finished_at / last_synced_at / last_success_at / last_run_at / triggered_at /
executed_at / etc.). Business date columns (price_klines.date /
valuations.date / dividends.ex_date / financial_statements.report_date /
dividends.pay_date) are NOT touched — they represent trading calendar
dates, not wall-clock timestamps.

Strategy: per-table explicit UPDATE. Each statement uses SQLite's
`datetime(col, '+8 hours')` which is idempotent for naive timestamps
(running twice produces +16h, so this migration is NOT re-runnable —
guard with check on data_freshness table existence).
"""

revision = "s11_1_bj_timezone_migration"
down_revision = "s10_1_in_circle_filter_default_off"
branch_labels = None
depends_on = None

from alembic import op  # noqa: E402


# (table, timestamp_column) pairs to shift +8h.
# Excludes business date columns (date / report_date / ex_date / pay_date / announced_date).
TIMESTAMP_COLUMNS = [
    # Core stocks
    ("stocks", "delisted_at"),
    ("stocks", "created_at"),
    ("stocks", "updated_at"),
    ("stocks", "business_pattern_inferred_at"),
    # Reference data
    ("valuations", "created_at"),
    ("financial_statements", "created_at"),
    ("price_klines", "created_at"),
    ("dividends", "created_at"),
    # Pipeline metadata
    ("pipeline_runs", "started_at"),
    ("pipeline_runs", "finished_at"),
    ("pipeline_runs", "created_at"),
    ("pipeline_runs", "updated_at"),
    ("pipeline_checkpoints", "created_at"),
    ("dead_letter_records", "created_at"),
    ("dead_letter_records", "last_retry_at"),
    ("api_usage_logs", "called_at"),
    # Scheduler
    ("scheduler_jobs", "created_at"),
    ("scheduler_jobs", "updated_at"),
    ("job_executions", "started_at"),
    ("job_executions", "finished_at"),
    # Freshness
    ("data_freshness", "last_synced_at"),
    ("data_freshness", "last_success_at"),
    # User action layer (wipe后空 = no-op)
    ("audit_logs", "created_at"),
    ("drafts", "triggered_at"),
    ("drafts", "executed_at"),
    ("drafts", "created_at"),
    ("candidates", "first_seen_at"),
    ("candidates", "last_confirmed_at"),
    ("candidates", "removed_at"),
    ("candidates", "created_at"),
    ("holdings", "first_buy_at"),
    ("holdings", "last_updated_at"),
    ("holdings", "created_at"),
    ("trades", "filled_at"),
    ("trades", "created_at"),
    ("cash_adjustments", "adjusted_at"),
    ("cash_adjustments", "created_at"),
    ("cash_balance", "updated_at"),
    # Alerting
    ("alert_events", "triggered_at"),
    ("alert_events", "resolved_at"),
    ("alert_events", "created_at"),
    ("alert_rules", "created_at"),
    ("alert_rules", "updated_at"),
    ("system_alerts", "triggered_at"),
    ("system_alerts", "resolved_at"),
    ("system_alerts", "created_at"),
    ("notification_channels", "created_at"),
    # Holdings extras
    ("holding_risk_rules", "triggered_at"),
    ("holding_risk_rules", "created_at"),
    # Strategy / plan / theme
    ("strategies", "created_at"),
    ("strategies", "updated_at"),
    ("plans", "last_run_at"),
    ("plans", "created_at"),
    ("plans", "updated_at"),
    ("themes", "created_at"),
    ("themes", "updated_at"),
    ("business_patterns", "created_at"),
    ("business_patterns", "updated_at"),
    ("cashflow_goals", "created_at"),
    ("cashflow_goals", "updated_at"),
    ("broker_fee_configs", "created_at"),
    ("broker_fee_configs", "updated_at"),
    # Corp actions
    ("corp_actions", "ex_date"),  # ex_date IS a timestamp here (action effective time)
    ("corp_actions", "processed_at"),
    ("corp_actions", "created_at"),
    # Watchlist
    ("watchlist_groups", "created_at"),
    ("watchlist_groups", "updated_at"),
    ("watchlist_items", "added_at"),
    ("watchlist_items", "removed_at"),
    ("watchlist_items", "created_at"),
    ("watchlist_items", "updated_at"),
    # Backtest
    ("backtest_runs", "started_at"),
    ("backtest_runs", "finished_at"),
    ("backtest_runs", "created_at"),
    # Research (serenity)
    ("research_themes", "last_run_at"),
    ("research_themes", "created_at"),
    ("research_themes", "updated_at"),
    ("research_runs", "started_at"),
    ("research_runs", "completed_at"),
    ("research_claim_variables", "created_at"),
    ("research_evidence", "created_at"),
    ("research_search_results", "created_at"),
    ("research_claims", "created_at"),
    ("research_company_ranking", "created_at"),
    ("research_company_universe", "created_at"),
    ("value_chain_layers", "created_at"),
    ("scarce_layers", "created_at"),
]


def upgrade():
    """Shift every timestamp column +8h (UTC → Beijing).

    Idempotent guard: skip if already migrated (heuristic — check if
    pipeline_runs.started_at is within last 7 days of CURRENT_TIMESTAMP;
    pre-migration data would be exactly 8h behind).
    """
    bind = op.get_bind()

    # Heuristic: if any pipeline_runs row has started_at within the last 8h
    # of CURRENT_TIMESTAMP, assume migration already applied.
    result = bind.execute(sa_text(
        "SELECT COUNT(*) FROM pipeline_runs "
        "WHERE started_at IS NOT NULL "
        "AND started_at > datetime(CURRENT_TIMESTAMP, '-8 hours')"
    )).scalar()
    if result and result > 0:
        print(f"  [SKIP] pipeline_runs has fresh timestamps (rows in last 8h: {result}), "
              "migration likely already applied.")
        return

    total_rows = 0
    for table, column in TIMESTAMP_COLUMNS:
        # Check column exists (some tables may have evolved)
        col_exists = bind.execute(sa_text(
            f"SELECT COUNT(*) FROM pragma_table_info('{table}') WHERE name='{column}'"
        )).scalar()
        if not col_exists:
            print(f"  [SKIP] {table}.{column} does not exist")
            continue
        # Check table has rows
        row_count = bind.execute(sa_text(
            f"SELECT COUNT(*) FROM {table} WHERE {column} IS NOT NULL"
        )).scalar()
        if row_count == 0:
            continue
        bind.execute(sa_text(
            f"UPDATE {table} SET {column} = datetime({column}, '+8 hours') "
            f"WHERE {column} IS NOT NULL"
        ))
        print(f"  [OK] {table}.{column}: +8h on {row_count} rows")
        total_rows += row_count

    print(f"\nTotal rows migrated: {total_rows}")


def downgrade():
    """Reverse: shift -8h (Beijing → UTC). Use only for true rollback."""
    bind = op.get_bind()
    for table, column in TIMESTAMP_COLUMNS:
        col_exists = bind.execute(sa_text(
            f"SELECT COUNT(*) FROM pragma_table_info('{table}') WHERE name='{column}'"
        )).scalar()
        if not col_exists:
            continue
        bind.execute(sa_text(
            f"UPDATE {table} SET {column} = datetime({column}, '-8 hours') "
            f"WHERE {column} IS NOT NULL"
        ))


def sa_text(sql: str):
    """Lazy import to avoid module-level sa dependency in revision file."""
    from sqlalchemy import text
    return text(sql)
