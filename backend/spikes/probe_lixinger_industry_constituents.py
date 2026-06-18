"""Spike: probe Lixinger /cn/industry + /cn/industry/constituents/sw_2021 endpoints.

F20 plan: use these APIs to reverse-build stock_code → industry_name mapping
since /cn/company endpoint has no industry field. Output artifact for design.

Questions to answer:
1. How many sw_2021 industries are there? (L1? L2? L3?)
2. What does an industry row look like (fields)?
3. How does /cn/industry/constituents/sw_2021 work — single industry or batch?
4. Are there rate-limit concerns for fetching all constituents?

Output: backend/spikes/output/probe_lixinger_industry_constituents_{ts}.json

Usage:
    cd backend && source .venv/bin/activate
    python spikes/probe_lixinger_industry_constituents.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx


API_BASE = "https://open.lixinger.com/api/cn"


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


def main() -> int:
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    output_path = output_dir / f"probe_lixinger_industry_constituents_{date_str}.json"

    token = load_token()
    if not token:
        print("[spike] FAIL: LIXINGER_TOKEN not set")
        return 1

    artifact = {
        "ok": True,
        "timestamp": date_str,
        "description": "F20 spike: probe Lixinger industry APIs",
        "sources_tested": [],
        "industries_count_by_source": {},
        "industry_row_sample": None,
        "constituents_batch_test": None,
    }

    with httpx.Client(timeout=30) as client:
        # 1. Test all classification sources
        for source in ["sw_2021", "sw", "cni"]:
            print(f"\n[1] source={source}")
            try:
                r = client.post(
                    f"{API_BASE}/industry",
                    json={"token": token, "source": source},
                )
                body = r.json()
                if body.get("code") != 1:
                    print(f"    FAIL: {body.get('error')}")
                    artifact["sources_tested"].append({
                        "source": source, "ok": False,
                        "error": body.get("error"),
                    })
                    continue
                data = body.get("data") or []
                print(f"    OK: {len(data)} industries")
                artifact["sources_tested"].append({
                    "source": source, "ok": True, "count": len(data),
                })
                artifact["industries_count_by_source"][source] = len(data)
                if source == "sw_2021" and data:
                    # Dump first 5 industries as sample
                    artifact["industry_row_sample"] = data[:5]
                    all_codes = [d.get("stockCode") or d.get("code") for d in data]
                    print(f"    sample codes: {all_codes[:5]}")

                    # 2. Test constituents — can we pass multiple industries at once?
                    print(f"\n[2] /cn/industry/constituents/sw_2021 (batch test)")
                    # Try passing 5 industry codes at once
                    test_codes = all_codes[:5]
                    r2 = client.post(
                        f"{API_BASE}/industry/constituents/sw_2021",
                        json={"token": token, "stockCodes": test_codes},
                    )
                    body2 = r2.json()
                    if body2.get("code") != 1:
                        print(f"    FAIL: {body2.get('error')}")
                        artifact["constituents_batch_test"] = {
                            "ok": False, "error": body2.get("error"),
                            "input_codes": test_codes,
                        }
                    else:
                        data2 = body2.get("data") or []
                        print(f"    OK: {len(data2)} rows returned for 5 industries")
                        artifact["constituents_batch_test"] = {
                            "ok": True,
                            "input_codes": test_codes,
                            "returned_rows": len(data2),
                            "sample_rows": data2[:5],
                            "row_keys": sorted(data2[0].keys()) if data2 else [],
                        }
                        if data2:
                            print(f"    sample row keys: {sorted(data2[0].keys())}")

                    # 3. Try single industry
                    print(f"\n[3] /cn/industry/constituents/sw_2021 (single)")
                    single_code = all_codes[0]
                    r3 = client.post(
                        f"{API_BASE}/industry/constituents/sw_2021",
                        json={"token": token, "stockCodes": [single_code]},
                    )
                    body3 = r3.json()
                    if body3.get("code") == 1:
                        data3 = body3.get("data") or []
                        print(f"    OK: industry {single_code} has {len(data3)} constituents")
                        artifact.setdefault("constituents_single_test", {})
                        artifact["constituents_single_test"] = {
                            "ok": True,
                            "industry_code": single_code,
                            "constituent_count": len(data3),
                            "first_3_constituents": data3[:3],
                        }

                    # 4. Cost analysis
                    print(f"\n[4] Cost analysis")
                    print(f"    Total sw_2021 industries: {len(data)}")
                    print(f"    If batch=5 per request: {len(data)//5 + 1} requests")
                    print(f"    If batch=20 per request: {len(data)//20 + 1} requests")
                    artifact["cost_estimate"] = {
                        "total_industries": len(data),
                        "requests_at_batch_5": len(data) // 5 + 1,
                        "requests_at_batch_20": len(data) // 20 + 1,
                        "requests_at_batch_50": len(data) // 50 + 1,
                    }

            except Exception as e:
                print(f"    EXCEPTION: {type(e).__name__}: {e}")
                artifact["sources_tested"].append({
                    "source": source, "ok": False, "error": str(e),
                })

    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, default=str))
    print(f"\n[spike] artifact → {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
