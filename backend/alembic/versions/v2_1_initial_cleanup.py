"""v2 (2026-06-24): drop v1 tables + create v2 LLM Pipeline tables

Revision ID: v2_1_initial_cleanup
Revises: s11_1_bj_timezone_migration
Create Date: 2026-06-24

Background (2026-06-24 grill-me v2 rewrite):
  Big rewrite per docs/active/redesign-decisions-v2.md. Drop all v1 concept
  tables (strategies / plans / themes / business_patterns / candidates / research_*
  / backtest_* / watchlist_* / thesis_*). Keep Lixinger data tables (stocks /
  financial_statements / price_klines / dividend_records / valuation_snapshots /
  audit_logs / corp_actions / historical_*) and infrastructure tables.

  Create v2 LLM Pipeline tables: stock_lifecycle / research_report /
  decision_audit / llm_call_log / red_line_event.

  See: docs/active/redesign-decisions-v2.md (decisions 17, 21, 22, 25)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "v2_1_initial_cleanup"
down_revision = "s11_1_bj_timezone_migration"
branch_labels = None
depends_on = None


# v1 tables to drop (cascade handles FK constraints)
V1_TABLES_TO_DROP = [
    "research_claim_variables",
    "research_claims",
    "research_company_rankings",
    "research_company_universe",
    "research_evidence",
    "research_search_results",
    "research_runs",
    "research_themes",
    "scarce_layers",
    "value_chain_layers",
    "backtest_runs",
    "business_patterns",
    "holding_risk_rules",
    "notification_channels",
    "cashflow_goals",
    "watchlist_items",
    "watchlist_groups",
    "thesis_variables",
    "candidates",
    "themes",
    "plans",
    "strategies",
]


def upgrade():
    # SQLite has limited DROP CONSTRAINT support; for drafts.plan_id FK we
    # rely on SQLite's loose FK enforcement (PRAGMA foreign_keys=OFF by default
    # in async engine). The column stays as plain Integer in v2 Draft model.

    # 1. Drop v1 tables (ignore-if-not-exists for idempotency)
    conn = op.get_bind()
    existing = {
        row[0] for row in conn.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table'"))
    }
    for table in V1_TABLES_TO_DROP:
        if table in existing:
            op.drop_table(table)

    # 2. Create v2 tables

    # stock_lifecycle — state machine per stock
    op.create_table(
        "stock_lifecycle",
        sa.Column("stock_code", sa.String, primary_key=True, nullable=False),
        sa.Column("current_state", sa.String, nullable=False),
        # universe | watchlist | researched | candidate | signaled | holding | exited
        sa.Column("entered_state_at", sa.DateTime, nullable=True),
        sa.Column("last_research_at", sa.DateTime, nullable=True),
        sa.Column("rejected_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("history_json", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("(datetime('now', 'localtime'))")),
        sa.Column("updated_at", sa.DateTime, server_default=sa.text("(datetime('now', 'localtime'))")),
    )
    op.create_index("ix_stock_lifecycle_state", "stock_lifecycle", ["current_state"])
    op.create_index("ix_stock_lifecycle_last_research", "stock_lifecycle", ["last_research_at"])

    # research_report — LLM outputs (JSON + markdown)
    op.create_table(
        "research_reports",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("stock_code", sa.String, nullable=False),
        sa.Column("pipeline_type", sa.String, nullable=False),
        # deep_research | thesis_tracker | news_pulse | earnings_review | quality_screen
        sa.Column("run_id", sa.Integer, nullable=True),
        sa.Column("json_output", sa.JSON, nullable=True),
        sa.Column("markdown_output", sa.Text, nullable=True),
        sa.Column("evidence_grade", sa.String(1), nullable=True),  # A | B | C
        sa.Column("data_conflict_json", sa.JSON, nullable=True),
        sa.Column("red_line_hit_json", sa.JSON, nullable=True),
        sa.Column("prompt_version", sa.String, nullable=True),
        sa.Column("overall_score", sa.Float, nullable=True),
        sa.Column("recommendation", sa.String, nullable=True),  # BUY | HOLD | PASS | SELL | TRIM
        sa.Column("status", sa.String, nullable=False, server_default="completed"),
        # completed | rejected | conflict | stale
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("(datetime('now', 'localtime'))")),
        sa.ForeignKeyConstraint(["stock_code"], ["stocks.code"]),
    )
    op.create_index("ix_research_reports_stock_code", "research_reports", ["stock_code"])
    op.create_index("ix_research_reports_pipeline_type", "research_reports", ["pipeline_type"])
    op.create_index(
        "ix_research_reports_stock_pipeline",
        "research_reports",
        ["stock_code", "pipeline_type"],
    )
    op.create_index("ix_research_reports_created_at", "research_reports", ["created_at"])
    op.create_index("ix_research_reports_overall_score", "research_reports", ["overall_score"])
    op.create_index("ix_research_reports_expires_at", "research_reports", ["expires_at"])

    # decision_audit — Tier 2 metrics (P&L tracking for approved drafts)
    op.create_table(
        "decision_audits",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("draft_id", sa.Integer, nullable=True),
        sa.Column("approved_at", sa.DateTime, nullable=True),
        sa.Column("approved_by", sa.String, nullable=True),
        sa.Column("stock_code", sa.String, nullable=False),
        sa.Column("action", sa.String, nullable=False),  # BUY | SELL | TRIM
        sa.Column("target_price", sa.Float, nullable=True),
        sa.Column("executed_price", sa.Float, nullable=True),
        sa.Column("quantity", sa.Integer, nullable=True),
        sa.Column("status_30d", sa.String, nullable=True),  # gain | loss | flat
        sa.Column("status_90d", sa.String, nullable=True),
        sa.Column("status_365d", sa.String, nullable=True),
        sa.Column("benchmark_diff_pct", sa.Float, nullable=True),
        sa.Column("thesis_status_now", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("(datetime('now', 'localtime'))")),
        sa.Column("updated_at", sa.DateTime, server_default=sa.text("(datetime('now', 'localtime'))")),
    )
    op.create_index("ix_decision_audits_draft_id", "decision_audits", ["draft_id"])
    op.create_index("ix_decision_audits_stock_code", "decision_audits", ["stock_code"])
    op.create_index("ix_decision_audits_created_at", "decision_audits", ["created_at"])

    # llm_call_log — LLM observability (per-call cost/tokens/latency)
    op.create_table(
        "llm_call_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("trace_id", sa.String, nullable=True),
        sa.Column("span_id", sa.String, nullable=True),
        sa.Column("model", sa.String, nullable=False),
        sa.Column("pipeline_type", sa.String, nullable=True),
        sa.Column("stock_code", sa.String, nullable=True),
        sa.Column("prompt_hash", sa.String, nullable=True),
        sa.Column("tokens_in", sa.Integer, nullable=True),
        sa.Column("tokens_out", sa.Integer, nullable=True),
        sa.Column("cost_usd", sa.Float, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("tool_calls_json", sa.JSON, nullable=True),
        sa.Column("conflict_flags_json", sa.JSON, nullable=True),
        sa.Column("success", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("(datetime('now', 'localtime'))")),
    )
    op.create_index("ix_llm_call_logs_trace_id", "llm_call_logs", ["trace_id"])
    op.create_index("ix_llm_call_logs_model", "llm_call_logs", ["model"])
    op.create_index("ix_llm_call_logs_stock_code", "llm_call_logs", ["stock_code"])
    op.create_index("ix_llm_call_logs_prompt_hash", "llm_call_logs", ["prompt_hash"])
    op.create_index("ix_llm_call_logs_created_at", "llm_call_logs", ["created_at"])
    op.create_index("ix_llm_call_logs_model_created", "llm_call_logs", ["model", "created_at"])

    # red_line_event — 8 red line triggers
    op.create_table(
        "red_line_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("stock_code", sa.String, nullable=False),
        sa.Column("red_line_type", sa.String, nullable=False),
        # management_integrity | financial_fraud | major_violation | consecutive_losses
        # | high_pledge | frequent_reduction | complex_related_transactions | benford_anomaly
        sa.Column("report_id", sa.Integer, nullable=True),
        sa.Column("severity", sa.String, nullable=False, server_default="hard_reject"),
        sa.Column("evidence_json", sa.JSON, nullable=True),
        sa.Column("action_taken", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("(datetime('now', 'localtime'))")),
        sa.ForeignKeyConstraint(["stock_code"], ["stocks.code"]),
    )
    op.create_index("ix_red_line_events_stock_code", "red_line_events", ["stock_code"])
    op.create_index("ix_red_line_events_red_line_type", "red_line_events", ["red_line_type"])
    op.create_index("ix_red_line_events_created_at", "red_line_events", ["created_at"])


def downgrade():
    # Drop v2 tables
    for table in ["red_line_events", "llm_call_logs", "decision_audits", "research_reports", "stock_lifecycle"]:
        op.drop_table(table)
    # Note: v1 tables are NOT recreated on downgrade (data would be lost anyway)
