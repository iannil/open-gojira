"""Spike: 探测 GLM web_search 调用在 response 里的真实结构。

bug #1: _count_web_search_calls 检查 tool_calls.function.name=='web_search',
但 GLM web_search 配置为 type='web_search' (非 function tool),可能不出现在 tool_calls。
本 spike 跑一次明确需要搜索的 prompt,dump 完整 response 看 web_search 调用位置。

用法:
    cd backend && source .venv/bin/activate
    python spikes/glm_web_search_shape.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from zhipuai import ZhipuAI


def main() -> int:
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    output_path = output_dir / f"glm_web_search_shape_{date_str}.json"

    print(f"[spike] GLM web_search shape probe — {date_str}")

    client = ZhipuAI(api_key=settings.ZHIPU_API_KEY)
    if settings.ZHIPU_BASE_URL:
        client_kwargs = {"base_url": settings.ZHIPU_BASE_URL}
        client = ZhipuAI(api_key=settings.ZHIPU_API_KEY, **client_kwargs)

    # 强触发搜索的 prompt
    prompt = "请搜索 2026 年 6 月最新的 A 股银行股涨幅榜,列出前 5 名和具体涨幅数字。"

    print(f"[spike] calling GLM with web_search enabled...")
    t0 = time.monotonic()
    response = client.chat.completions.create(
        model=settings.ZHIPU_MODEL,
        messages=[{"role": "user", "content": prompt}],
        tools=[
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_result": False,
                },
            },
        ],
        tool_choice="auto",
        max_tokens=2000,
        temperature=0.3,
        timeout=120,
    )
    elapsed = int(time.monotonic() - t0)
    print(f"[ok] response in {elapsed}s")

    # Dump full response as dict
    raw_dict = response.model_dump() if hasattr(response, "model_dump") else response.__dict__
    output_path.write_text(json.dumps(raw_dict, ensure_ascii=False, indent=2, default=str))
    print(f"\n[spike] full response → {output_path}")
    print(f"[spike] response size: {output_path.stat().st_size} bytes")

    # Inspect structure
    print("\n=== Response top-level keys ===")
    for k in raw_dict.keys():
        print(f"  {k}: {type(raw_dict[k]).__name__}")

    print("\n=== Choices[0] structure ===")
    choices = raw_dict.get("choices", [])
    if choices:
        ch0 = choices[0]
        for k in ch0.keys():
            v = ch0[k]
            print(f"  {k}: {type(v).__name__}", end="")
            if isinstance(v, dict):
                print(f" keys={list(v.keys())}")
            elif isinstance(v, list):
                print(f" len={len(v)}")
                if v:
                    print(f"    [0] keys: {list(v[0].keys()) if isinstance(v[0], dict) else type(v[0]).__name__}")
            else:
                print(f" value={str(v)[:80]!r}")

    print("\n=== Message structure ===")
    msg = ch0.get("message", {}) if choices else {}
    for k in msg.keys():
        v = msg[k]
        if isinstance(v, list):
            print(f"  message.{k}: list len={len(v)}")
            for i, item in enumerate(v[:3]):
                print(f"    [{i}] {json.dumps(item, ensure_ascii=False, default=str)[:200]}")
        else:
            print(f"  message.{k}: {str(v)[:200]!r}")

    # Specifically look for web_search evidence
    print("\n=== Looking for web_search evidence ===")
    found_locations = []
    _search_for_key(raw_dict, "web_search", found_locations, path="root")
    _search_for_key(raw_dict, "search_result", found_locations, path="root")
    _search_for_key(raw_dict, "tool_calls", found_locations, path="root")
    _search_for_key(raw_dict, "search", found_locations, path="root")

    print(f"\n[spike] total locations: {len(found_locations)}")
    return 0


def _search_for_key(obj, target_key: str, found: list, path: str, depth: int = 0) -> None:
    """Recursively search for target_key in dict/list, record path."""
    if depth > 8:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_path = f"{path}.{k}"
            if target_key in k.lower():
                preview = json.dumps(v, ensure_ascii=False, default=str)[:150]
                found.append({"path": new_path, "type": type(v).__name__, "preview": preview})
            _search_for_key(v, target_key, found, new_path, depth + 1)
    elif isinstance(obj, list):
        for i, item in enumerate(obj[:5]):  # limit list scan
            _search_for_key(item, target_key, found, f"{path}[{i}]", depth + 1)


if __name__ == "__main__":
    sys.exit(main())
