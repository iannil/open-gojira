"""data migration: legacy holdings -> trades

Revision ID: s1_8_migrate_data
Revises: s1_4_fee_configs
Create Date: 2026-06-12 22:00:00

S1.8: One-shot conversion of legacy Holding rows into Trade events with
source='migration'. Strategy:
- Open holdings (sell_date IS NULL) -> 1 BUY trade each
- Closed holdings (sell_date set) -> skipped (already realized)
- Idempotent: source_ref = "{batch_id}:{holding_id}" for dedup
- Updates cash_balance: balance -= sum(total_value) of migrated trades
  (assumes starting cash was sufficient; user reconciles via UI deposit
  entry against real broker balance)

After migration, holding_view_service returns positions identical to
legacy holdings table. position_advisor will switch to reading from
holding_view in S1.11.
"""
revision = "s1_8_migrate_data"
down_revision = "s1_4_fee_configs"
branch_labels = None
depends_on = None


def upgrade():
    """Run holding -> trades migration."""
    from app.db.session import SessionLocal
    from app.services.migrations.holding_to_trades_migrator import (
        migrate_holdings_to_trades,
    )

    db = SessionLocal()
    try:
        count = migrate_holdings_to_trades(db)
        print(f"Migrated {count} open holdings to trades")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def downgrade():
    """Reverse migration: remove all trades with source='migration'.

    Note: cash_balance is NOT restored on downgrade (we don't know the
    pre-migration balance). User should manually reconcile cash after
    downgrade if needed.
    """
    from sqlalchemy import delete

    from app.db.session import SessionLocal
    from app.models.trade import Trade

    db = SessionLocal()
    try:
        result = db.execute(delete(Trade).where(Trade.source == "migration"))
        db.commit()
        print(f"Removed {result.rowcount} migration-source trades")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
