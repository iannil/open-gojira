"""Spike: 验证 Lixinger token 真实有效性 (解 P0-2).

之前 STATUS.md 第 254 行基于口头报告标 ✅,无 artifact 留存。
本次重跑并落 artifact,确保论断可 reproduce。

用法:
    cd backend && source .venv/bin/activate
    python spikes/lixinger_token_verification.py

输出:
    backend/spikes/output/lixinger_token_verification_{date}.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.lixinger_client import LixingerClient  # noqa: E402


def main() -> int:
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    output_path = output_dir / f"lixinger_token_verification_{date_str}.json"

    print(f"[spike] Lixinger token verification — {date_str}")

    try:
        client = LixingerClient()
    except Exception as e:
        print(f"[FAIL] Client init: {e}")
        output_path.write_text(json.dumps({
            "ok": False,
            "stage": "client_init",
            "error": str(e),
            "timestamp": date_str,
        }, ensure_ascii=False, indent=2))
        return 1

    print(f"[spike] token configured: len={len(client._token)} prefix={client._token[:8]}...")

    try:
        # page_size=500 受 Lixinger silent cap 限制;取 1 页足够验证 token 有效性
        companies = client.get_company_list(page=0, page_size=500)
    except Exception as e:
        print(f"[FAIL] get_company_list: {type(e).__name__}: {e}")
        output_path.write_text(json.dumps({
            "ok": False,
            "stage": "get_company_list",
            "error_type": type(e).__name__,
            "error": str(e),
            "timestamp": date_str,
        }, ensure_ascii=False, indent=2))
        return 2

    sample = companies[:5] if companies else []
    print(f"[OK] returned {len(companies)} companies")
    for c in sample:
        code = c.get("stockCode") or c.get("code") or "?"
        name = c.get("name") or c.get("stockName") or "?"
        print(f"     - {code} {name}")

    artifact = {
        "ok": True,
        "stage": "complete",
        "timestamp": date_str,
        "returned_count": len(companies),
        "sample": sample,
        "token_prefix": client._token[:8] + "...",
    }
    output_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2)
    )
    print(f"[spike] artifact → {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
