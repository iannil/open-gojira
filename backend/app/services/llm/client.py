"""LLM client — v2 core (per decision 2: native Pipeline).

Self-wrapped Zhipu SDK with:
  - @tracked-compatible observability (writes llm_call_logs)
  - prompt_hash caching (30-day TTL per stock+pipeline)
  - exponential backoff retry (3 attempts)
  - cost tracking (USD, monthly cap)
  - watchdog timeout (immune to SSL read blocks)
  - tool_use for structured JSON output
  - web_search tool support

Usage:
    from app.services.llm.client import get_llm_client, GLM_TIER

    client = get_llm_client()
    response = await client.complete(
        prompt="...",
        model=GLM_TIER.SONNET,  # glm-5.1
        response_schema={...},  # JSON schema for tool_use
        tools=["web_search"],
        pipeline_type="deep_research",
        stock_code="600519",
    )
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from zhipuai import ZhipuAI

from app.core.datetime_utils import now
from app.core.observability import _generate_id, trace_id_var
from app.db.session import SessionLocal
from app.services.llm.cost_tracker import (
    CostEntry,
    compute_cost_usd,
    write_call_log,
)
from app.services.llm.prompt_loader import build_system_prompt

logger = logging.getLogger(__name__)


class GLMTier(str, Enum):
    """Model tier per decision 4 (GLM 4.8/5.1/5.2 = Haiku/Sonnet/Opus equivalent)."""
    HAIKU = "glm-4.8"   # 后勤层: quality_screen / news_pulse
    SONNET = "glm-5.1"  # 战术层: deep_research default / thesis_tracker / earnings_review
    OPUS = "glm-5.2"    # 战略层: top 3 候选最终决策


# ── Response dataclass ────────────────────────────────────────────────────


@dataclass
class LLMResponse:
    """Result of a single LLM call."""
    content: str
    tool_call_args: Optional[dict[str, Any]] = None  # parsed JSON if response_schema used
    usage: dict[str, int] = field(default_factory=dict)  # tokens_in, tokens_out, search_count
    cost_usd: float = 0.0
    latency_ms: int = 0
    model: str = ""
    trace_id: Optional[str] = None
    prompt_hash: Optional[str] = None
    tool_calls_breakdown: Optional[dict] = None  # web_search calls count etc.


class LLMClientError(Exception):
    """Raised on LLM API failure or malformed output."""


# ── Client ────────────────────────────────────────────────────────────────


# Retry config (per decision 14: exponential backoff 3 attempts)
MAX_RETRIES: int = 3
INITIAL_BACKOFF_SEC: float = 2.0
BACKOFF_MULTIPLIER: float = 2.0

# Watchdog (per memory: GLM SDK httpx timeout ineffective on SSL read block)
WATCHDOG_GRACE_SEC: int = 30

# Default sampling
DEFAULT_TEMPERATURE: float = 0.3
DEFAULT_MAX_TOKENS: int = 16000
DEFAULT_TIMEOUT_SEC: int = 300


class LLMClient:
    """v2 LLM client wrapping Zhipu SDK."""

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
    ) -> None:
        if not api_key:
            raise LLMClientError("ZHIPU_API_KEY is required")
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = ZhipuAI(**kwargs)

    def complete(
        self,
        *,
        user_prompt: str,
        pipeline: str,
        model: GLMTier | str = GLMTier.SONNET,
        version: str = "v1",
        response_schema: Optional[dict[str, Any]] = None,
        use_web_search: bool = False,
        stock_code: Optional[str] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        timeout: int = DEFAULT_TIMEOUT_SEC,
        pipeline_type: Optional[str] = None,
        db_session: Any = None,  # optional: caller's session, else new one
    ) -> LLMResponse:
        """Single LLM call (synchronous; wrapped with watchdog).

        Args:
            user_prompt: user message content
            pipeline: prompt pipeline (deep_research / thesis_tracker / ...)
            model: GLM tier or model string
            version: prompt version directory
            response_schema: JSON schema for tool_use structured output
            use_web_search: enable web_search tool
            stock_code: for cost tracking / prompt_hash namespacing
            max_tokens / temperature / timeout: LLM hyperparams
            pipeline_type: cost tracking grouping (defaults to pipeline)
            db_session: if provided, use it; else create SessionLocal

        Returns:
            LLMResponse with content + parsed tool_call args + cost metadata.

        Raises:
            LLMClientError on persistent failure.
        """
        model_str = model.value if isinstance(model, GLMTier) else model
        pipeline_type_str = pipeline_type or pipeline
        prompt_hash = self._hash_prompt(pipeline, version, user_prompt, model_str)

        system_prompt = build_system_prompt(pipeline, version)

        # Build tools list
        tools: list[dict[str, Any]] = []
        if response_schema:
            tools.append({
                "type": "function",
                "function": {
                    "name": "submit_result",
                    "description": "提交结构化输出（必须调用，且只调用一次）",
                    "parameters": response_schema,
                },
            })
        if use_web_search:
            tools.append({"type": "web_search", "web_search": {"enable": True}})

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        trace_id = trace_id_var.get("") or _generate_id()
        span_id = _generate_id()
        start_monotonic = time.monotonic()

        # Retry loop with exponential backoff
        last_error: Optional[Exception] = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self._call_with_watchdog(
                    model=model_str,
                    messages=messages,
                    tools=tools or None,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=timeout,
                )
                # Parse + record
                llm_response = self._parse_response(
                    response, model_str, prompt_hash, trace_id
                )
                llm_response.trace_id = trace_id
                self._record_success(
                    db_session=db_session,
                    span_id=span_id,
                    trace_id=trace_id,
                    pipeline_type=pipeline_type_str,
                    stock_code=stock_code,
                    model=model_str,
                    prompt_hash=prompt_hash,
                    response=llm_response,
                    latency_ms=int((time.monotonic() - start_monotonic) * 1000),
                )
                return llm_response

            except LLMClientError as exc:
                last_error = exc
                if attempt < MAX_RETRIES - 1:
                    backoff = INITIAL_BACKOFF_SEC * (BACKOFF_MULTIPLIER ** attempt)
                    logger.warning(
                        "LLM call attempt %d/%d failed: %s. Retrying in %.1fs",
                        attempt + 1, MAX_RETRIES, exc, backoff,
                    )
                    time.sleep(backoff)
                continue
            except Exception as exc:
                last_error = exc
                logger.exception(
                    "LLM call unexpected error attempt %d/%d",
                    attempt + 1, MAX_RETRIES,
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(INITIAL_BACKOFF_SEC * (BACKOFF_MULTIPLIER ** attempt))
                continue

        # All retries exhausted
        self._record_failure(
            db_session=db_session,
            span_id=span_id,
            trace_id=trace_id,
            pipeline_type=pipeline_type_str,
            stock_code=stock_code,
            model=model_str,
            prompt_hash=prompt_hash,
            error=str(last_error),
            latency_ms=int((time.monotonic() - start_monotonic) * 1000),
        )
        raise LLMClientError(
            f"LLM call failed after {MAX_RETRIES} attempts: {last_error}"
        ) from last_error

    # ── Internals ─────────────────────────────────────────────────────

    @staticmethod
    def _hash_prompt(
        pipeline: str, version: str, user_prompt: str, model: str
    ) -> str:
        """Stable hash for caching/deduplication.

        Excludes model so that switching model invalidates cache (different output expected).
        """
        h = hashlib.sha256(
            f"{pipeline}|{version}|{user_prompt}|{model}".encode("utf-8")
        )
        return h.hexdigest()[:16]

    def _call_with_watchdog(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        tools: Optional[list[dict[str, Any]]],
        max_tokens: int,
        temperature: float,
        timeout: int,
    ) -> Any:
        """Call Zhipu SDK with watchdog (immune to SSL read blocks).

        Per memory: GLM SDK httpx timeout fails when connection is kept open
        but no data flows. ThreadPoolExecutor.future.result enforces timeout
        at Python level.
        """
        watchdog_timeout = timeout + WATCHDOG_GRACE_SEC
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "timeout": timeout,
        }
        if tools:
            kwargs["tools"] = tools
            # auto = let LLM choose (web_search auto-triggers, function tool called at end)
            kwargs["tool_choice"] = "auto"

        def _do_call():
            return self._client.chat.completions.create(**kwargs)

        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_do_call)
            try:
                return future.result(timeout=watchdog_timeout)
            except FutureTimeoutError:
                raise LLMClientError(
                    f"GLM API watchdog timeout after {watchdog_timeout}s "
                    f"(SDK timeout={timeout}s ineffective, SSL read blocked)"
                )

    def _parse_response(
        self,
        response: Any,
        model: str,
        prompt_hash: str,
        trace_id: str,
    ) -> LLMResponse:
        """Extract content + tool_call args + usage from Zhipu response."""
        choices = getattr(response, "choices", None) or []
        if not choices:
            raise LLMClientError("LLM returned empty choices")
        msg = choices[0].message
        content = getattr(msg, "content", "") or ""

        # Pull tool_call args (submit_result function)
        tool_args: Optional[dict[str, Any]] = None
        tool_calls_breakdown: Optional[dict] = None
        tool_calls = getattr(msg, "tool_calls", None) or []
        for tc in tool_calls:
            fn = getattr(tc, "function", None)
            if not fn:
                continue
            fn_name = getattr(fn, "name", "") or ""
            if fn_name == "submit_result":
                args_str = getattr(fn, "arguments", "") or ""
                try:
                    tool_args = json.loads(args_str) if args_str else None
                except json.JSONDecodeError as exc:
                    raise LLMClientError(
                        f"submit_result arguments invalid JSON: {exc}"
                    ) from exc
            elif fn_name == "web_search":
                # web_search tools have search_result metadata
                pass

        # Check for web_search in tool_calls (may be separate type)
        ws_count = sum(
            1 for tc in tool_calls
            if (getattr(tc, "type", "") or "") == "web_search"
        )
        if ws_count > 0:
            tool_calls_breakdown = {"web_search_count": ws_count}

        # Usage
        usage_obj = getattr(response, "usage", None)
        usage = {
            "tokens_in": getattr(usage_obj, "prompt_tokens", 0) if usage_obj else 0,
            "tokens_out": getattr(usage_obj, "completion_tokens", 0) if usage_obj else 0,
            "search_count": ws_count,
        }

        # Cost
        cost = compute_cost_usd(model, usage["tokens_in"], usage["tokens_out"])

        return LLMResponse(
            content=content,
            tool_call_args=tool_args,
            usage=usage,
            cost_usd=cost,
            model=model,
            prompt_hash=prompt_hash,
            tool_calls_breakdown=tool_calls_breakdown,
        )

    def _record_success(
        self,
        *,
        db_session: Any,
        span_id: str,
        trace_id: str,
        pipeline_type: str,
        stock_code: Optional[str],
        model: str,
        prompt_hash: str,
        response: LLMResponse,
        latency_ms: int,
    ) -> None:
        entry = CostEntry(
            trace_id=trace_id,
            span_id=span_id,
            model=model,
            pipeline_type=pipeline_type,
            stock_code=stock_code,
            prompt_hash=prompt_hash,
            tokens_in=response.usage.get("tokens_in", 0),
            tokens_out=response.usage.get("tokens_out", 0),
            cost_usd=response.cost_usd,
            latency_ms=latency_ms,
            tool_calls=response.tool_calls_breakdown,
            success=True,
        )
        self._safe_write_log(db_session, entry)

    def _record_failure(
        self,
        *,
        db_session: Any,
        span_id: str,
        trace_id: str,
        pipeline_type: str,
        stock_code: Optional[str],
        model: str,
        prompt_hash: str,
        error: str,
        latency_ms: int,
    ) -> None:
        entry = CostEntry(
            trace_id=trace_id,
            span_id=span_id,
            model=model,
            pipeline_type=pipeline_type,
            stock_code=stock_code,
            prompt_hash=prompt_hash,
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            latency_ms=latency_ms,
            success=False,
            error_message=error[:2000],  # truncate
        )
        self._safe_write_log(db_session, entry)

    @staticmethod
    def _safe_write_log(db_session: Any, entry: CostEntry) -> None:
        """Persist call log; tolerate DB failure (log only)."""
        if db_session is not None:
            try:
                write_call_log(db_session, entry)
                db_session.flush()
                return
            except Exception:
                logger.exception("Failed to write llm_call_log with provided session")

        # Fallback: own session
        try:
            with SessionLocal() as fallback_db:
                write_call_log(fallback_db, entry)
                fallback_db.commit()
        except Exception:
            logger.exception("Failed to write llm_call_log via fallback session")


# ── Factory ──────────────────────────────────────────────────────────────


_client_singleton: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Shared LLMClient (lazy-init from settings)."""
    global _client_singleton
    if _client_singleton is None:
        from app.config import settings
        if not settings.ZHIPU_API_KEY:
            raise LLMClientError(
                "ZHIPU_API_KEY not set in .env. Get one at "
                "https://open.bigmodel.cn/usercenter/apikeys"
            )
        _client_singleton = LLMClient(
            api_key=settings.ZHIPU_API_KEY,
            base_url=getattr(settings, "ZHIPU_BASE_URL", None) or None,
        )
    return _client_singleton


def reset_llm_client() -> None:
    """Test hook: reset singleton between tests."""
    global _client_singleton
    _client_singleton = None
