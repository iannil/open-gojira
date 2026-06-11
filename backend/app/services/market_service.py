"""Market data service — fetches market indices, sector data, and capital flow from Lixinger."""

import logging

from app.services.lixinger_client import get_lixinger_client, LixingerError

logger = logging.getLogger(__name__)

# Major A-share index codes
INDEX_CODES = {
    "000001": "上证指数",
    "399001": "深证成指",
    "399006": "创业板指",
    "000016": "上证50",
    "000300": "沪深300",
    "000905": "中证500",
}


def fetch_market_indices() -> list[dict]:
    """Fetch current data for major A-share indices.

    Returns:
        List of {"code": ..., "name": ..., "close": ..., "change_pct": ...}.
    """
    try:
        client = get_lixinger_client()
        codes = list(INDEX_CODES.keys())
        data = client.get_index_fundamental(
            stock_codes=codes,
            metrics=["cp", "cpc"],
        )
        results = []
        for item in data:
            code = item.get("stockCode", "")
            results.append({
                "code": code,
                "name": INDEX_CODES.get(code, code),
                "close": item.get("cp"),
                "change_pct": item.get("cpc"),
            })
        return results
    except LixingerError:
        logger.exception("Failed to fetch market indices")
        return []


