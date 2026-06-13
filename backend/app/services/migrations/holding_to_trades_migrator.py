"""One-shot migrator: legacy Holding rows -> opening Trade events.

Run via Alembic data migration (see alembic/versions/s1_8_migrate_holdings_data.py)
or manually: ``python -m app.services.migrations.holding_to_trades_migrator``.

Strategy:
- Open holdings (sell_date IS NULL) become BUY trades with source='migration'
- Closed holdings (sell_date set) are skipped (already realized P&L)
- Idempotent: checks source_ref existence before insert
- Updates cash_balance.balance -= sum(total_value) of migrated trades
  (assumes initial cash was sufficient; user should adjust via UI deposit
  entry if real broker balance differs)

After migration, holding_view_service returns positions identical to the
legacy holdings table. position_advisor switches to reading from
holding_view in S1.11.
"""
from datetime import UTC, datetime
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cash_balance import CashBalance
from app.models.holding import Holding
from app.models.trade import Trade

logger = logging.getLogger(__name__)

MIGRATION_BATCH_ID = "migration_2026_06_12"


def migrate_holdings_to_trades(db: Session, batch_id: str = MIGRATION_BATCH_ID) -> int:
    """Convert each open Holding into a Trade(source='migration').

    Args:
        db: SQLAlchemy session.
        batch_id: Unique batch identifier for idempotency.

    Returns:
        Number of trades inserted (0 if already migrated).
    """
    open_holdings = db.execute(
        select(Holding).where(Holding.sell_date.is_(None))
    ).scalars().all()

    cb = db.query(CashBalance).first()
    if not cb:
        cb = CashBalance(id=1, balance=0.0)
        db.add(cb)
        db.flush()

    inserted = 0
    cash_delta = 0.0
    last_trade_id = None

    for h in open_holdings:
        source_ref = f"{batch_id}:{h.id}"
        existing = db.execute(
            select(Trade).where(
                Trade.source == "migration",
                Trade.source_ref == source_ref,
            )
        ).scalar_one_or_none()
        if existing:
            continue

        total_value = h.buy_price * h.quantity
        trade = Trade(
            stock_code=h.stock_code,
            side="BUY",
            price=h.buy_price,
            quantity=h.quantity,
            filled_at=datetime.combine(h.buy_date, datetime.min.time()),
            commission=0.0,
            stamp_duty=0.0,
            transfer_fee=0.0,
            total_value=total_value,
            source="migration",
            source_ref=source_ref,
            fee_source="auto",
            note=f"Migrated from Holding#{h.id}",
        )
        db.add(trade)
        db.flush()
        inserted += 1
        cash_delta += total_value
        last_trade_id = trade.id

    if inserted > 0:
        cb.balance -= cash_delta
        cb.last_trade_id = last_trade_id
        cb.as_of_at = datetime.now(UTC)
        db.flush()
        logger.info(
            "Migrated %d open holdings to trades, cash_delta=-¥%.2f",
            inserted, cash_delta,
        )

    return inserted


if __name__ == "__main__":
    """Manual run (outside Alembic) — use only for one-off ops on dev DB."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        count = migrate_holdings_to_trades(db)
        db.commit()
        print(f"Migrated {count} open holdings to trades")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
