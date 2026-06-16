"""Spike: 验证 GLM (智谱) API token 真实可用,解 P0-1 GLM 阻塞。

之前 STATUS.md P0-1 标 "GLM 账号余额不足,429 code 1113,external blocker"。
用户称已充值,本 spike 直接调 GLM API 验证。

用法:
    cd backend && source .venv/bin/activate
    python spikes/glm_token_verification.py

输出:
    backend/spikes/output/glm_token_verification_{date}.json
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings  # noqa: E402


def main() -> int:
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    output_path = output_dir / f"glm_token_verification_{date_str}.json"

    print(f"[spike] GLM token verification — {date_str}")
    print(f"[spike] ZHIPU_API_KEY: len={len(settings.ZHIPU_API_KEY)} prefix={settings.ZHIPU_API_KEY[:8]}...")
    print(f"[spike] ZHIPU_MODEL: {settings.ZHIPU_MODEL}")
    print(f"[spike] ZHIPU_BASE_URL: {settings.ZHIPU_BASE_URL or '(default)'}")

    if not settings.ZHIPU_API_KEY:
        print("[FAIL] ZHIPU_API_KEY not configured")
        return 1

    try:
        from zhipuai import ZhipuAI
    except ImportError as e:
        print(f"[FAIL] zhipuai SDK not installed: {e}")
        return 2

    client_kwargs = {"api_key": settings.ZHIPU_API_KEY}
    if settings.ZHIPU_BASE_URL:
        client_kwargs["base_url"] = settings.ZHIPU_BASE_URL
    client = ZhipuAI(**client_kwargs)

    # Stage 1: minimal ping (1 token)
    print("\n[stage 1] Minimal ping (max_tokens=1)...")
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=settings.ZHIPU_MODEL or "glm-4.7",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            timeout=15,
        )
        elapsed_ms = int((time.time() - t0) * 1000)
        usage = getattr(resp, "usage", None)
        content = resp.choices[0].message.content if resp.choices else None
        print(f"[OK] stage 1 in {elapsed_ms}ms")
        print(f"     content: {content!r}")
        print(f"     usage: total={getattr(usage, 'total_tokens', 0)} prompt={getattr(usage, 'prompt_tokens', 0)} completion={getattr(usage, 'completion_tokens', 0)}")
        stage1 = {
            "ok": True,
            "elapsed_ms": elapsed_ms,
            "content": content,
            "usage": {
                "total_tokens": getattr(usage, "total_tokens", 0),
                "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                "completion_tokens": getattr(usage, "completion_tokens", 0),
            },
        }
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        msg = str(e)
        is_quota = "1113" in msg or "429" in msg
        print(f"[FAIL] stage 1 after {elapsed_ms}ms: {type(e).__name__}: {msg[:300]}")
        if is_quota:
            print("     → 仍然 quota_exhausted,充值未生效或已用完")
        stage1 = {
            "ok": False,
            "elapsed_ms": elapsed_ms,
            "error_type": type(e).__name__,
            "error": msg[:500],
            "is_quota_exhausted": is_quota,
        }

    # Stage 2: small structured completion (10 tokens, JSON-ish)
    print("\n[stage 2] Small structured prompt (max_tokens=20)...")
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=settings.ZHIPU_MODEL or "glm-4.7",
            messages=[
                {"role": "user", "content": '返回一个 JSON: {"ok": true, "value": 42},只返回这个 JSON 不要其他文字。'},
            ],
            max_tokens=20,
            timeout=15,
        )
        elapsed_ms = int((time.time() - t0) * 1000)
        content = resp.choices[0].message.content if resp.choices else None
        usage = getattr(resp, "usage", None)
        print(f"[OK] stage 2 in {elapsed_ms}ms")
        print(f"     content: {content!r}")
        print(f"     usage: total={getattr(usage, 'total_tokens', 0)}")
        stage2 = {
            "ok": True,
            "elapsed_ms": elapsed_ms,
            "content": content,
            "usage_total_tokens": getattr(usage, "total_tokens", 0),
        }
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        msg = str(e)
        print(f"[FAIL] stage 2 after {elapsed_ms}ms: {type(e).__name__}: {msg[:300]}")
        stage2 = {
            "ok": False,
            "elapsed_ms": elapsed_ms,
            "error_type": type(e).__name__,
            "error": msg[:500],
        }

    overall_ok = stage1.get("ok") and stage2.get("ok")
    artifact = {
        "ok": overall_ok,
        "timestamp": date_str,
        "model": settings.ZHIPU_MODEL,
        "base_url": settings.ZHIPU_BASE_URL or "(default)",
        "key_prefix": settings.ZHIPU_API_KEY[:8] + "...",
        "stage1_ping": stage1,
        "stage2_structured": stage2,
        "conclusion": (
            "GLM API reachable + quota available — P0-1 unblocked"
            if overall_ok else
            "GLM still blocked — see error details"
        ),
    }
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2))
    print(f"\n[spike] artifact → {output_path}")
    print(f"[spike] conclusion: {artifact['conclusion']}")
    return 0 if overall_ok else 3


if __name__ == "__main__":
    sys.exit(main())
