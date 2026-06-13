"""add historical_* tables for backtest time-series data

Revision ID: s4b_1_historical
Revises: s4a_1_corp_actions
Create Date: 2026-06-13 01:25:00

S4B.1: Three tables for backtest engine (S4C) to read from:

- historical_valuations: daily PE/PB/PS/DYR/MC time-series per stock
- historical_klines: daily OHLCV + amount + turnover_rate
- historical_financials: quarterly/annual financials with report_date
  for point-in-time correctness (only financials with report_date <= D
  are "known" on day D).

S0.3 spike validated:
- Lixinger returns 10y daily data for all 3 endpoints (2431 records
  for 600519 over 2015-2024).
- K-line and valuation 1:1 aligned (same dates).
- reportDate field present on financials (S0.2).

S4B.2 pipeline will populate these tables (incremental + checkpoint).
For storage: ~12M rows for full market x 10y daily; SQLite WAL handles
this fine per S0.5 spike (1 writer + 5 readers, 0 lock contention).

Unique constraints prevent duplicate sync. Composite indexes on
(stock_code, date|period) for efficient range scans during backtest replay.
report_date single-column index for point-in-time financial queries.
"""
revision = "s4b_1_historical"
down_revision = "s4a_1_corp_actions"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade():
    # --- historical_valuations ---
    op.create_table(
        "historical_valuations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "stock_code",
            sa.String,
            sa.ForeignKey("stocks.code"),
            nullable=False,
        ),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("pe_ttm", sa.Float, nullable=True),
        sa.Column("pb", sa.Float, nullable=True),
        sa.Column("pb_wo_gw", sa.Float, nullable=True),
        sa.Column("ps_ttm", sa.Float, nullable=True),
        sa.Column("pcf_ttm", sa.Float, nullable=True),
        sa.Column("dyr", sa.Float, nullable=True),
        sa.Column("sp", sa.Float, nullable=True),
        sa.Column("mc", sa.Float, nullable=True),
        sa.Column("mc_om", sa.Float, nullable=True),
        sa.Column("cmc", sa.Float, nullable=True),
        sa.UniqueConstraint(
            "stock_code", "date", name="uq_hist_val_code_date"
        ),
    )
    op.create_index(
        "ix_historical_valuations_code_date",
        "historical_valuations",
        ["stock_code", "date"],
    )

    # --- historical_klines ---
    op.create_table(
        "historical_klines",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "stock_code",
            sa.String,
            sa.ForeignKey("stocks.code"),
            nullable=False,
        ),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("open", sa.Float, nullable=False),
        sa.Column("high", sa.Float, nullable=False),
        sa.Column("low", sa.Float, nullable=False),
        sa.Column("close", sa.Float, nullable=False),
        sa.Column("volume", sa.Float, nullable=True),
        sa.Column("amount", sa.Float, nullable=True),
        sa.Column("turnover_rate", sa.Float, nullable=True),
        sa.UniqueConstraint(
            "stock_code", "date", name="uq_hist_kline_code_date"
        ),
    )
    op.create_index(
        "ix_historical_klines_code_date",
        "historical_klines",
        ["stock_code", "date"],
    )

    # --- historical_financials ---
    op.create_table(
        "historical_financials",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "stock_code",
            sa.String,
            sa.ForeignKey("stocks.code"),
            nullable=False,
        ),
        sa.Column("period", sa.Date, nullable=False),
        sa.Column("report_date", sa.Date, nullable=False),
        sa.Column("report_type", sa.String, nullable=True),
        # Income statement
        sa.Column("revenue", sa.Float, nullable=True),
        sa.Column("net_profit", sa.Float, nullable=True),
        sa.Column("operating_profit", sa.Float, nullable=True),
        # Balance sheet
        sa.Column("total_assets", sa.Float, nullable=True),
        sa.Column("total_liabilities", sa.Float, nullable=True),
        sa.Column("total_equity", sa.Float, nullable=True),
        # Cash flow
        sa.Column("operating_cash_flow", sa.Float, nullable=True),
        sa.Column("investing_cash_flow", sa.Float, nullable=True),
        sa.Column("financing_cash_flow", sa.Float, nullable=True),
        # Ratios
        sa.Column("roe", sa.Float, nullable=True),
        sa.Column("roa", sa.Float, nullable=True),
        sa.Column("debt_ratio", sa.Float, nullable=True),
        sa.Column("ocf_to_np_ratio", sa.Float, nullable=True),
        sa.Column("gross_margin", sa.Float, nullable=True),
        sa.UniqueConstraint(
            "stock_code", "period", name="uq_hist_fin_code_period"
        ),
    )
    op.create_index(
        "ix_historical_financials_period",
        "historical_financials",
        ["period"],
    )
    op.create_index(
        "ix_historical_financials_report_date",
        "historical_financials",
        ["report_date"],
    )
    op.create_index(
        "ix_historical_financials_code_period",
        "historical_financials",
        ["stock_code", "period"],
    )


def downgrade():
    op.drop_index(
        "ix_historical_financials_code_period",
        table_name="historical_financials",
    )
    op.drop_index(
        "ix_historical_financials_report_date",
        table_name="historical_financials",
    )
    op.drop_index(
        "ix_historical_financials_period", table_name="historical_financials"
    )
    op.drop_table("historical_financials")

    op.drop_index(
        "ix_historical_klines_code_date", table_name="historical_klines"
    )
    op.drop_table("historical_klines")

    op.drop_index(
        "ix_historical_valuations_code_date",
        table_name="historical_valuations",
    )
    op.drop_table("historical_valuations")
