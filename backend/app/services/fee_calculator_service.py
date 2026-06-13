"""Fee calculator — commission / stamp duty / transfer fee.

A-share fee structure (current as of 2023-10-23):
- Commission: max(notional × rate, min) — both BUY and SELL
- Stamp duty: notional × rate — SELL ONLY (0.05% currently)
- Transfer fee: notional × rate — both BUY and SELL (0.001%)

`notional = price × quantity`.

Historical rates are stored in broker_fee_configs with effective_from.
Caller selects the right config based on trade.filled_at.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.models.broker_fee_config import BrokerFeeConfig


@dataclass(frozen=True)
class FeeBreakdown:
    commission: float
    stamp_duty: float
    transfer_fee: float
    notional: float
    side: str

    def total_value(self, side: str | None = None) -> float:
        """Net cash impact.

        BUY: cash outflow = notional + all fees
        SELL: cash inflow = notional - all fees
        DIVIDEND: cash inflow = -notional (negative indicates inflow)
        CORP_ACTION: no cash impact (price=0, no fees)
        """
        side = side or self.side
        fees = self.commission + self.stamp_duty + self.transfer_fee
        if side == "BUY":
            return self.notional + fees
        elif side == "SELL":
            return self.notional - fees
        elif side == "DIVIDEND":
            return -self.notional
        elif side == "CORP_ACTION":
            return 0.0
        raise ValueError(f"Unknown side: {side}")


def compute_fees(
    side: str,
    price: float,
    quantity: int,
    broker_config: BrokerFeeConfig,
) -> FeeBreakdown:
    """Compute fee breakdown for a single trade.

    Args:
        side: "BUY" | "SELL" | "DIVIDEND" | "CORP_ACTION"
        price: Per-share price.
        quantity: Number of shares (positive integer).
        broker_config: Fee rates from broker_fee_configs table.

    Returns:
        FeeBreakdown with commission, stamp_duty, transfer_fee, notional, side.
    """
    notional = price * quantity

    commission = max(
        notional * broker_config.commission_rate,
        broker_config.commission_min,
    )

    # 印花税:仅卖出收(严格 side == SELL)
    stamp_duty = (
        notional * broker_config.stamp_duty_rate
        if side == "SELL"
        else 0.0
    )

    # 过户费:买卖双向
    transfer_fee = notional * broker_config.transfer_fee_rate

    # DIVIDEND / CORP_ACTION: 没有交易费用(notional 保留用于 cash impact)
    if side in ("DIVIDEND", "CORP_ACTION"):
        commission = 0.0
        transfer_fee = 0.0
        # DIVIDEND/CORP_ACTION 的 stamp_duty 已经是 0(side != SELL)

    return FeeBreakdown(
        commission=commission,
        stamp_duty=stamp_duty,
        transfer_fee=transfer_fee,
        notional=notional,
        side=side,
    )
