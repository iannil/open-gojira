"""Lixinger (理杏仁) API client — the sole data source for Gojira.

Provides typed methods for all Lixinger open API endpoints used by the system.
All requests are POST with JSON body containing a `token` field.
Results are cached in-memory with configurable TTL.
"""

import json
import logging
import threading
import time
from datetime import datetime
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://open.lixinger.com/api"
_TIMEOUT = 30.0
_MAX_CACHE_SIZE = 500


class LixingerError(Exception):
    """Raised when the Lixinger API returns a non-success response."""


class _TTLCache:
    """Simple TTL cache with max size and LRU-style eviction."""

    def __init__(self, maxsize: int = _MAX_CACHE_SIZE):
        self._cache: dict[str, tuple[float, Any]] = {}
        self._maxsize = maxsize
        self._lock = threading.Lock()

    def get(self, key: str, ttl: float) -> Optional[Any]:
        with self._lock:
            if key in self._cache:
                ts, value = self._cache[key]
                if time.monotonic() - ts < ttl:
                    return value
                del self._cache[key]
        return None

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if len(self._cache) >= self._maxsize:
                # Evict oldest entries (first 20%)
                to_remove = max(1, self._maxsize // 5)
                keys = list(self._cache.keys())[:to_remove]
                for k in keys:
                    del self._cache[k]
            self._cache[key] = (time.monotonic(), value)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


class LixingerClient:
    """Low-level Lixinger API client with caching."""

    def __init__(self, token: str = ""):
        self._token = token or settings.LIXINGER_TOKEN
        self._cache = _TTLCache()
        self._client = httpx.Client(timeout=_TIMEOUT)

    def _post(self, path: str, payload: dict, cache_ttl: float = 0) -> Any:
        """Send a POST request to the Lixinger API.

        Args:
            path: API path, e.g. "/cn/company".
            payload: JSON body (token will be injected automatically).
            cache_ttl: Cache TTL in seconds. 0 means no caching.

        Returns:
            The `data` field from the API response.

        Raises:
            LixingerError: If the API returns a non-success code.
        """
        # Stable cache key: JSON with sorted keys, excludes token for security
        safe_payload = {k: v for k, v in payload.items() if k != "token"}
        cache_key = f"{path}:{json.dumps(safe_payload, sort_keys=True, default=str)}"
        if cache_ttl > 0:
            cached = self._cache.get(cache_key, cache_ttl)
            if cached is not None:
                return cached

        body = {**payload, "token": self._token}
        url = f"{_BASE_URL}{path}"

        try:
            resp = self._client.post(url, json=body)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error("Lixinger API error %s: %s", path, e.response.text)
            raise LixingerError(f"API returned {e.response.status_code}: {path}") from e
        except httpx.RequestError as e:
            logger.error("Lixinger request failed %s: %s", path, e)
            raise LixingerError(f"Request failed: {path}") from e

        result = resp.json()
        if result.get("code") != 1:
            msg = result.get("message", "unknown error")
            logger.error("Lixinger API returned error for %s: %s", path, msg)
            raise LixingerError(f"API error: {msg}")

        data = result.get("data")

        if cache_ttl > 0:
            self._cache.set(cache_key, data)

        return data

    # ── Company ──────────────────────────────────────────────────────────

    def get_company_list(self, page: int = 0, page_size: int = 5000) -> list[dict]:
        """Get paginated list of all A-share stocks."""
        data = self._post(
            "/cn/company",
            {"pageIndex": page, "pageSize": page_size},
            cache_ttl=86400,  # 24h — stock list rarely changes
        )
        return data or []

    def get_company_profile(self, stock_code: str) -> Optional[dict]:
        """Get company profile for a single stock."""
        data = self._post(
            "/cn/company/profile",
            {"stockCodes": [stock_code]},
            cache_ttl=3600,
        )
        return data[0] if data else None

    # ── Fundamentals (valuation) ─────────────────────────────────────────

    def get_fundamentals(
        self,
        stock_codes: list[str],
        date: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        metrics: Optional[list[str]] = None,
    ) -> list[dict]:
        """Get fundamental valuation data (PE/PB/PS/dividend yield + percentile stats).

        Default metrics include core valuation indicators. Supports up to 100 stocks
        per request (48 metrics max for multi-stock, 36 for single-stock).
        """
        if metrics is None:
            metrics = [
                "pe_ttm", "d_pe_ttm", "pb", "pb_wo_gw", "ps_ttm",
                "pcf_ttm", "dyr", "mc", "mc_om", "cmc", "sp",
            ]
        payload: dict[str, Any] = {"stockCodes": stock_codes, "metricsList": metrics}
        if date:
            payload["date"] = date
        elif start_date:
            payload["startDate"] = start_date
            if end_date:
                payload["endDate"] = end_date
        else:
            # Lixinger requires at least one of date or startDate
            payload["date"] = "latest"

        cache_ttl = 900 if not start_date else 3600  # 15min for latest, 1h for historical
        return self._post("/cn/company/fundamental/non_financial", payload, cache_ttl=cache_ttl) or []

    FUNDAMENTAL_ENDPOINTS = {
        "non_financial": "/cn/company/fundamental/non_financial",
        "bank": "/cn/company/fundamental/bank",
        "insurance": "/cn/company/fundamental/insurance",
        "security": "/cn/company/fundamental/security",
        "other_financial": "/cn/company/fundamental/other_financial",
    }

    def get_fundamentals_at_endpoint(
        self,
        endpoint_kind: str,
        stock_codes: list[str],
        date: Optional[str] = None,
        metrics: Optional[list[str]] = None,
    ) -> list[dict]:
        """Get fundamentals from a specific industry endpoint.

        Lixinger's /non_financial endpoint silently returns empty for stocks
        from financial industries (banks/insurance/securities). Dispatch to
        the matching endpoint by industry kind to recover those rows.
        """
        endpoint = self.FUNDAMENTAL_ENDPOINTS.get(endpoint_kind)
        if not endpoint:
            raise LixingerError(f"Unknown fundamental endpoint kind: {endpoint_kind}")
        if metrics is None:
            metrics = (
                ["pe_ttm", "d_pe_ttm", "pb", "pb_wo_gw", "ps_ttm",
                 "pcf_ttm", "dyr", "mc", "mc_om", "cmc", "sp"]
                if endpoint_kind == "non_financial"
                else ["pe_ttm", "pb", "dyr", "mc", "sp"]
            )
        payload: dict[str, Any] = {"stockCodes": stock_codes, "metricsList": metrics}
        payload["date"] = date or "latest"
        return self._post(endpoint, payload, cache_ttl=900) or []

    def _financial_fundamental(
        self,
        endpoint: str,
        stock_codes: list[str],
        date: Optional[str],
        start_date: Optional[str],
        end_date: Optional[str],
        metrics: Optional[list[str]],
    ) -> list[dict]:
        if metrics is None:
            metrics = ["pe_ttm", "pb", "dyr", "mc"]
        payload: dict[str, Any] = {"stockCodes": stock_codes, "metricsList": metrics}
        if date:
            payload["date"] = date
        elif start_date:
            payload["startDate"] = start_date
            if end_date:
                payload["endDate"] = end_date
        else:
            payload["date"] = datetime.now().strftime("%Y-%m-%d")
        return self._post(endpoint, payload, cache_ttl=900) or []

    def get_fundamentals_for_bank(self, stock_codes, date=None, start_date=None, end_date=None, metrics=None):
        return self._financial_fundamental(
            "/cn/company/fundamental/bank", stock_codes, date, start_date, end_date, metrics
        )

    def get_fundamentals_for_insurance(self, stock_codes, date=None, start_date=None, end_date=None, metrics=None):
        return self._financial_fundamental(
            "/cn/company/fundamental/insurance", stock_codes, date, start_date, end_date, metrics
        )

    def get_fundamentals_for_security(self, stock_codes, date=None, start_date=None, end_date=None, metrics=None):
        return self._financial_fundamental(
            "/cn/company/fundamental/security", stock_codes, date, start_date, end_date, metrics
        )

    def get_fundamentals_for_other_financial(self, stock_codes, date=None, start_date=None, end_date=None, metrics=None):
        return self._financial_fundamental(
            "/cn/company/fundamental/other_financial", stock_codes, date, start_date, end_date, metrics
        )

    # ── Financial statements ─────────────────────────────────────────────

    def get_financials(
        self,
        stock_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        date: Optional[str] = None,
        metrics: Optional[list[str]] = None,
        granularity: str = "q",
    ) -> list[dict]:
        """Get financial statement data (income/balance/cash-flow + indicators).

        Uses the non-financial endpoint. For banks/securities/insurance, use
        get_financials_for_bank() etc.

        Single stock only when using date range (Lixinger constraint).
        Supports up to 128 metrics for a single stock.
        """
        if metrics is None:
            metrics = [
                # Balance sheet
                f"{granularity}.bs.ta.t", f"{granularity}.bs.tl.t", f"{granularity}.bs.toe.t",
                f"{granularity}.bs.tca.t", f"{granularity}.bs.tcl.t",
                f"{granularity}.bs.cabb.t", f"{granularity}.bs.gw.t",
                f"{granularity}.bs.tsc.t", f"{granularity}.bs.mc.t",
                # Income statement
                f"{granularity}.ps.toi.t", f"{granularity}.ps.oi.t",
                f"{granularity}.ps.oc.t", f"{granularity}.ps.gp_m.t",
                f"{granularity}.ps.np.t", f"{granularity}.ps.npatoshopc.t",
                f"{granularity}.ps.beps.t",
                f"{granularity}.ps.da.t", f"{granularity}.ps.d_np_r.t",
                # Cash flow
                f"{granularity}.cfs.ncffoa.t", f"{granularity}.cfs.ncffia.t",
                f"{granularity}.cfs.ncfffa.t",
                # Financial indicators
                f"{granularity}.m.wroe.t", f"{granularity}.m.roa.t",
                f"{granularity}.m.np_s_r.t", f"{granularity}.m.gp_m.t",
                f"{granularity}.m.tl_ta_r.t", f"{granularity}.m.c_r.t",
                f"{granularity}.m.q_r.t", f"{granularity}.m.i_tor.t",
                f"{granularity}.m.ncffoa_np_r.t", f"{granularity}.m.fcf.t",
            ]
        payload: dict[str, Any] = {
            "stockCodes": [stock_code],
            "metricsList": metrics,
        }
        if date:
            payload["date"] = date
        elif start_date:
            payload["startDate"] = start_date
            if end_date:
                payload["endDate"] = end_date
        else:
            payload["startDate"] = "2019-01-01"

        return self._post("/cn/company/fs/non_financial", payload, cache_ttl=3600) or []

    def _financial_fs(
        self,
        endpoint: str,
        stock_code: str,
        start_date: Optional[str],
        end_date: Optional[str],
        date: Optional[str],
        metrics: Optional[list[str]],
        granularity: str = "y",
    ) -> list[dict]:
        """Generic financial-industry FS fetcher with safe default metrics."""
        if metrics is None:
            # Use a minimal common subset; callers needing industry-specific metrics
            # should pass them explicitly. These are present on all four FS variants.
            metrics = [
                f"{granularity}.ps.toi.t", f"{granularity}.ps.np.t",
                f"{granularity}.bs.ta.t", f"{granularity}.bs.tl.t",
                f"{granularity}.bs.toe.t",
                f"{granularity}.m.wroe.t", f"{granularity}.m.roa.t",
            ]
        payload: dict[str, Any] = {"stockCodes": [stock_code], "metricsList": metrics}
        if date:
            payload["date"] = date
        elif start_date:
            payload["startDate"] = start_date
            if end_date:
                payload["endDate"] = end_date
        else:
            payload["startDate"] = "2019-01-01"
        return self._post(endpoint, payload, cache_ttl=3600) or []

    def get_financials_for_bank(self, stock_code, start_date=None, end_date=None, date=None, metrics=None, granularity="y"):
        return self._financial_fs("/cn/company/fs/bank", stock_code, start_date, end_date, date, metrics, granularity)

    def get_financials_for_insurance(self, stock_code, start_date=None, end_date=None, date=None, metrics=None, granularity="y"):
        return self._financial_fs("/cn/company/fs/insurance", stock_code, start_date, end_date, date, metrics, granularity)

    def get_financials_for_security(self, stock_code, start_date=None, end_date=None, date=None, metrics=None, granularity="y"):
        return self._financial_fs("/cn/company/fs/security", stock_code, start_date, end_date, date, metrics, granularity)

    def get_financials_for_other_financial(self, stock_code, start_date=None, end_date=None, date=None, metrics=None, granularity="y"):
        return self._financial_fs("/cn/company/fs/other_financial", stock_code, start_date, end_date, date, metrics, granularity)

    # ── K-line (candlestick) ─────────────────────────────────────────────

    def get_kline(
        self,
        stock_code: str,
        start_date: str,
        end_date: Optional[str] = None,
        kline_type: str = "lxr_fc_rights",
    ) -> list[dict]:
        """Get daily K-line data for a stock.

        Args:
            stock_code: Single stock code.
            start_date: Required start date (YYYY-MM-DD).
            end_date: Optional end date.
            kline_type: Adjustment type. Default lxr_fc_rights (理杏仁前复权).
        """
        payload: dict[str, Any] = {"stockCode": stock_code, "startDate": start_date, "type": kline_type}
        if end_date:
            payload["endDate"] = end_date
        return self._post("/cn/company/candlestick", payload, cache_ttl=900) or []

    # ── Index ────────────────────────────────────────────────────────────

    def get_index_kline(
        self,
        stock_code: str,
        start_date: str,
        end_date: Optional[str] = None,
        kline_type: str = "normal",
    ) -> list[dict]:
        """Get daily K-line for an index.

        Args:
            stock_code: Index code (e.g. '000016' for 上证50).
            start_date: Required start date (YYYY-MM-DD).
            end_date: Optional end date.
            kline_type: normal or total_return. Default normal.
        """
        payload: dict[str, Any] = {"stockCode": stock_code, "startDate": start_date, "type": kline_type}
        if end_date:
            payload["endDate"] = end_date
        return self._post("/cn/index/candlestick", payload, cache_ttl=900) or []

    def get_index_fundamental(
        self,
        stock_codes: list[str],
        date: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        metrics: Optional[list[str]] = None,
    ) -> list[dict]:
        """Get fundamental data for indices.

        Supports single-date or date-range queries.
        For date ranges, pass start_date (and optionally end_date) instead of date.
        """
        if metrics is None:
            metrics = ["pe_ttm.mcw", "pb.mcw", "dyr.mcw", "mc"]
        payload: dict[str, Any] = {"stockCodes": stock_codes, "metricsList": metrics}
        if start_date:
            payload["startDate"] = start_date
            if end_date:
                payload["endDate"] = end_date
        elif date:
            payload["date"] = date
        else:
            payload["date"] = datetime.now().strftime("%Y-%m-%d")
        cache_ttl = 3600 if start_date else 900
        return self._post("/cn/index/fundamental", payload, cache_ttl=cache_ttl) or []

    # ── Industry ─────────────────────────────────────────────────────────

    def get_industry_list(self, source: str = "sw_2021") -> list[dict]:
        """Get list of all Shenwan (申万) industries.

        Args:
            source: Industry classification source. Options: "sw", "sw_2021", "cni".
        """
        return self._post(
            "/cn/industry",
            {"source": source},
            cache_ttl=86400,
        ) or []

    def get_industry_constituents(self, industry_code: str) -> list[dict]:
        """Get constituent stocks of an industry (SW 2021 classification)."""
        return self._post(
            "/cn/industry/constituents/sw_2021",
            {"stockCodes": [industry_code]},
            cache_ttl=86400,
        ) or []

    def get_industry_fundamental(
        self,
        stock_codes: list[str],
        date: Optional[str] = None,
        metrics: Optional[list[str]] = None,
    ) -> list[dict]:
        """Get fundamental data for SW 2021 industries.

        Args:
            stock_codes: Industry codes (required). Get from get_industry_list().
            date: Specific date (YYYY-MM-DD). Defaults to today.
            metrics: Metrics to fetch.
        """
        if metrics is None:
            metrics = ["pe_ttm.mcw", "pb.mcw", "dyr.mcw"]
        payload: dict[str, Any] = {"stockCodes": stock_codes, "metricsList": metrics}
        if date:
            payload["date"] = date
        else:
            payload["date"] = datetime.now().strftime("%Y-%m-%d")
        return self._post(
            "/cn/industry/fundamental/sw_2021",
            payload,
            cache_ttl=900,
        ) or []

    # ── Dividend ─────────────────────────────────────────────────────────

    def get_dividend(self, stock_code: str, start_date: str, end_date: Optional[str] = None) -> list[dict]:
        """Get dividend history for a stock.

        Args:
            stock_code: Single stock code.
            start_date: Required start date (YYYY-MM-DD).
            end_date: Optional end date.
        """
        payload: dict[str, Any] = {"stockCode": stock_code, "startDate": start_date}
        if end_date:
            payload["endDate"] = end_date
        return self._post("/cn/company/dividend", payload, cache_ttl=3600) or []

    # ── Shareholders / Customers / Suppliers ─────────────────────────────

    def get_shareholders_num(self, stock_code: str, start_date: str, end_date: Optional[str] = None) -> list[dict]:
        """Get shareholder count history (筹码集中度 indicator)."""
        payload: dict[str, Any] = {"stockCode": stock_code, "startDate": start_date}
        if end_date:
            payload["endDate"] = end_date
        return self._post("/cn/company/shareholders-num", payload, cache_ttl=86400) or []

    def get_customers(self, stock_code: str, start_date: str, end_date: Optional[str] = None) -> list[dict]:
        """Get major customers history (上游议价 indicator)."""
        payload: dict[str, Any] = {"stockCode": stock_code, "startDate": start_date}
        if end_date:
            payload["endDate"] = end_date
        return self._post("/cn/company/customers", payload, cache_ttl=86400) or []

    def get_suppliers(self, stock_code: str, start_date: str, end_date: Optional[str] = None) -> list[dict]:
        """Get major suppliers history (下游议价 indicator)."""
        payload: dict[str, Any] = {"stockCode": stock_code, "startDate": start_date}
        if end_date:
            payload["endDate"] = end_date
        return self._post("/cn/company/suppliers", payload, cache_ttl=86400) or []

    def get_majority_shareholders(self, stock_code: str, start_date: str, end_date: Optional[str] = None) -> list[dict]:
        """Get top 10 shareholders.

        Args:
            stock_code: Single stock code.
            start_date: Required start date (YYYY-MM-DD).
            end_date: Optional end date.
        """
        payload: dict[str, Any] = {"stockCode": stock_code, "startDate": start_date}
        if end_date:
            payload["endDate"] = end_date
        return self._post("/cn/company/majority-shareholders", payload, cache_ttl=86400) or []

    # ── Revenue composition ──────────────────────────────────────────────

    def get_revenue_composition(
        self,
        stock_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[dict]:
        """Get revenue composition breakdown by business segment.

        Lixinger endpoint: /cn/company/operation/revenue/structure.
        Returns annual segment data per report period; exact field layout depends
        on the company's disclosure (industry/product/region/customer).
        """
        payload: dict[str, Any] = {"stockCode": stock_code}
        if start_date:
            payload["startDate"] = start_date
        else:
            payload["startDate"] = "2019-01-01"
        if end_date:
            payload["endDate"] = end_date
        return self._post(
            "/cn/company/operation/revenue/structure",
            payload,
            cache_ttl=86400,
        ) or []

    # ── Capital flow ─────────────────────────────────────────────────────

    def get_index_mutual_market(
        self,
        stock_code: str,
        start_date: str,
        end_date: Optional[str] = None,
    ) -> list[dict]:
        """Get northbound (互联互通) capital flow data for an index.

        Args:
            stock_code: Index code (e.g. '000300').
            start_date: Required start date (YYYY-MM-DD).
            end_date: Optional end date.
        """
        payload: dict[str, Any] = {"stockCode": stock_code, "startDate": start_date}
        if end_date:
            payload["endDate"] = end_date
        return self._post("/cn/index/mutual-market", payload, cache_ttl=900) or []

    def get_mutual_market(
        self,
        stock_code: str,
        start_date: str,
        end_date: Optional[str] = None,
    ) -> list[dict]:
        """Get northbound (互联互通) capital flow data for a stock.

        Args:
            stock_code: Single stock code.
            start_date: Required start date (YYYY-MM-DD).
            end_date: Optional end date.
        """
        payload: dict[str, Any] = {"stockCode": stock_code, "startDate": start_date}
        if end_date:
            payload["endDate"] = end_date
        return self._post("/cn/company/mutual-market", payload, cache_ttl=900) or []

    def get_margin_trading(
        self,
        stock_code: str,
        start_date: str,
        end_date: Optional[str] = None,
    ) -> list[dict]:
        """Get margin trading (融资融券) data for a stock.

        Args:
            stock_code: Single stock code.
            start_date: Required start date (YYYY-MM-DD).
            end_date: Optional end date.
        """
        payload: dict[str, Any] = {"stockCode": stock_code, "startDate": start_date}
        if end_date:
            payload["endDate"] = end_date
        return self._post(
            "/cn/company/margin-trading-and-securities-lending",
            payload,
            cache_ttl=900,
        ) or []


# ── Module-level singleton ───────────────────────────────────────────────

_client: Optional[LixingerClient] = None
_client_lock = threading.Lock()


def get_lixinger_client() -> LixingerClient:
    """Get or create the shared LixingerClient instance.

    Double-checked locking guards against two requests racing to construct
    the client (and httpx.Client) on cold start under the threaded uvicorn
    worker — historically harmless but burns a token on each duplicate init.
    """
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = LixingerClient()
    return _client
