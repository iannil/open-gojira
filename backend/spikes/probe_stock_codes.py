"""Spike: probe Lixinger to verify 6 stock codes for Batch 4 invest-alignment.

Batch 4 N1 needs to seed 10 stocks with `tier` field (heaven / mystic). 4 codes
are already in BUILTIN_RESOURCE_LEADERS (verified). 6 codes need Lixinger
verification before seeding:

  - DSL (大参林)         target: 603233
  - HXYH (华夏银行)      target: 600015
  - 菜百股份              target: 605599
  - GGGF (国光股份)       target: 002749
  - YTKG (云天化)         target: 600096  (invest3 text ambiguous: 云天化/云图?)
  - 九华旅游              target: 603199

For each, this spike calls /cn/company/profile and verifies:
  (1) the code resolves to a valid company (HTTP 200 + data array non-empty)
  (2) the returned `name` matches the expected Chinese name

Output artifact: backend/spikes/output/probe_stock_codes_{ts}.json

Usage:
    cd backend && source .venv/bin/activate
    python spikes/probe_stock_codes.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx


# (code, expected_name_keyword, invest3_role, invest3_section)
TEST_STOCKS: list[tuple[str, str, str, str]] = [
    # 6 codes to verify
    ("603233", "大参林", "天阶 (药店规模效应)", "invest3 §七章 §医药零售"),
    ("600015", "华夏银行", "天阶 (银行盲盒可视化)", "invest3 §银行 案例"),
    ("605599", "菜百", "天阶 (黄金金融安全)", "invest3 §七章 §黄金"),
    ("002749", "国光", "玄阶 (植物生长调节剂 + 治理瑕疵)", "invest3 §十章 §效率革命"),
    ("600096", "云天化", "玄阶 (磷矿 '吃饼' 预期)", "invest3 §九章 §进度条战法"),
    ("603199", "九华", "玄阶 (消费降级 + 数人头)", "invest3 §十一章 §寺庙游"),
    # 4 already-verified controls (sanity check that API is responsive)
    ("600989", "宝丰", "天阶 (煤化工)", "invest3 §五章 §煤化工"),
    ("600219", "南山", "天阶 (电解铝出海)", "invest3 §六章 §铝业"),
    ("002170", "芭田", "天阶 (磷矿)", "invest3 §八章 §磷矿"),
    ("002895", "川恒", "天阶 (磷化工)", "invest3 §八章 §磷化工"),
]


API_BASE = "https://open.lixinger.com/api/cn/company"


def load_token() -> str | None:
    """Load Lixinger token from env or .env file."""
    token = os.getenv("LIXINGER_TOKEN")
    if token:
        return token
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("LIXINGER_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def fetch_company_index(client: httpx.Client, token: str) -> dict[str, dict]:
    """Fetch the full company list from /cn/company and build code → row index.

    The /cn/company endpoint returns paginated full list (pageSize capped at 500).
    Iterate all pages to build a complete lookup table.
    """
    index: dict[str, dict] = {}
    page = 0
    page_size = 500  # Lixinger cap
    while True:
        payload = {"token": token, "pageIndex": page, "pageSize": page_size}
        try:
            r = client.post(API_BASE, json=payload, timeout=30)
        except Exception as e:
            print(f"[fetch] page {page} error: {type(e).__name__}: {e}")
            break
        if r.status_code != 200:
            print(f"[fetch] page {page} http_{r.status_code}: {r.text[:200]}")
            break
        try:
            body = r.json()
        except Exception as e:
            print(f"[fetch] page {page} json_decode: {e}")
            break
        if body.get("code") != 1:
            print(f"[fetch] page {page} biz_code={body.get('code')}: {body.get('error') or body.get('message')}")
            break
        data = body.get("data") or []
        if not data:
            break
        for row in data:
            code = row.get("stockCode") or row.get("code")
            if code:
                index[code] = row
        if len(data) < page_size:
            break
        page += 1
    return index


def main() -> int:
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    output_path = output_dir / f"probe_stock_codes_{date_str}.json"

    token = load_token()
    if not token:
        print("[spike] FAIL: LIXINGER_TOKEN not set")
        return 1

    print(f"[spike] fetching full company index from Lixinger...")
    with httpx.Client() as client:
        index = fetch_company_index(client, token)
    print(f"[spike] index built: {len(index)} stocks")

    results = {}
    for code, expected, role, section in TEST_STOCKS:
        row = index.get(code)
        if row is None:
            outcome = {
                "code_resolves": False,
                "returned_name": None,
                "name_matches": False,
                "error": "code_not_in_index",
                "raw": None,
            }
        else:
            returned_name = (row.get("name") or "").strip()
            outcome = {
                "code_resolves": True,
                "returned_name": returned_name,
                "name_matches": expected in returned_name,
                "error": None,
                "raw": {
                    k: row.get(k)
                    for k in ("stockCode", "name", "exchange", "industry", "listingStatus", "ipoDate")
                    if k in row
                },
            }
        tag = "✓" if outcome["code_resolves"] and outcome["name_matches"] else (
            "?" if outcome["code_resolves"] and not outcome["name_matches"] else "✗"
        )
        print(f"  {tag} {code} ({role})")
        print(f"      expected_keyword={expected!r} → returned={outcome['returned_name']!r}")
        if outcome["error"]:
            print(f"      error: {outcome['error']}")
        results[code] = {
            "expected_keyword": expected,
            "role": role,
            "section": section,
            **outcome,
        }

    # Aggregate verdicts
    six_to_verify = [c for c, _, _, _ in TEST_STOCKS if c in {
        "603233", "600015", "605599", "002749", "600096", "603199"
    }]
    four_controls = [c for c, _, _, _ in TEST_STOCKS if c in {
        "600989", "600219", "002170", "002895"
    }]

    six_pass = sum(1 for c in six_to_verify if results[c]["code_resolves"] and results[c]["name_matches"])
    four_pass = sum(1 for c in four_controls if results[c]["code_resolves"] and results[c]["name_matches"])

    mismatches = [
        {
            "code": c,
            "expected_keyword": results[c]["expected_keyword"],
            "returned_name": results[c]["returned_name"],
            "role": results[c]["role"],
        }
        for c in six_to_verify
        if results[c]["code_resolves"] and not results[c]["name_matches"]
    ]
    unresolved = [
        {"code": c, "error": results[c]["error"], "role": results[c]["role"]}
        for c in six_to_verify
        if not results[c]["code_resolves"]
    ]

    artifact = {
        "ok": True,
        "timestamp": date_str,
        "description": "Batch 4 invest-alignment: verify 6 stock codes for tier seeding",
        "test_stocks": [
            {"code": c, "expected_keyword": e, "role": r, "section": s}
            for c, e, r, s in TEST_STOCKS
        ],
        "results": results,
        "summary": {
            "six_to_verify_pass": six_pass,
            "six_to_verify_total": len(six_to_verify),
            "four_controls_pass": four_pass,
            "four_controls_total": len(four_controls),
            "all_pass": six_pass == len(six_to_verify) and four_pass == len(four_controls),
        },
        "mismatches": mismatches,
        "unresolved": unresolved,
        "key_findings": {
            "all_codes_valid": six_pass == len(six_to_verify),
            "ytkg_clarification": (
                "invest3 文本对 YTKG 含歧义 ('云天化/云图?')。若 600096 返回 '云天化' 则锁定。"
            ),
        },
        "next_steps_if_all_pass": [
            "1. backend/app/services/builtin_seeder.py: add BUILTIN_HEAVEN_TIER_CODES = [600989, 600219, 002170, 603233, 600015, 605599, 002895]",
            "2. backend/app/services/builtin_seeder.py: add BUILTIN_MYSTIC_TIER_CODES = [002749, 600096, 603199]",
            "3. backend/app/services/builtin_seeder.py: add seed_tier() function",
            "4. backend/app/services/builtin_seeder.py: call seed_tier() from seed_all()",
        ],
        "next_steps_if_mismatch": [
            "1. For each code in mismatches: investigate returned name, possibly correct expected_keyword",
            "2. If code itself wrong: search Lixinger company list for the right code",
            "3. Re-run spike after correction",
        ],
    }
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, default=str))
    print(f"\n[spike] artifact → {output_path}")
    print(f"\n[summary] 6 to verify: {six_pass}/{len(six_to_verify)} pass | 4 controls: {four_pass}/{len(four_controls)} pass")
    if mismatches:
        print(f"[mismatches] {len(mismatches)}: {[(m['code'], m['expected_keyword'], m['returned_name']) for m in mismatches]}")
    if unresolved:
        print(f"[unresolved] {len(unresolved)}: {[(u['code'], u['error']) for u in unresolved]}")

    return 0 if artifact["summary"]["all_pass"] else 2


if __name__ == "__main__":
    sys.exit(main())
