"""ZhipuAI (GLM) client for serenity research.

Thin wrapper over zhipuai SDK. Loads prompt + schema from prompts.py,
calls chat.completions with web_search + submit_research tools,
extracts structured result.

Q5: GLM-5.2 default (per .env ZHIPU_MODEL). Phase 1 fallback glm-4.7
when GLM-5.2 quota exhausted / not yet opened.
"""
from __future__ import annotations

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
    """LLM client for serenity research workflow."""

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
        max_tokens: int | None = None,
        max_searches: int | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Call GLM with web_search + submit_research tools.

        Returns parsed structured research result (JSON from tool_call).

        Raises ZhipuClientError on:
        - API failure (auth / quota / timeout / network)
        - LLM did not call submit_research tool
        - Invalid JSON in tool_call arguments
        """
        cfg = SERENITY_RUN_CONFIG
        max_tokens = max_tokens or cfg["max_tokens"]
        max_searches = max_searches or cfg["max_searches"]
        timeout = timeout or cfg["timeout_seconds"]

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": build_system_prompt(max_searches)},
                    {"role": "user", "content": user_context},
                ],
                tools=[
                    {
                        "type": "web_search",
                        "web_search": {
                            "enable": True,
                            "search_result": False,
                        },
                    },
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
        search_count = self._count_web_search_calls(response)
        result["_usage"] = {
            "token_input": getattr(usage, "prompt_tokens", 0) if usage else 0,
            "token_output": getattr(usage, "completion_tokens", 0) if usage else 0,
            "search_count": search_count,
            "model": self._model,
        }
        return result

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

    @staticmethod
    def _count_web_search_calls(response: Any) -> int:
        """Count how many web_search tool calls LLM issued."""
        count = 0
        try:
            for choice in getattr(response, "choices", None) or []:
                msg = choice.message
                for tc in getattr(msg, "tool_calls", None) or []:
                    fn = getattr(tc, "function", None)
                    if fn and fn.name == "web_search":
                        count += 1
        except Exception:
            pass
        return count


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
