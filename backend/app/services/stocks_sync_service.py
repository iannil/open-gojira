"""Stock-list sync helpers extracted from routers/stocks.py.

The sync workflow itself stays in the router (it composes many DB ops);
this module owns the Lixinger-specific HTTP shape so the router talks to
domain functions instead of inline httpx calls.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.lixinger_client import LixingerClient

logger = logging.getLogger(__name__)


def fetch_industry_constituents(
    industry_codes: list[str],
    industry_name_map: dict[str, str],
    client: LixingerClient,
) -> dict[str, str]:
    """Fetch stock-to-industry mapping from Lixinger industry constituents API.

    Args:
        industry_codes: Level-1 SW 2021 industry codes.
        industry_name_map: {industry_code: industry_name} from industry list.
        client: LixingerClient instance (uses internal _post with token).

    Returns {stock_code: industry_name}. Batches at 100 codes per request
    (Lixinger's documented limit); per-batch failures are logged and skipped
    so partial results still flow through.
    """
    stock_industry_map: dict[str, str] = {}

    for i in range(0, len(industry_codes), 100):
        batch_codes = industry_codes[i : i + 100]
        try:
            result = client._post(
                "/cn/industry/constituents/sw_2021",
                {"stockCodes": batch_codes, "date": "latest"},
            )
            if not result:
                continue

            for item in result if isinstance(result, list) else result.get("data", []):
                ind_code = item.get("stockCode", "")
                ind_name = industry_name_map.get(ind_code, "")
                for c in item.get("constituents", []):
                    sc = c.get("stockCode", "")
                    if sc and ind_name:
                        stock_industry_map[sc] = ind_name
        except Exception:
            logger.exception(
                "Failed to fetch constituents for batch %d-%d", i, i + 100
            )

    return stock_industry_map
