"""Position sizing service — convert target_pct to actual share quantity.

A-share lot size = 100 shares (主板/创业板/科创板/北交所统一).
Formula:
1. raw_cash = capital_base × target_pct
2. raw_qty = int(raw_cash // current_price)
3. rounded_qty = (raw_qty // lot_size) × lot_size
4. While rounded_qty > 0 and (rounded_qty × price + commission) > available_cash:
       rounded_qty -= lot_size
5. Return quantity, estimated_cost, actual_pct_of_nav

Used by plan_runner (S2.5) when generating BUY drafts to populate
suggested_quantity field.
"""
from dataclasses import dataclass

from app.models.broker_fee_config import BrokerFeeConfig
from app.services.fee_calculator_service import compute_fees


@dataclass(frozen=True)
class BuyQuantityResult:
    quantity: int
    """Suggested buy quantity (multiple of lot_size, may be 0)."""
    estimated_cost: float
    """Total cash needed = price × qty + commission + transfer_fee."""
    estimated_commission: float
    """Commission amount (auto-computed, not override)."""
    actual_pct_of_nav: float
    """Fraction of capital_base actually used (≤ target_pct after rounding)."""


def compute_buy_quantity(
    *,
    capital_base: float,
    target_pct: float,
    current_price: float,
    available_cash: float,
    broker_config: BrokerFeeConfig,
    lot_size: int = 100,
) -> BuyQuantityResult:
    """Compute suggested buy quantity given capital constraints.

    Args:
        capital_base: Total NAV (cash + holdings market value).
        target_pct: Target fraction for this position (e.g. 0.10 = 10%).
        current_price: Latest price of the stock.
        available_cash: Current cash_balance.balance.
        broker_config: Fee rates for commission/transfer_fee calc.
        lot_size: Minimum lot size (default 100 for A-share).

    Returns:
        BuyQuantityResult with quantity, estimated_cost, etc.
    """
    if target_pct <= 0 or current_price <= 0 or capital_base <= 0:
        return BuyQuantityResult(
            quantity=0, estimated_cost=0.0,
            estimated_commission=0.0, actual_pct_of_nav=0.0,
        )

    raw_cash_needed = capital_base * target_pct
    raw_qty = int(raw_cash_needed // current_price)
    rounded_qty = (raw_qty // lot_size) * lot_size

    # Step down lots if cash insufficient (incl. fees)
    while rounded_qty > 0:
        fees = compute_fees(
            side="BUY", price=current_price,
            quantity=rounded_qty, broker_config=broker_config,
        )
        total_cost = fees.total_value("BUY")
        if total_cost <= available_cash:
            return BuyQuantityResult(
                quantity=rounded_qty,
                estimated_cost=total_cost,
                estimated_commission=fees.commission,
                actual_pct_of_nav=total_cost / capital_base,
            )
        rounded_qty -= lot_size

    return BuyQuantityResult(
        quantity=0, estimated_cost=0.0,
        estimated_commission=0.0, actual_pct_of_nav=0.0,
    )
