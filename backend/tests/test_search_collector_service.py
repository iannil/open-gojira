"""Tests for search_collector_service (Path B 2026-06-16).

Covers:
- generate_queries: LLM-driven (mocked) + fallback path
- collect_results: parallel calls + dedup + failure isolation
- persist_search_results: URL dedup across run
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models.research_search_result import ResearchSearchResult
from app.services.search_collector_service import (
    CollectedResult,
    _fallback_queries,
    _parse_json_array,
    _search_one,
    collect_results,
    generate_queries,
    persist_search_results,
)


# ── Test doubles ─────────────────────────────────────────────────────────


def _make_search_resp_item(
    title: str = "T",
    link: str = "https://example.com",
    content: str = "snippet",
    media: str = "media",
    publish_date: str = "2025-01-01",
    refer: str = "[ref_1]",
):
    return SimpleNamespace(
        title=title,
        link=link,
        content=content,
        media=media,
        publish_date=publish_date,
        refer=refer,
    )


def _make_search_response(items: list) -> SimpleNamespace:
    return SimpleNamespace(
        search_result=items,
        search_intent=SimpleNamespace(
            query="q", intent="SEARCH", keywords="kw",
        ),
    )


class _FakeChatCompletions:
    """Fake of client.chat.completions for query generation tests."""

    def __init__(self, content: str):
        self._content = content

    def create(self, **kwargs):
        msg = SimpleNamespace(content=self._content)
        choice = SimpleNamespace(message=msg)
        return SimpleNamespace(choices=[choice])


class _FakeWebSearch:
    """Fake of client.web_search for collect_results tests."""

    def __init__(self, results_by_query: dict[str, list]):
        self._results = results_by_query
        self.calls: list[str] = []

    def web_search(self, *, search_query, **kwargs):
        self.calls.append(search_query)
        return _make_search_response(self._results.get(search_query, []))


class _FakeClient:
    def __init__(self, chat_content: str = "", web_results: dict | None = None):
        self.chat = SimpleNamespace(completions=_FakeChatCompletions(chat_content))
        self.web_search = _FakeWebSearch(web_results or {})


# ── generate_queries ─────────────────────────────────────────────────────


def test_generate_queries_parses_llm_json_array():
    client = _FakeClient(chat_content='["query A", "query B", "query C"]')
    queries = generate_queries("银行", [], zhipu_client=client)
    assert queries == ["query A", "query B", "query C"]


def test_generate_queries_strips_markdown_fences():
    client = _FakeClient(chat_content='```json\n["a", "b"]\n```')
    queries = generate_queries("主题", [], zhipu_client=client)
    assert queries == ["a", "b"]


def test_generate_queries_dedups():
    client = _FakeClient(chat_content='["q1", "q1", "q2", "q2", "q3"]')
    queries = generate_queries("t", [], zhipu_client=client)
    assert queries == ["q1", "q2", "q3"]


def test_generate_queries_caps_at_max():
    many = [f"q{i}" for i in range(50)]
    client = _FakeClient(chat_content=str(many).replace("'", '"'))
    queries = generate_queries("t", [], max_queries=10, zhipu_client=client)
    assert len(queries) == 10


def test_generate_queries_fallback_on_unparseable_llm_output():
    """When LLM returns garbage, fallback queries are generated."""
    client = _FakeClient(chat_content="sorry I cannot help")
    candidates = [{"name": "紫光国微", "code": "002049", "industry": "半导体"}]
    queries = generate_queries("银行", candidates, zhipu_client=client)
    assert len(queries) > 0
    # Fallback should mention candidate name
    assert any("紫光国微" in q for q in queries)


def test_generate_queries_fallback_on_llm_exception():
    """When LLM call raises, fallback queries are generated."""

    class _BoomChat:
        def create(self, **kwargs):
            raise RuntimeError("network down")

    class _BoomClient:
        chat = SimpleNamespace(completions=_BoomChat())
        web_search = _FakeWebSearch({})

    candidates = [{"name": "X", "code": "001", "industry": "i"}]
    queries = generate_queries("t", candidates, zhipu_client=_BoomClient())
    assert len(queries) > 0


def test_generate_queries_empty_theme_returns_empty():
    client = _FakeClient(chat_content='["should not reach"]')
    assert generate_queries("", [], zhipu_client=client) == []


def test_fallback_queries_includes_theme_level_queries():
    candidates = [{"name": "C1", "code": "001", "industry": "i"}]
    queries = _fallback_queries("白酒", candidates, 20)
    assert any("白酒" in q for q in queries)
    assert any("C1" in q for q in queries)


def test_parse_json_array_handles_code_fences():
    assert _parse_json_array("```json\n[\"a\",\"b\"]\n```") == ["a", "b"]


def test_parse_json_array_handles_bare_array():
    assert _parse_json_array('["x", "y"]') == ["x", "y"]


def test_parse_json_array_returns_empty_on_garbage():
    assert _parse_json_array("not json at all") == []


# ── collect_results ──────────────────────────────────────────────────────


def test_collect_results_parallel_dedup_per_query():
    """Within a query, duplicate URLs are deduped; positions are 0-based."""
    web_results = {
        "q1": [
            _make_search_resp_item(link="https://a.com"),
            _make_search_resp_item(link="https://a.com"),  # dup
            _make_search_resp_item(link="https://b.com"),
        ],
        "q2": [
            _make_search_resp_item(link="https://c.com"),
        ],
    }
    client = _FakeClient(web_results=web_results)
    results = collect_results(["q1", "q2"], zhipu_client=client)
    assert len(results) == 3
    q1_results = [r for r in results if r.search_query == "q1"]
    assert {r.url for r in q1_results} == {"https://a.com", "https://b.com"}
    # Positions should be 0, 1 (not 0, 1, 2 with dup)
    positions = sorted(r.position for r in q1_results)
    assert positions == [0, 1]


def test_collect_results_skips_empty_urls():
    web_results = {
        "q1": [
            _make_search_resp_item(link=""),  # empty URL → skip
            _make_search_resp_item(link="https://real.com"),
        ],
    }
    client = _FakeClient(web_results=web_results)
    results = collect_results(["q1"], zhipu_client=client)
    assert len(results) == 1
    assert results[0].url == "https://real.com"


def test_collect_results_parses_published_at():
    web_results = {
        "q1": [_make_search_resp_item(publish_date="2025-03-15")],
    }
    client = _FakeClient(web_results=web_results)
    results = collect_results(["q1"], zhipu_client=client)
    assert results[0].published_at == date(2025, 3, 15)


def test_collect_results_handles_invalid_published_at():
    web_results = {
        "q1": [_make_search_resp_item(publish_date="not-a-date")],
    }
    client = _FakeClient(web_results=web_results)
    results = collect_results(["q1"], zhipu_client=client)
    assert results[0].published_at is None


def test_collect_results_isolates_query_failures():
    """One query's exception doesn't kill others."""

    class _PartialWebSearch:
        def __init__(self):
            self.calls = 0

        def web_search(self, *, search_query, **kwargs):
            self.calls += 1
            if search_query == "boom":
                raise RuntimeError("api timeout")
            return _make_search_response([
                _make_search_resp_item(link=f"https://{search_query}.com")
            ])

    class _PartialClient:
        web_search = None

        def __init__(self):
            self.web_search = _PartialWebSearch()

    client = _PartialClient()
    results = collect_results(["ok1", "boom", "ok2"], zhipu_client=client)
    assert len(results) == 2
    assert {r.url for r in results} == {"https://ok1.com", "https://ok2.com"}


def test_collect_results_empty_queries_returns_empty():
    client = _FakeClient(web_results={})
    assert collect_results([], zhipu_client=client) == []


def test_search_one_returns_empty_list_on_empty_results():
    client = _FakeClient(web_results={"q": []})
    rows = _search_one(client, "q", count=5, timeout=10)
    assert rows == []


# ── persist_search_results ───────────────────────────────────────────────


def test_persist_search_results_dedups_across_run(db_session):
    """Same URL from different queries is only stored once."""
    run_id = 999  # synthetic; FK may not exist but persist only flushes
    # Use a real ResearchRun via fixture-equivalent — but our db_session
    # uses in-memory SQLite. Insert a parent row.
    from app.models.research_run import ResearchRun
    from app.models.research_theme import ResearchTheme

    theme = ResearchTheme(name="t", market="A_SHARE", status="active")
    db_session.add(theme)
    db_session.flush()
    run = ResearchRun(
        research_theme_id=theme.id,
        status="completed",
        scope_market="A_SHARE",
        scope_time_window="3-12M",
        triggered_by="test",
        llm_provider="glm-5.1",
    )
    db_session.add(run)
    db_session.flush()
    run_id = run.id

    results = [
        CollectedResult(
            search_query="q1", position=0, url="https://a.com",
            title="A", snippet="s", media="m", published_at=date(2025, 1, 1),
        ),
        CollectedResult(
            search_query="q2", position=0, url="https://a.com",  # same URL
            title="A2", snippet="s", media="m", published_at=date(2025, 1, 2),
        ),
        CollectedResult(
            search_query="q2", position=1, url="https://b.com",
            title="B", snippet="s", media="m", published_at=date(2025, 1, 3),
        ),
    ]
    inserted = persist_search_results(db_session, run_id, results)
    assert inserted == 2  # a.com deduped
    rows = db_session.query(ResearchSearchResult).filter(
        ResearchSearchResult.research_run_id == run_id
    ).all()
    assert len(rows) == 2
    urls = {r.url for r in rows}
    assert urls == {"https://a.com", "https://b.com"}


def test_persist_search_results_empty_list_noop(db_session):
    assert persist_search_results(db_session, 1, []) == 0
