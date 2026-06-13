"""Realtime quote service — Sina hq.sinajs.cn wrapper.

S0.4 spike validated: 20/20 success, 44ms avg latency, GBK encoded.
1-minute in-memory cache to avoid hitting Sina too often.

Sina format example:
    var hq_str_sh600519="贵州茅台,1675.00,1680.00,1685.50,1690.00,1670.00,...";

Field index (validated by S0.4 spike):
    [0]=name, [1]=today_open, [2]=prev_close, [3]=current,
    [4]=high, [5]=low, ...
"""
from __future__ import annotations

import logging
import threading
import time

import requests

logger = logging.getLogger(__name__)

_SINA_URL = "https://hq.sinajs.cn/list="
_SINA_HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0 (gojira)",
}
_CACHE_TTL = 60  # seconds
_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_LOCK = threading.Lock()


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def _to_sina_code(code: str) -> str:
    """Convert A-share code to Sina format (sh/sz prefix)."""
    if code.startswith(("6", "5", "9", "11", "13")):
        return f"sh{code}"
    return f"sz{code}"


def _safe_float(s) -> float:
    try:
        v = float(s)
        return v if v == v else 0.0  # NaN check
    except (TypeError, ValueError):
        return 0.0


def _parse_sina_response(text: str) -> dict[str, dict]:
    """Parse Sina's `var hq_str_shCODE="name,prev,curr,high,low,...";` format.

    Returns dict keyed by full Sina code (e.g. 'sh600519').  Empty dict on
    garbage / no parseable lines.
    """
    result: dict[str, dict] = {}
    for line in text.strip().split("\n"):
        if "=" not in line:
            continue
        try:
            var, data = line.split("=", 1)
            # var looks like: var hq_str_sh600519
            code_with_prefix = var.split("_")[-1].strip(';"\n').lower()
            if not code_with_prefix:
                continue
            # data looks like: "贵州茅台,1,2,3,...";
            inner = data.strip().rstrip(";").strip('"')
            parts = inner.split(",")
            if len(parts) < 6:
                continue
            result[code_with_prefix] = {
                "name": parts[0],
                "prev_close": _safe_float(parts[2]),
                "current": _safe_float(parts[3]),
                "high": _safe_float(parts[4]),
                "low": _safe_float(parts[5]),
            }
        except (IndexError, ValueError) as e:
            logger.debug("Skip Sina line: %s", e)
    return result


def get_realtime_prices(codes: list[str]) -> dict[str, dict]:
    """Batch fetch realtime quotes. Returns code → quote dict.

    1-minute in-memory cache. Network errors return empty dict (never raises).
    """
    if not codes:
        return {}

    now = time.monotonic()
    result: dict[str, dict] = {}
    missing: list[str] = []
    with _CACHE_LOCK:
        for code in codes:
            cached = _CACHE.get(code)
            if cached and (now - cached[0]) < _CACHE_TTL:
                result[code] = cached[1]
            else:
                missing.append(code)

    if not missing:
        return result

    sina_codes = [_to_sina_code(c) for c in missing]
    try:
        resp = requests.get(
            _SINA_URL + ",".join(sina_codes),
            headers=_SINA_HEADERS,
            timeout=5,
        )
        resp.encoding = "gbk"
        if resp.status_code != 200:
            logger.warning("Sina HTTP %s", resp.status_code)
            return result
        parsed = _parse_sina_response(resp.text)
        # Update cache + result. Note Sina returns the prefixed code
        # (sh600519), so build a reverse lookup from missing → sina_code.
        with _CACHE_LOCK:
            for code in missing:
                sina_code = _to_sina_code(code)
                if sina_code in parsed:
                    _CACHE[code] = (now, parsed[sina_code])
                    result[code] = parsed[sina_code]
        return result
    except Exception as e:
        logger.error("Sina fetch failed: %s", e)
        return result


def get_realtime_price(code: str) -> dict | None:
    """Single code convenience wrapper."""
    prices = get_realtime_prices([code])
    return prices.get(code)
