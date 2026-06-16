"""Search collector service — Path B step 1 of serenity research.

Generates search queries (LLM-driven, A+C hybrid) and collects real results
from zhipu's standalone web_search API (`client.web_search.web_search()`).

Why this exists (2026-06-16):
  GLM-5.1's chat-embedded `tools=[{type: "web_search"}]` doesn't expose
  structured search results — only implicit references in reasoning_content.
  In serenity runs, LLM skipped web_search entirely and hallucinated 29
  evidence URLs (curl-confirmed fake: cninfo returned size 0, pbc.gov.cn
  returned 404). serenity spec requires ≥25 real sources via web_search.

  Path B: collect real URLs first via standalone API, then pass to LLM as
  constrained context. LLM can only cite URLs from this set.

Public API:
  generate_queries(theme, candidates, *, max_queries=30) -> list[str]
  collect_results(queries, *, count_per_query=5, max_workers=4) -> list[CollectedResult]
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.core.research_config import SERENITY_RUN_CONFIG
from app.models.research_search_result import ResearchSearchResult

logger = logging.getLogger(__name__)


# Default search engine — search_std is the basic tier; search_pro adds
# deeper indexing. Std is sufficient for serenity's financial-filing needs
# and roughly half the cost.
DEFAULT_SEARCH_ENGINE = "search_std"


class CollectedResult(BaseModel):
    """One search result row, ready for DB persistence."""

    search_query: str
    position: int
    title: str | None = None
    url: str
    snippet: str | None = None
    media: str | None = None
    published_at: date | None = None
    refer: str | None = None


# ── Query generation (A+C hybrid) ────────────────────────────────────────

QUERY_GEN_SYSTEM_PROMPT = """你是 Gojira 投资研究助手的 query 生成器。

任务: 为「供应链卡点猎手」研究工作流生成 30 个高质量的中文搜索查询。

混合策略:
- 公司驱动 (C): 对每个候选公司,生成 2 个查询 — (1) 公司最新季报/年报核心业务 (2) 公司在产业链中的地位/竞争力
- 主题驱动 (A): 剩余查询覆盖 (1) 行业政策与监管动态 (2) 产业链稀缺层与替代风险 (3) 行业龙头最新动态 (4) 关键技术/工艺进展 (5) 海外对标与竞争格局

输出格式: 严格的 JSON 数组,每条是一个 query 字符串。不要其他文字。
示例输出: ["紫光国微 002049 2024 三季报 金融IC卡芯片业务", "紫光国微 数字人民币硬钱包芯片 市占率", ...]
"""


def generate_queries(
    theme: str,
    candidates: list[dict[str, Any]],
    *,
    max_queries: int = 30,
    zhipu_client: Any | None = None,
) -> list[str]:
    """Generate up to `max_queries` search queries for serenity research.

    A+C hybrid: company-driven (2 per candidate) + theme-driven (remainder).

    Args:
        theme: research theme name (e.g. "银行")
        candidates: list of {"code", "name", "industry"} dicts from Lixinger
        max_queries: hard cap, default 30 (matches SERENITY_RUN_CONFIG)
        zhipu_client: optional injected client (for testing)

    Returns:
        list of query strings, deduplicated, length ≤ max_queries.
    """
    if not theme:
        return []

    client = zhipu_client or _get_zhipu_client()
    if client is None:
        logger.warning("ZhipuAI not configured — returning empty query list")
        return []

    # Build user prompt with candidate list (top 10 to keep prompt tight)
    top_candidates = candidates[:10]
    candidate_lines = [
        f"- {c.get('name', '?')} ({c.get('code', '?')}) — {c.get('industry', '?')}"
        for c in top_candidates
    ]
    user_prompt = (
        f"主题: {theme}\n"
        f"候选公司 (前 {len(top_candidates)} 家,Lixinger 行业成分股):\n"
        + "\n".join(candidate_lines)
        + f"\n\n请生成 {max_queries} 个搜索查询 (JSON 数组格式)。"
    )

    try:
        response = client.chat.completions.create(
            model=settings.ZHIPU_MODEL or SERENITY_RUN_CONFIG["default_model"],
            messages=[
                {"role": "system", "content": QUERY_GEN_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=SERENITY_RUN_CONFIG.get("max_query_generation_tokens", 800),
            temperature=0.4,  # slight creativity for diverse queries
            timeout=60,
        )
    except Exception as exc:
        logger.warning("Query generation LLM call failed: %s", exc)
        return _fallback_queries(theme, top_candidates, max_queries)

    raw_content = ""
    try:
        msg = response.choices[0].message
        raw_content = msg.content or ""
        # Reasoning model (glm-5.x) may put output in reasoning_content
        # when content is empty. Mine reasoning_content for JSON array.
        if not raw_content:
            reasoning = getattr(msg, "reasoning_content", None) or ""
            if reasoning:
                # Find last [ ... ] block in reasoning
                start = reasoning.rfind("[")
                end = reasoning.rfind("]")
                if 0 <= start < end:
                    raw_content = reasoning[start:end + 1]
    except Exception as exc:
        logger.warning("Failed to read query-gen response: %s", exc)
        return _fallback_queries(theme, top_candidates, max_queries)

    queries = _parse_json_array(raw_content)
    if not queries:
        logger.warning(
            "Query-gen returned unparseable content (len=%d), using fallback",
            len(raw_content),
        )
        return _fallback_queries(theme, top_candidates, max_queries)

    # Dedup + cap
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        q_stripped = q.strip()
        if q_stripped and q_stripped not in seen:
            seen.add(q_stripped)
            unique.append(q_stripped)
        if len(unique) >= max_queries:
            break

    logger.info(
        "Generated %d unique queries for theme=%r (candidates=%d)",
        len(unique), theme, len(top_candidates),
    )
    return unique


def _fallback_queries(
    theme: str, candidates: list[dict[str, Any]], max_queries: int
) -> list[str]:
    """Rule-based fallback when LLM query-gen fails.

    Generates 2 per candidate + a few theme-level templates.
    """
    queries: list[str] = []
    for c in candidates[: max_queries // 2]:
        name = c.get("name", "")
        code = c.get("code", "")
        if name and code:
            queries.append(f"{name} {code} 最新财报 业务进展")
            queries.append(f"{name} {code} 产业链 行业地位")
    # Theme-level templates
    queries.extend([
        f"{theme} 行业最新政策 监管动态",
        f"{theme} 产业链 稀缺层 龙头公司",
        f"{theme} 行业风险 替代品 技术变更",
        f"{theme} 海外对标 国际竞争格局",
        f"{theme} 行业景气度 2025 2026",
    ])
    return queries[:max_queries]


def _parse_json_array(content: str) -> list[str]:
    """Parse LLM output as JSON array of strings, tolerant of code fences."""
    s = content.strip()
    # Strip markdown code fences if present
    if s.startswith("```"):
        first_newline = s.find("\n")
        if first_newline > 0:
            s = s[first_newline + 1:]
        if s.endswith("```"):
            s = s[:-3].rstrip()
    try:
        parsed = json.loads(s)
        if isinstance(parsed, list):
            return [str(item) for item in parsed if isinstance(item, (str, int))]
    except json.JSONDecodeError:
        pass
    # Last-ditch: extract bracketed content
    if "[" in s and "]" in s:
        start = s.find("[")
        end = s.rfind("]") + 1
        try:
            parsed = json.loads(s[start:end])
            if isinstance(parsed, list):
                return [str(item) for item in parsed if isinstance(item, (str, int))]
        except json.JSONDecodeError:
            pass
    return []


# ── Search collection (parallel) ──────────────────────────────────────────


def collect_results(
    queries: list[str],
    *,
    count_per_query: int = 5,
    max_workers: int = 4,
    timeout_per_query: int = 30,
    zhipu_client: Any | None = None,
) -> list[CollectedResult]:
    """Run web_search.web_search() for each query in parallel.

    Args:
        queries: list of search query strings
        count_per_query: max results per query (GLM-side cap also applies)
        max_workers: parallel worker count
        timeout_per_query: per-call timeout seconds
        zhipu_client: optional injected client (for testing)

    Returns:
        list of CollectedResult, deduplicated by URL within query,
        position-ordered per query. Failures logged and skipped.
    """
    if not queries:
        return []

    client = zhipu_client or _get_zhipu_client()
    if client is None:
        logger.warning("ZhipuAI not configured — returning empty results")
        return []

    results: list[CollectedResult] = []
    failed_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_query = {
            executor.submit(
                _search_one,
                client, q, count_per_query, timeout_per_query,
            ): q
            for q in queries
        }
        for future in as_completed(future_to_query):
            q = future_to_query[future]
            try:
                rows = future.result()
                results.extend(rows)
            except Exception as exc:
                failed_count += 1
                logger.warning("Search failed for query=%r: %s", q, exc)

    logger.info(
        "Collected %d results from %d queries (%d failed)",
        len(results), len(queries), failed_count,
    )
    return results


def _search_one(
    client: Any,
    query: str,
    count: int,
    timeout: int,
) -> list[CollectedResult]:
    """Execute one web_search API call, return parsed CollectedResults."""
    resp = client.web_search.web_search(
        search_query=query,
        search_engine=DEFAULT_SEARCH_ENGINE,
        count=count,
        content_size="high",
        timeout=timeout,
    )
    raw_results = getattr(resp, "search_result", None) or []
    out: list[CollectedResult] = []
    seen_urls: set[str] = set()
    position = 0
    for r in raw_results:
        url = (getattr(r, "link", None) or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        published = getattr(r, "publish_date", None)
        published_date: date | None = None
        if isinstance(published, str) and published:
            try:
                published_date = date.fromisoformat(published[:10])
            except ValueError:
                published_date = None
        out.append(CollectedResult(
            search_query=query,
            position=position,
            title=getattr(r, "title", None),
            url=url,
            snippet=getattr(r, "content", None),
            media=getattr(r, "media", None),
            published_at=published_date,
            refer=getattr(r, "refer", None),
        ))
        position += 1
    return out


# ── Persistence ───────────────────────────────────────────────────────────


def persist_search_results(
    db: Session, run_id: int, results: list[CollectedResult]
) -> int:
    """Persist collected results to research_search_results table.

    Deduplicates by URL across the whole run (not just per query).

    Returns: number of rows actually inserted.
    """
    if not results:
        return 0

    seen_urls: set[str] = set()
    inserted = 0
    for r in results:
        if r.url in seen_urls:
            continue
        seen_urls.add(r.url)
        db.add(ResearchSearchResult(
            research_run_id=run_id,
            search_query=r.search_query,
            position=r.position,
            title=r.title,
            url=r.url,
            snippet=r.snippet,
            media=r.media,
            published_at=r.published_at,
            refer=r.refer,
        ))
        inserted += 1

    db.flush()
    return inserted


# ── Client factory ────────────────────────────────────────────────────────


def _get_zhipu_client() -> Any | None:
    """Lazy-init shared ZhipuAI client. Returns None if not configured."""
    if not settings.ZHIPU_API_KEY:
        return None
    from app.services.llm.zhipu_client import get_zhipu_client
    return get_zhipu_client()._client  # underlying ZhipuAI SDK instance
