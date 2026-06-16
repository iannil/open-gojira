"""Research search result — raw URLs returned by GLM web_search API.

Path B (2026-06-16): serenity research now uses two-step search → synthesis.
Step 1 collects ~30 queries' worth of real search results from
`client.web_search.web_search()` (standalone API), persists them here.
Step 2 LLM synthesis must cite URLs from this table — no fabrication.

Without this table, LLM hallucinated evidence URLs (curl-confirmed 2026-06-16:
cninfo returned size 0, pbc.gov.cn returned 404).
"""

from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ResearchSearchResult(Base):
    """One search result row from a single GLM web_search API call.

    Each row corresponds to one (query, position) tuple. Multiple rows share
    the same `search_query` (one query → up to N position-ordered results).
    Deduplicated by `url` within a run before persistence.
    """

    __tablename__ = "research_search_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    research_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("research_runs.id"), nullable=False, index=True
    )

    # Query that produced this result
    search_query: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    # Position within the query's result list (0-based)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    media: Mapped[str | None] = mapped_column(String, nullable=True)
    published_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    # GLM-assigned refer marker like "[ref_1]" — preserved for traceability
    refer: Mapped[str | None] = mapped_column(String, nullable=True)
