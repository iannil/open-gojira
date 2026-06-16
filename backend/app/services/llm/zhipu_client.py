"""ZhipuAI (GLM) client for serenity research.

Path B (2026-06-16): chat-embedded `tools=[{type: "web_search"}]` doesn't
expose structured search results — GLM-5.1 silently skipped search and
hallucinated evidence URLs (curl-confirmed fake). New flow:

  1. search_collector_service.generate_queries() + collect_results() — uses
     standalone `client.web_search.web_search()` API to gather real URLs
  2. THIS client.run_serenity_research() — receives search_results as
     constrained context, LLM must cite URLs from this set only

The chat.completions call no longer includes web_search in tools. LLM only
has submit_research function. Prompt enforces "evidence.source_url must be
from the provided search_results list".
"""
from __future__ import annotations

import json
import logging
from typing import Any

from zhipuai import ZhipuAI

from app.core.research_config import SERENITY_RUN_CONFIG
from app.services.llm.prompts import (
    SERENITY_RESEARCH_JSON_SCHEMA,
    build_system_prompt,
)

logger = logging.getLogger(__name__)


class ZhipuClientError(Exception):
    """Raised when ZhipuAI call fails or returns malformed output."""


class ZhipuClient:
    """LLM client for serenity research workflow (Path B two-step)."""

    def __init__(
        self,
        api_key: str,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        if not api_key:
            raise ZhipuClientError("ZHIPU_API_KEY is required")
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = ZhipuAI(**kwargs)
        self._model = model or SERENITY_RUN_CONFIG["default_model"]

    def run_serenity_research(
        self,
        user_context: str,
        search_results: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Call GLM with constrained search_results context + submit_research.

        Path B step 2: LLM receives pre-collected search results as JSON in
        user message. LLM must cite URLs from this set in evidence rows.

        Args:
            user_context: original serenity user prompt (theme + Lixinger
                candidates hint).
            search_results: list of collected search result dicts with at
                least {search_query, url, title, snippet, media,
                published_at}. Empty list = degraded mode (LLM may
                hallucinate URLs, caller should warn).
            max_tokens: override SERENITY_RUN_CONFIG default.
            timeout: override SERENITY_RUN_CONFIG default.

        Returns:
            Parsed structured research result (JSON from submit_research
            tool_call), with `_usage` dict containing tokens + result count.

        Raises:
            ZhipuClientError on API failure, missing submit_research call,
            or invalid JSON in tool_call arguments.
        """
        cfg = SERENITY_RUN_CONFIG
        max_tokens = max_tokens or cfg["max_tokens"]
        timeout = timeout or cfg["timeout_seconds"]

        enriched_prompt = self._build_synthesis_prompt(
            user_context, search_results or []
        )

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": build_system_prompt(
                            cfg["max_search_queries"]
                        ),
                    },
                    {"role": "user", "content": enriched_prompt},
                ],
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "submit_research",
                            "description": "提交 serenity 研究结果 (必须调用,且只调用一次)",
                            "parameters": SERENITY_RESEARCH_JSON_SCHEMA,
                        },
                    },
                ],
                tool_choice="auto",
                max_tokens=max_tokens,
                temperature=cfg["temperature"],
                timeout=timeout,
            )
        except Exception as exc:
            raise ZhipuClientError(f"GLM API call failed: {exc}") from exc

        result = self._extract_submit_research(response)
        usage = getattr(response, "usage", None)
        result["_usage"] = {
            "token_input": getattr(usage, "prompt_tokens", 0) if usage else 0,
            "token_output": getattr(usage, "completion_tokens", 0) if usage else 0,
            "search_count": len(search_results or []),
            "model": self._model,
        }
        return result

    @staticmethod
    def _build_synthesis_prompt(
        user_context: str, search_results: list[dict[str, Any]]
    ) -> str:
        """Merge original user_context with collected search_results JSON.

        LLM is instructed that evidence.source_url must come from the
        search_results list. No fabrication allowed.
        """
        if not search_results:
            return (
                user_context
                + "\n\n⚠️ 警告: 没有可用的 web_search 结果。evidence 可能无法"
                "提供真实 URL,请在 evidence 中如实标注 grade=lead 或省略 source_url。"
            )

        # Compress each result to essential fields to keep prompt size sane
        compact = [
            {
                "query": r.get("search_query", ""),
                "url": r.get("url", ""),
                "title": (r.get("title") or "")[:120],
                "snippet": (r.get("snippet") or "")[:300],
                "media": r.get("media") or "",
                "published_at": str(r.get("published_at") or ""),
            }
            for r in search_results
            if r.get("url")
        ]
        return (
            user_context
            + "\n\n# web_search 真实结果 (Path B 约束)\n\n"
            + "以下是通过 zhipu web_search API 真实返回的搜索结果。"
            + "你的 evidence 数组里,每条 source_url **必须从下方 urls 中选择**,"
            + "不允许编造。如果某条证据找不到匹配 URL,降级为 grade=lead 并标注。\n\n"
            + f"```json\n{json.dumps(compact, ensure_ascii=False, indent=2)}\n```"
        )

    @staticmethod
    def _extract_submit_research(response: Any) -> dict[str, Any]:
        """Pull submit_research tool_call arguments from response."""
        choices = getattr(response, "choices", None) or []
        if not choices:
            raise ZhipuClientError("LLM returned empty choices")
        msg = choices[0].message
        tool_calls = getattr(msg, "tool_calls", None) or []
        for tc in tool_calls:
            fn = getattr(tc, "function", None)
            if not fn or fn.name != "submit_research":
                continue
            import json

            try:
                return json.loads(fn.arguments)
            except json.JSONDecodeError as exc:
                raise ZhipuClientError(
                    f"submit_research arguments invalid JSON: {exc}"
                ) from exc
        content = getattr(msg, "content", None) or ""
        raise ZhipuClientError(
            f"LLM did not call submit_research tool. content head: {content[:500]}"
        )


# ── Factory ─────────────────────────────────────────────────────────────
_client_singleton: ZhipuClient | None = None


def get_zhipu_client() -> ZhipuClient:
    """Return shared ZhipuClient (lazy-init from settings)."""
    global _client_singleton
    if _client_singleton is None:
        from app.config import settings

        if not settings.ZHIPU_API_KEY:
            raise ZhipuClientError(
                "ZHIPU_API_KEY is not set in .env. Get one at "
                "https://open.bigmodel.cn/usercenter/apikeys"
            )
        _client_singleton = ZhipuClient(
            api_key=settings.ZHIPU_API_KEY,
            model=settings.ZHIPU_MODEL or None,
            base_url=settings.ZHIPU_BASE_URL or None,
        )
    return _client_singleton


def reset_zhipu_client() -> None:
    """Test hook: reset singleton between tests."""
    global _client_singleton
    _client_singleton = None
