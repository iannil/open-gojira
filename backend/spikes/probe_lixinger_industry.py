"""Spike: probe Lixinger to verify what industry field API actually returns.

F20 finding: stocks.industry currently stores fs_table_type values
(non_financial/bank/security/insurance/other_financial), not real申万 industry.
This breaks business_pattern_inference (matches 0) and midstream filter.

Question: Does Lixinger /cn/company endpoint return a real industry field?

Method: Pull a few representative stocks + dump ALL fields in their row
to see what industry-related keys exist.

Output: backend/spikes/output/probe_lixinger_industry_{ts}.json

Usage:
    cd backend && source .venv/bin/activate
    python spikes/probe_lixinger_industry.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx


# Mix of known stocks + resource-type we expect to map to business_patterns
PROBE_STOCKS: list[tuple[str, str]] = [
    ("600989", "宝丰能源 (煤化工)"),
    ("600219", "南山铝业 (电解铝/铝上游)"),
    ("002170", "芭田股份 (磷化工)"),
    ("002895", "川恒股份 (磷化工)"),
    ("601398", "工商银行 (银行)"),
    ("600036", "招商银行 (银行)"),
    ("600519", "贵州茅台 (白酒 — 应无 pattern)"),
    ("000001", "平安银行 (银行)"),
    ("601628", "中国人寿 (保险)"),
    ("600030", "中信证券 (证券)"),
    ("601088", "中国神华 (煤炭)"),
    ("600547", "山东黄金 (黄金)"),
    ("601899", "紫金矿业 (铜/金)"),
]


API_BASE = "https://open.lixinger.com/api/cn/company"


def load_token() -> str | None:
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
    """Fetch the full company list to build code → row index."""
    index: dict[str, dict] = {}
    page = 0
    page_size = 500
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
    output_path = output_dir / f"probe_lixinger_industry_{date_str}.json"

    token = load_token()
    if not token:
        print("[spike] FAIL: LIXINGER_TOKEN not set")
        return 1

    print(f"[spike] fetching full company index from Lixinger...")
    with httpx.Client() as client:
        index = fetch_company_index(client, token)
    print(f"[spike] index built: {len(index)} stocks")

    # Step 1: dump ALL fields of first probe stock to discover industry-related keys
    first_code = PROBE_STOCKS[0][0]
    first_row = index.get(first_code)
    if first_row is None:
        print(f"[spike] FAIL: probe code {first_code} not in index")
        return 2
    all_keys = sorted(first_row.keys())
    print(f"\n[all fields of {first_code}] ({len(all_keys)} keys)")
    for k in all_keys:
        v = first_row.get(k)
        if isinstance(v, (dict, list)):
            v_repr = f"<{type(v).__name__} len={len(v)}>"
        else:
            v_repr = repr(v)[:80]
        print(f"  {k}: {v_repr}")

    # Step 2: extract industry-like fields for each probe stock
    industry_field_candidates = [
        k for k in all_keys
        if any(x in k.lower() for x in ("industr", "sector", "swl1", "swl2", "wind", "citic", "classify"))
    ]
    print(f"\n[industry-like field candidates] {industry_field_candidates}")

    results = {}
    for code, label in PROBE_STOCKS:
        row = index.get(code)
        if row is None:
            results[code] = {"label": label, "in_index": False, "raw": None}
            continue
        results[code] = {
            "label": label,
            "in_index": True,
            "name": row.get("name"),
            "industry_related_fields": {
                k: row.get(k) for k in industry_field_candidates
            },
            "current_pipeline_fields": {
                "fs_table_type": row.get("fsTableType"),
                "fsType": row.get("fsType"),
                "exchange": row.get("exchange"),
            },
        }

    # Step 3: cross-check vs business_patterns.lixinger_industries_json
    db_path = Path(__file__).parent.parent / "data" / "gojira.db"
    patterns_industries: dict[str, list] = {}
    if db_path.exists():
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        try:
            for name, raw_json in conn.execute(
                "SELECT name, lixinger_industries_json FROM business_patterns"
            ).fetchall():
                try:
                    patterns_industries[name] = json.loads(raw_json) if raw_json else []
                except Exception:
                    patterns_industries[name] = [f"<decode_error: {raw_json!r:.80}>"]
        finally:
            conn.close()

    artifact = {
        "ok": True,
        "timestamp": date_str,
        "description": "F20 spike: probe Lixinger /cn/company for actual industry field",
        "total_index_size": len(index),
        "first_code_all_fields": dict(first_row),
        "industry_field_candidates": industry_field_candidates,
        "per_stock": results,
        "business_patterns_industries_json": patterns_industries,
        "key_questions": {
            "does_lixinger_return_industry": any(
                "industr" in k.lower() or "swl" in k.lower() or "wind" in k.lower()
                for k in all_keys
            ),
            "field_to_use_if_exists": (
                next((k for k in all_keys if "industr" in k.lower() and "type" not in k.lower()), None)
                or "NO_INDUSTRY_FIELD_FOUND"
            ),
        },
    }
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, default=str))
    print(f"\n[spike] artifact → {output_path}")

    # Verdict
    has_industry = artifact["key_questions"]["does_lixinger_return_industry"]
    field_to_use = artifact["key_questions"]["field_to_use_if_exists"]
    print(f"\n[verdict] Lixinger returns industry: {has_industry}")
    print(f"[verdict] Field to use: {field_to_use}")
    if has_industry and field_to_use != "NO_INDUSTRY_FIELD_FOUND":
        print("[verdict] → Recommend fix F20 by syncing this field to stocks.industry")
    else:
        print("[verdict] → Lixinger does NOT return industry. Need different approach (e.g. /cn/company/detail endpoint, or remove business_pattern_inference)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
