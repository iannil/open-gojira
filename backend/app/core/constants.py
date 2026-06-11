"""Business constants — single source of truth for thresholds and limits."""

# Portfolio position limits
MAX_POSITION_WEIGHT = 20.0       # % — single stock max weight
MAX_INDUSTRY_WEIGHT = 15.0       # % — single industry max weight

# Rebalancing signal thresholds (pnl_pct)
REBALANCE_GREEN_THRESHOLD = 15.0   # % — strong performer signal
REBALANCE_RED_THRESHOLD = -10.0    # % — weak performer signal
REBALANCE_SHORT_TERM_DAYS = 30     # days — short-term volatility grace period
