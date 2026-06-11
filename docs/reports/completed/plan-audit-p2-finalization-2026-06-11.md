# Audit Round 6 P2 Finalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the remaining 4 P2 architectural refactors from audit round 6: remove redundant service commits, add response_model to complex endpoints, unify serialization to Pydantic, and make EventBus async.

**Architecture:** Four independent batches, each produces working tested software. Batches are ordered by risk: lowest-risk commit removals first, highest-risk EventBus async last. Each batch can ship independently if earlier batches stall.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy / Pydantic v2 / pytest, threading for EventBus

---

## Context

Audit round 6 found 32 issues. 29 are fixed. These 4 remaining items are architectural refactors identified during the audit:

- **P2-06**: 46 manual `db.commit()` calls in services; ~28 are redundant (API auto-commits via `get_db`)
- **P2-09c**: ~15 complex endpoints lack `response_model` (cockpit, kline, market, review, stocks detail)
- **P2-11**: 4 inconsistent serialization patterns (manual dict, dataclass to_dict, Pydantic from_orm, raw returns)
- **P2-12**: EventBus is synchronous; 3 of 4 `emit()` calls block API responses

---

## File Structure

**Created files:**
- `backend/app/schemas/cockpit.py` — CockpitResponse + nested item schemas
- `backend/app/schemas/market.py` — Market index, cycle, dividend projection schemas
- `backend/app/schemas/review.py` — Monthly/quarterly/annual review schemas
- `backend/app/schemas/kline.py` (extend) — KlineSummary, ShareholdersNum, etc.
- `backend/app/schemas/stocks_detail.py` — Customers, suppliers, revenue composition
- `backend/tests/test_cockpit_response_model.py`
- `backend/tests/test_universe_service.py` (if missing)
- `backend/tests/test_event_bus_async.py`

**Modified files:**
- Services with redundant commits (watchlist, alert, dividend, theme, data_management)
- Routers missing response_model (cockpit, stocks, market, review, drafts)
- `backend/app/core/events.py` — async dispatch
- `backend/app/core/event_handlers.py` — session safety
- Dataclasses with `to_dict` — convert to Pydantic where feasible

---

## Batch 1: Remove Redundant Service Commits (P2-06)

### Task 1: Remove commits from theme_service.py (API-only, safe)

**Files:**
- Modify: `backend/app/services/theme_service.py`

- [ ] **Step 1: Read the file to identify all `db.commit()` calls**

Run: `grep -n "db.commit()" backend/app/services/theme_service.py`

Expected: 3 lines (around 191, 215, 227)

- [ ] **Step 2: Remove all 3 manual commits**

For each line found, delete the `db.commit()` call. Do NOT change anything else. The `get_db` dependency auto-commits after the router yields the session.

- [ ] **Step 3: Run tests**

Run: `cd backend && source .venv/bin/activate && pytest tests/ -q --tb=line 2>&1 | tail -5`
Expected: 399 passed

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/theme_service.py
git commit -m "refactor: remove redundant db.commit() from theme_service (P2-06)"
```

### Task 2: Remove commits from data_management_service.py (API-only, safe)

**Files:**
- Modify: `backend/app/services/data_management_service.py`

- [ ] **Step 1: Identify commits**

Run: `grep -n "db.commit()" backend/app/services/data_management_service.py`

Expected: 2 lines (around 124, 226)

- [ ] **Step 2: Remove both commits**

Delete each `db.commit()` line.

- [ ] **Step 3: Run tests + commit**

Run: `cd backend && pytest tests/ -q --tb=line 2>&1 | tail -5`

```bash
git add backend/app/services/data_management_service.py
git commit -m "refactor: remove redundant db.commit() from data_management_service (P2-06)"
```

### Task 3: Remove API-method commits from watchlist_service.py

**Files:**
- Modify: `backend/app/services/watchlist_service.py`

**Context:** watchlist_service is called from both API routes (via `get_db`, auto-commits) and scheduler (via `SessionLocal`, needs manual commit). The scheduler only calls `all_watched_codes()` which is read-only (no commit). So ALL commits are redundant.

- [ ] **Step 1: Verify scheduler only calls read-only methods**

Run: `grep -n "watchlist_service\." backend/app/scheduler.py backend/app/core/event_handlers.py`

Expected: Only `all_watched_codes()` or similar read-only calls.

- [ ] **Step 2: Remove all 7 manual commits**

Run: `grep -n "db.commit()" backend/app/services/watchlist_service.py`

Delete each `db.commit()` line (around lines 23, 46, 58, 68, 94, 116, 128, 138).

- [ ] **Step 3: Run tests + commit**

Run: `cd backend && pytest tests/test_watchlist* tests/ -q --tb=line 2>&1 | tail -5`

```bash
git add backend/app/services/watchlist_service.py
git commit -m "refactor: remove redundant db.commit() from watchlist_service API methods (P2-06)"
```

### Task 4: Remove API-method commits from dividend_service.py (mixed service)

**Files:**
- Modify: `backend/app/services/dividend_service.py`

**Context:** dividend_service has CRUD methods called from API (redundant commits) and `fetch_and_store_from_lixinger()` called from scheduler (REQUIRES commit). Only remove commits from API CRUD methods.

- [ ] **Step 1: Identify which methods are scheduler-only**

Run: `grep -n "dividend_service\." backend/app/scheduler.py backend/app/core/event_handlers.py`

Expected: Only `fetch_and_store_from_lixinger` is scheduler-called.

- [ ] **Step 2: Read the file and identify API CRUD methods**

API methods: `create_dividend_record`, `update_dividend_record`, `delete_dividend_record`
Scheduler method: `fetch_and_store_from_lixinger` (keep its commit)

- [ ] **Step 3: Remove commits ONLY from API CRUD methods**

Delete `db.commit()` from create/update/delete methods (around lines 45, 71). Keep the commit in `fetch_and_store_from_lixinger` (around line 121, 217).

- [ ] **Step 4: Run tests + commit**

Run: `cd backend && pytest tests/test_dividend* tests/ -q --tb=line 2>&1 | tail -5`

```bash
git add backend/app/services/dividend_service.py
git commit -m "refactor: remove redundant db.commit() from dividend_service API CRUD methods (P2-06)"
```

### Task 5: Remove API-method commits from alert_service.py (mixed service)

**Files:**
- Modify: `backend/app/services/alert_service.py`

**Context:** alert_service has CRUD methods (API, redundant commits) and `evaluate_all_rules()` + `sync_stop_profit_rules_from_holdings()` (scheduler/handler, keep commits).

- [ ] **Step 1: Identify scheduler/handler-called methods**

Run: `grep -n "alert_service\." backend/app/scheduler.py backend/app/core/event_handlers.py`

- [ ] **Step 2: Remove commits ONLY from API CRUD methods**

API methods: `create_rule`, `update_rule`, `delete_rule`, `ack_event`, `ack_all_events`
Keep commits in: `evaluate_all_rules`, `sync_stop_profit_rules_from_holdings`, `sync_rules_from_watchlist`

- [ ] **Step 3: Run tests + commit**

Run: `cd backend && pytest tests/ -q --tb=line 2>&1 | tail -5`

```bash
git add backend/app/services/alert_service.py
git commit -m "refactor: remove redundant db.commit() from alert_service API CRUD methods (P2-06)"
```

---

## Batch 2: Add response_model to Complex Endpoints (P2-09c)

### Task 6: Create CockpitResponse schema and apply to cockpit endpoint

**Files:**
- Create: `backend/app/schemas/cockpit.py`
- Modify: `backend/app/routers/cockpit.py`
- Test: `backend/tests/test_cockpit_response_model.py`

- [ ] **Step 1: Read the cockpit service return structure**

Read: `backend/app/services/cockpit_service.py` lines 194-219 — the `return {...}` dict.

- [ ] **Step 2: Create the schema file**

Create `backend/app/schemas/cockpit.py`:

```python
"""Response schemas for the cockpit aggregator endpoint."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class CockpitCashflow(BaseModel):
    annual_expense: Optional[float] = None
    goal_multiple: Optional[float] = None
    target_annual_cashflow: Optional[float] = None
    weighted_dyr: Optional[float] = None
    annual_passive_cashflow: Optional[float] = None
    goal_progress: Optional[float] = None
    total_portfolio_value: Optional[float] = None
    currency: Optional[str] = None


class CockpitDraft(BaseModel):
    id: int
    plan_id: int
    code: str
    side: str
    status: str
    step_kind: Optional[str] = None
    step_index: Optional[int] = None
    add_pct: Optional[float] = None
    reduce_pct_of_position: Optional[float] = None
    reason: Optional[str] = None
    source: Optional[str] = None
    triggered_at: Optional[str] = None


class CockpitHoldingItem(BaseModel):
    id: int
    stock_code: str
    stock_name: Optional[str] = None
    stock_industry: Optional[str] = None
    stock_tier: Optional[str] = None
    buy_date: Optional[str] = None
    buy_price: Optional[float] = None
    quantity: Optional[float] = None
    current_value: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    annualized_return_pct: Optional[float] = None
    weight_pct: Optional[float] = None
    stop_profit_price: Optional[float] = None


class CockpitHoldings(BaseModel):
    items: list[CockpitHoldingItem] = []
    warnings: list[str] = []
    summary: Optional[dict[str, Any]] = None


class CockpitQuadrantItem(BaseModel):
    quadrant: str
    weight_pct: Optional[float] = None
    value: Optional[float] = None
    count: Optional[int] = None


class CockpitAlertItem(BaseModel):
    id: int
    rule_id: Optional[int] = None
    stock_code: Optional[str] = None
    level: Optional[str] = None
    message: Optional[str] = None
    triggered_at: Optional[str] = None


class CockpitAlerts(BaseModel):
    items: list[CockpitAlertItem] = []
    unacked_count: int = 0


class CockpitPlan(BaseModel):
    id: int
    slug: Optional[str] = None
    name: str
    status: str
    description: Optional[str] = None
    is_builtin: Optional[bool] = None


class CockpitResponse(BaseModel):
    as_of: str
    cashflow: CockpitCashflow = CockpitCashflow()
    drafts: list[CockpitDraft] = []
    holdings: CockpitHoldings = CockpitHoldings()
    quadrant: list[dict[str, Any]] = []
    alerts: CockpitAlerts = CockpitAlerts()
    plans: list[CockpitPlan] = []
    theme_exposure: list[dict[str, Any]] = []
    rebalance_suggestions: list[dict[str, Any]] = []
    cycle: Optional[dict[str, Any]] = None
    dividend_projection: Optional[dict[str, Any]] = None
    thesis_alerts: list[dict[str, Any]] = []
    errors: list[str] = []
```

- [ ] **Step 3: Apply response_model to the endpoint**

In `backend/app/routers/cockpit.py`, add import and decorator:

```python
from app.schemas.cockpit import CockpitResponse

@router.get("", response_model=CockpitResponse)
def get_cockpit(db: Session = Depends(get_db)):
    ...
```

- [ ] **Step 4: Write a test that the endpoint returns valid CockpitResponse**

Create `backend/tests/test_cockpit_response_model.py`:

```python
"""Test that cockpit endpoint returns schema-valid responses."""

from fastapi.testclient import TestClient
from app.main import app


def test_cockpit_returns_valid_schema():
    client = TestClient(app)
    resp = client.get("/api/cockpit")
    assert resp.status_code == 200
    data = resp.json()
    assert "as_of" in data
    assert "holdings" in data
    assert "items" in data["holdings"]
    assert isinstance(data["errors"], list)
```

- [ ] **Step 5: Run tests**

Run: `cd backend && pytest tests/test_cockpit_response_model.py tests/ -q --tb=short 2>&1 | tail -10`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/cockpit.py backend/app/routers/cockpit.py backend/tests/test_cockpit_response_model.py
git commit -m "feat: add CockpitResponse schema and response_model to cockpit endpoint (P2-09c)"
```

### Task 7: Add response_model to kline_summary and stock detail endpoints

**Files:**
- Modify: `backend/app/schemas/kline.py` (extend with summary schemas)
- Modify: `backend/app/routers/stocks.py`

- [ ] **Step 1: Read the endpoint return shapes**

Read `backend/app/routers/stocks.py` lines 165-410 to see what each endpoint returns. Most delegate to `stocks_detail_service` functions.

- [ ] **Step 2: Add schemas to kline.py**

Append to `backend/app/schemas/kline.py`:

```python
class KlineSummaryItem(BaseModel):
    stock_code: str
    stock_name: Optional[str] = None
    earliest_date: Optional[str] = None
    latest_date: Optional[str] = None
    total_bars: Optional[int] = None


class KlineSummaryResponse(BaseModel):
    items: list[KlineSummaryItem] = []
```

Create `backend/app/schemas/stocks_detail.py`:

```python
"""Response schemas for stock detail endpoints (shareholders, customers, suppliers, revenue)."""

from typing import Optional, Any

from pydantic import BaseModel


class ShareholdersNumRecord(BaseModel):
    date: Optional[str] = None
    shareholders_num: Optional[int] = None
    avg_holding_value: Optional[float] = None


class ThesisTemplatesResponse(BaseModel):
    industry: Optional[str] = None
    templates: list[dict[str, Any]] = []
```

For `customers`, `suppliers`, `revenue_composition`: these return dynamic Lixinger data. Use `list[dict[str, Any]]` as the response_model (validated as JSON array but fields are passthrough).

- [ ] **Step 3: Apply response_model to each endpoint**

In `stocks.py`:

```python
@router.get("/kline-summary", response_model=KlineSummaryResponse)
def api_kline_summary(...):

@router.get("/{code}/shareholders-num", response_model=list[ShareholdersNumRecord])
def api_shareholders_num(...):

@router.get("/{code}/customers", response_model=list[dict])
def api_customers(...):

@router.get("/{code}/suppliers", response_model=list[dict])
def api_suppliers(...):

@router.get("/{code}/revenue-composition", response_model=list[dict])
def api_revenue_composition(...):

@router.get("/{code}/thesis-templates", response_model=ThesisTemplatesResponse)
def get_thesis_templates(...):
```

Add all imports at the top.

- [ ] **Step 4: Run tests + commit**

Run: `cd backend && pytest tests/ -q --tb=line 2>&1 | tail -5`

```bash
git add backend/app/schemas/kline.py backend/app/schemas/stocks_detail.py backend/app/routers/stocks.py
git commit -m "feat: add response_model to kline_summary and stock detail endpoints (P2-09c)"
```

### Task 8: Add response_model to market endpoints

**Files:**
- Create: `backend/app/schemas/market.py`
- Modify: `backend/app/routers/market.py`

- [ ] **Step 1: Read market router and services**

Read `backend/app/routers/market.py` completely. Read the `assess_cycle`, `project_dividends`, `check_held_stocks` service functions to understand return shapes.

- [ ] **Step 2: Create market schemas**

Create `backend/app/schemas/market.py`:

```python
"""Response schemas for market endpoints."""

from typing import Any, Optional

from pydantic import BaseModel


class IndexKlinePoint(BaseModel):
    date: Optional[str] = None
    close: Optional[float] = None


class IndexKlineResponse(BaseModel):
    stock_code: str
    points: list[IndexKlinePoint] = []


class CycleAssessmentResponse(BaseModel):
    """Market cycle assessment — uses model_validate from dataclass.to_dict()."""
    model_config = {"extra": "allow"}

    temperature: Optional[float] = None
    stage: Optional[str] = None


class DividendProjectionResponse(BaseModel):
    """Dividend projection — fields vary, allow extra."""
    model_config = {"extra": "allow"}


class ThesisAlertResponse(BaseModel):
    """Thesis alert item — fields vary, allow extra."""
    model_config = {"extra": "allow"}
```

Note: For cycle/dividend/thesis endpoints that return dataclass `.to_dict()`, use `extra="allow"` so all fields pass through while still validating the response shape.

- [ ] **Step 3: Apply response_model to all 5 market endpoints**

```python
from app.schemas.market import (
    IndexKlineResponse, CycleAssessmentResponse,
    DividendProjectionResponse, ThesisAlertResponse,
)

@router.get("/indices", response_model=list[dict])
def api_get_market_indices(...):

@router.get("/index/{code}/kline", response_model=IndexKlineResponse)
def api_get_index_kline(...):

@router.get("/cycle", response_model=CycleAssessmentResponse)
def api_get_cycle_assessment(...):

@router.get("/dividend-projection", response_model=DividendProjectionResponse)
def api_get_dividend_projection(...):

@router.get("/thesis-alerts", response_model=list[ThesisAlertResponse])
def api_get_thesis_alerts(...):
```

- [ ] **Step 4: Run tests + commit**

Run: `cd backend && pytest tests/ -q --tb=line 2>&1 | tail -5`

```bash
git add backend/app/schemas/market.py backend/app/routers/market.py
git commit -m "feat: add response_model to all market endpoints (P2-09c)"
```

### Task 9: Add response_model to review and drafts backfill endpoints

**Files:**
- Create: `backend/app/schemas/review.py`
- Modify: `backend/app/routers/review.py`
- Modify: `backend/app/routers/drafts.py`

- [ ] **Step 1: Create review schema**

Create `backend/app/schemas/review.py`:

```python
"""Response schemas for review endpoints."""

from typing import Any, Optional

from pydantic import BaseModel


class ReviewResponse(BaseModel):
    """Review data — structure varies by period, allow extra fields."""
    model_config = {"extra": "allow"}

    period: Optional[str] = None


class BackfillSuggestionResponse(BaseModel):
    model_config = {"extra": "allow"}
    action: str
    message: Optional[str] = None
```

- [ ] **Step 2: Apply to review endpoints**

```python
from app.schemas.review import ReviewResponse

@router.get("", response_model=ReviewResponse)
def get_monthly_review(...):

@router.get("/quarterly", response_model=ReviewResponse)
def get_quarterly_review(...):

@router.get("/annual", response_model=ReviewResponse)
def get_annual_review(...):
```

- [ ] **Step 3: Apply to drafts backfill**

In `drafts.py`:

```python
from app.schemas.review import BackfillSuggestionResponse

@router.get("/{draft_id}/backfill-suggestion", response_model=BackfillSuggestionResponse)
def get_backfill_suggestion(...):
```

- [ ] **Step 4: Run tests + commit**

Run: `cd backend && pytest tests/ -q --tb=line 2>&1 | tail -5`

```bash
git add backend/app/schemas/review.py backend/app/routers/review.py backend/app/routers/drafts.py
git commit -m "feat: add response_model to review and drafts backfill endpoints (P2-09c)"
```

---

## Batch 3: Unify Serialization to Pydantic (P2-11)

### Task 10: Convert RebalanceSuggestion dataclass to Pydantic model

**Files:**
- Modify: `backend/app/services/rebalance_service.py`
- Test: `backend/tests/test_rebalance_service.py`

**Context:** `RebalanceSuggestion` is a dataclass with `.to_dict()`. Converting to Pydantic gives validation + serialization for free.

- [ ] **Step 1: Read current dataclass**

Read `backend/app/services/rebalance_service.py` to find the `RebalanceSuggestion` dataclass definition.

- [ ] **Step 2: Convert to Pydantic BaseModel**

Replace the `@dataclass` with Pydantic:

```python
from pydantic import BaseModel

class RebalanceSuggestion(BaseModel):
    stock_code: str
    stock_name: Optional[str] = None
    current_weight: Optional[float] = None
    target_weight: Optional[float] = None
    drift: Optional[float] = None
    action: Optional[str] = None
    # ... preserve ALL existing fields
```

Remove the `to_dict()` method — Pydantic's `.model_dump()` replaces it.

- [ ] **Step 3: Update all callers of `.to_dict()`**

Search: `grep -rn "\.to_dict()" backend/app/ | grep rebalance`

Replace `.to_dict()` with `.model_dump()` in cockpit_service.py and any other callers.

- [ ] **Step 4: Run tests + commit**

Run: `cd backend && pytest tests/ -q --tb=line 2>&1 | tail -5`

```bash
git add backend/app/services/rebalance_service.py backend/app/services/cockpit_service.py
git commit -m "refactor: convert RebalanceSuggestion from dataclass to Pydantic model (P2-11)"
```

### Task 11: Convert CycleAssessment dataclass to Pydantic

**Files:**
- Modify: `backend/app/services/cycle_assessment_service.py`

- [ ] **Step 1: Read current dataclass**

Find `CycleAssessment` dataclass.

- [ ] **Step 2: Convert to Pydantic**

```python
from pydantic import BaseModel

class CycleAssessment(BaseModel):
    temperature: Optional[float] = None
    stage: Optional[str] = None
    # ... preserve ALL fields
```

Remove `to_dict()`, update callers to `.model_dump()`.

- [ ] **Step 3: Run tests + commit**

Run: `cd backend && pytest tests/ -q --tb=line 2>&1 | tail -5`

```bash
git add backend/app/services/cycle_assessment_service.py backend/app/services/cockpit_service.py
git commit -m "refactor: convert CycleAssessment from dataclass to Pydantic (P2-11)"
```

### Task 12: Document the serialization standard

**Files:**
- Create: `docs/active/serialization-standard.md`

- [ ] **Step 1: Write the standard doc**

```markdown
# Serialization Standard

## Rule: All ORM-to-response conversions use Pydantic schemas

1. Define a `XxxResponse` Pydantic model in `app/schemas/`
2. Service layer constructs Pydantic models directly OR returns ORM objects
3. Routers declare `response_model=XxxResponse` — FastAPI handles serialization
4. Dataclasses for internal computation should be converted to Pydantic if they cross the API boundary
5. `.model_dump()` (Pydantic v2) replaces manual `to_dict()` methods

## Anti-patterns removed:
- Manual dict construction in service layer (_serialize_*)
- dataclass.to_dict() methods
- Raw dict returns without response_model
```

- [ ] **Step 2: Commit**

```bash
git add docs/active/serialization-standard.md
git commit -m "docs: document Pydantic serialization standard (P2-11)"
```

---

## Batch 4: Make EventBus Async (P2-12)

### Task 13: Add async dispatch mode to EventBus

**Files:**
- Modify: `backend/app/core/events.py`
- Test: `backend/tests/test_event_bus_async.py`

**Context:** The current `emit()` blocks until all handlers complete. We add a new `emit_async()` that dispatches handlers to a thread pool. The scheduler already runs in background, so only API-path callers need async dispatch.

- [ ] **Step 1: Write failing test for async dispatch**

Create `backend/tests/test_event_bus_async.py`:

```python
"""Tests for async EventBus dispatch."""

import threading
import time

from app.core.events import bus, BaseEvent


class _TestEvent(BaseEvent):
    """Test event type."""
    pass


_handler_thread_ids = []


def test_emit_async_does_not_block():
    """emit_async should return before slow handlers complete."""
    slow_done = threading.Event()

    def slow_handler(event):
        time.sleep(0.1)
        _handler_thread_ids.append(threading.current_thread().ident)
        slow_done.set()

    bus.register(_TestEvent, slow_handler)
    try:
        start = time.monotonic()
        bus.emit_async(_TestEvent())
        elapsed = time.monotonic() - start
        # Should return immediately, not wait 0.1s
        assert elapsed < 0.05, f"emit_async blocked for {elapsed:.3f}s"
        # Wait for handler to finish
        assert slow_done.wait(timeout=1.0)
        # Handler ran in a different thread
        assert _handler_thread_ids[-1] != threading.current_thread().ident
    finally:
        bus.unregister(_TestEvent, slow_handler)


def test_emit_sync_still_blocks():
    """emit (sync) should still block until handlers complete."""
    done = threading.Event()

    def handler(event):
        done.set()

    bus.register(_TestEvent, handler)
    try:
        bus.emit(_TestEvent())
        assert done.is_set()
    finally:
        bus.unregister(_TestEvent, handler)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_event_bus_async.py -v 2>&1 | tail -10`
Expected: FAIL — `emit_async` not defined

- [ ] **Step 3: Add `emit_async` to EventBus**

Read `backend/app/core/events.py` to understand current structure. Add a thread-pool-based async dispatcher:

```python
import threading
from concurrent.futures import ThreadPoolExecutor

# Module-level executor for async event dispatch
_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="eventbus")
    return _executor


class EventBus:
    # ... existing code unchanged ...

    def emit_async(self, event: BaseEvent) -> None:
        """Dispatch event to handlers in background threads.

        Returns immediately without waiting for handlers. Use for
        request-path events that shouldn't block the response.
        """
        handlers = self._get_handlers(type(event))
        executor = _get_executor()
        for handler in handlers:
            executor.submit(self._safe_call, handler, event)

    def _safe_call(self, handler, event: BaseEvent) -> None:
        """Call a handler, logging exceptions instead of propagating."""
        try:
            handler(event)
        except Exception:
            logger.exception("EventBus handler %s failed", handler.__name__)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd backend && pytest tests/test_event_bus_async.py -v 2>&1 | tail -10`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/events.py backend/tests/test_event_bus_async.py
git commit -m "feat: add emit_async for non-blocking EventBus dispatch (P2-12)"
```

### Task 14: Switch request-path emit calls to emit_async

**Files:**
- Modify: `backend/app/services/draft_service.py`
- Modify: `backend/app/services/alert_service.py`

**Context:** `draft_service.emit()` (lines 99, 125) and `alert_service.emit()` (line 181) are called from API request paths. Switch them to `emit_async` to unblock responses.

- [ ] **Step 1: Read the emit call sites**

Run: `grep -n "bus.emit" backend/app/services/draft_service.py backend/app/services/alert_service.py`

- [ ] **Step 2: Switch to emit_async in draft_service.py**

For each `bus.emit(...)` call in draft_service.py, change to `bus.emit_async(...)`.

- [ ] **Step 3: Switch to emit_async in alert_service.py**

For each `bus.emit(...)` call in alert_service.py (API-triggered alerts), change to `bus.emit_async(...)`.

- [ ] **Step 4: Keep sync emit in scheduler/handler paths**

`plan_runner.py` and `pipelines/manager.py` emit from scheduler context — keep sync `emit()` there since those are already background.

- [ ] **Step 5: Run tests + verify no regressions**

Run: `cd backend && pytest tests/ -q --tb=line 2>&1 | tail -5`

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/draft_service.py backend/app/services/alert_service.py
git commit -m "perf: switch request-path EventBus emit to emit_async (P2-12)"
```

### Task 15: Add graceful shutdown for event executor

**Files:**
- Modify: `backend/app/main.py` (lifecycle shutdown)
- Modify: `backend/app/core/events.py`

- [ ] **Step 1: Add shutdown function to events.py**

Add to `backend/app/core/events.py`:

```python
def shutdown_executor(wait: bool = True, timeout: float = 10.0) -> None:
    """Shutdown the event dispatch executor. Call on app shutdown."""
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=wait, cancel_futures=False)
            _executor = None
```

- [ ] **Step 2: Call shutdown in app lifecycle**

In `backend/app/main.py`, find the lifespan/shutdown handler and add:

```python
from app.core.events import shutdown_executor

# In the shutdown handler:
shutdown_executor(wait=True, timeout=10.0)
```

- [ ] **Step 3: Run tests + commit**

Run: `cd backend && pytest tests/ -q --tb=line 2>&1 | tail -5`

```bash
git add backend/app/core/events.py backend/app/main.py
git commit -m "feat: add graceful shutdown for EventBus executor (P2-12)"
```

---

## Verification

After all batches complete:

- [ ] **Full test suite passes**

Run: `cd backend && source .venv/bin/activate && pytest tests/ -q`
Expected: 399+ passed (count may grow from new tests)

- [ ] **Frontend build succeeds**

Run: `cd frontend && npm run build`

- [ ] **Manual smoke test**

Run: `./dev.sh`
- Open cockpit page — loads without errors
- Open candidates page — universe/full endpoint returns data
- Create a draft — response returns quickly (async EventBus)
- Trigger an alert — response returns quickly

- [ ] **Update audit report**

In `docs/progress/2026-06-11-audit-round6.md`, update the remaining P2 table to mark all 4 items as fixed.

---

## Risk Notes

- **Batch 1 (commits)**: Scheduler-called services keep their commits. If a test fails after removing commits, the method is likely called from scheduler — restore its commit.
- **Batch 2 (response_model)**: Adding `response_model` with `extra="allow"` for dynamic data is safe. If a schema is too strict and drops fields, switch to `extra="allow"`.
- **Batch 3 (serialization)**: Converting dataclasses to Pydantic changes `.to_dict()` to `.model_dump()`. Grep for all callers before committing.
- **Batch 4 (EventBus)**: `emit_async` changes ordering semantics — handlers may complete after the response is sent. Handlers must not rely on caller's DB session (they should create their own `SessionLocal()`). Verify each handler is session-safe before switching.
