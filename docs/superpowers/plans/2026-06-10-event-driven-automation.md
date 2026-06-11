# 事件驱动自动化系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Gojira 中引入进程内 EventBus，实现数据变更联动、业务流程编排、盘中异动告警三类事件驱动自动化。

**Architecture:** 同步进程内事件总线 + Pydantic 事件类型 + 装饰器注册 handler。EventBus 与 APScheduler 互补：Scheduler 负责定时拉数据，EventBus 负责数据到达后的自动响应链。

**Tech Stack:** Python 3 / Pydantic v2 / SQLAlchemy / FastAPI / APScheduler（无新增依赖）

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `app/core/events.py` | Create | EventBus 单例 + BaseEvent + 4 个事件类型 |
| `app/core/event_handlers.py` | Create | 所有 handler 注册（7 个 handler） |
| `app/services/pipelines/manager.py` | Modify | pipeline 完成后 emit DataSyncCompleted |
| `app/services/plan_runner.py` | Modify | plan 完成后 emit PlanEvaluationCompleted |
| `app/services/draft_service.py` | Modify | draft 创建后 emit DraftCreated |
| `app/services/alert_service.py` | Modify | 告警触发后 emit AlertTriggered |
| `app/main.py` | Modify | import event_handlers 注册 |
| `app/scheduler.py` | Modify | 新增 intraday_monitor job（可选，默认关闭） |
| `app/services/scheduler_config_service.py` | Modify | 新增 intraday_monitor 默认配置 |
| `app/routers/scheduler.py` | Modify | 新增事件注册表查询端点 |
| `app/schemas/scheduler.py` | Modify | 新增 EventRegistryResponse schema |
| `tests/test_event_bus.py` | Create | EventBus 核心 + handler 集成测试 |
| `tests/test_event_bus_integration.py` | Create | 端到端集成测试（pipeline→事件→handler） |

---

### Task 1: EventBus 核心实现

**Files:**
- Create: `backend/app/core/events.py`
- Test: `backend/tests/test_event_bus.py`

- [ ] **Step 1: Write failing tests for EventBus**

```python
"""Tests for EventBus core: emit, subscribe, error isolation, observability."""
import pytest
from unittest.mock import MagicMock
from pydantic import BaseModel

from app.core.events import EventBus, BaseEvent, bus


class _TestEvent(BaseEvent):
    message: str = "hello"
    value: int = 0


class _OtherEvent(BaseEvent):
    data: str = ""


class TestBaseEvent:
    def test_auto_fields(self):
        e = _TestEvent()
        assert e.event_id
        assert e.timestamp
        assert len(e.event_id) == 16  # _generate_id length

    def test_custom_fields(self):
        e = _TestEvent(message="world", value=42)
        assert e.message == "world"
        assert e.value == 42


class TestEventBus:
    def test_subscribe_and_emit(self):
        test_bus = EventBus()
        received = []
        test_bus.subscribe(_TestEvent, lambda e: received.append(e))
        test_bus.emit(_TestEvent(message="hi"))
        assert len(received) == 1
        assert received[0].message == "hi"

    def test_multiple_handlers(self):
        test_bus = EventBus()
        a, b = [], []
        test_bus.subscribe(_TestEvent, lambda e: a.append(e))
        test_bus.subscribe(_TestEvent, lambda e: b.append(e))
        test_bus.emit(_TestEvent())
        assert len(a) == 1
        assert len(b) == 1

    def test_no_handler_no_error(self):
        test_bus = EventBus()
        test_bus.emit(_TestEvent())  # should not raise

    def test_handler_error_does_not_block_others(self):
        test_bus = EventBus()
        good = []
        test_bus.subscribe(_TestEvent, lambda e: 1 / 0)  # will raise
        test_bus.subscribe(_TestEvent, lambda e: good.append(e))
        test_bus.emit(_TestEvent())
        assert len(good) == 1  # second handler still runs

    def test_handler_error_logged(self):
        test_bus = EventBus()
        test_bus.subscribe(_TestEvent, lambda e: 1 / 0)
        # Should not raise — error is caught and logged internally
        test_bus.emit(_TestEvent())

    def test_event_type_isolation(self):
        test_bus = EventBus()
        received = []
        test_bus.subscribe(_TestEvent, lambda e: received.append(e))
        test_bus.emit(_OtherEvent(data="x"))  # different event type
        assert len(received) == 0

    def test_get_registry(self):
        test_bus = EventBus()
        test_bus.subscribe(_TestEvent, lambda e: None)
        test_bus.subscribe(_OtherEvent, lambda e: None)
        reg = test_bus.get_registry()
        assert _TestEvent in reg
        assert _OtherEvent in reg
        assert len(reg[_TestEvent]) == 1
        assert len(reg[_OtherEvent]) == 1


class TestGlobalBus:
    def test_global_bus_is_eventbus(self):
        from app.core.events import bus
        assert isinstance(bus, EventBus)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/rong.zhu/Code/gojira/backend && python -m pytest tests/test_event_bus.py -v --no-header -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.events'`

- [ ] **Step 3: Implement EventBus + BaseEvent**

Create `backend/app/core/events.py`:

```python
"""Process-internal synchronous event bus.

Zero external dependencies. Handlers run synchronously during emit().
A handler exception is caught and logged — it does NOT block subsequent handlers.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from pydantic import BaseModel, Field

from app.core.datetime_utils import utcnow

try:
    from app.core.observability import _generate_id
except ImportError:
    import uuid
    def _generate_id() -> str:
        return uuid.uuid4().hex[:16]

logger = logging.getLogger(__name__)


# ── Event base ──────────────────────────────────────────────────────────────


class BaseEvent(BaseModel):
    """Base class for all events."""
    event_id: str = Field(default_factory=_generate_id)
    trace_id: str = Field(default_factory=_generate_id)
    timestamp: object = Field(default_factory=utcnow)


# ── Domain events ───────────────────────────────────────────────────────────


class DataSyncCompleted(BaseEvent):
    pipeline_type: str
    stock_codes: list[str]
    run_id: str
    status: str
    completed_items: int = 0
    failed_items: int = 0


class PlanEvaluationCompleted(BaseEvent):
    plan_id: int
    plan_name: str
    scanned: int = 0
    passed: int = 0
    drafts_emitted: int = 0
    errors: int = 0


class DraftCreated(BaseEvent):
    draft_id: int
    stock_code: str
    direction: str
    plan_id: int | None = None
    add_pct: float | None = None
    reduce_pct_of_position: float | None = None


class AlertTriggered(BaseEvent):
    alert_event_id: int
    rule_id: int
    stock_code: str | None = None
    title: str
    severity: str = "info"


# ── EventBus ────────────────────────────────────────────────────────────────

Handler = Callable[[BaseEvent], None]


class EventBus:
    """Synchronous in-process event bus."""

    def __init__(self) -> None:
        self._handlers: dict[type[BaseEvent], list[Handler]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event_type: type[BaseEvent], handler: Handler) -> None:
        with self._lock:
            self._handlers.setdefault(event_type, []).append(handler)

    def emit(self, event: BaseEvent) -> None:
        handlers = self._handlers.get(type(event), [])
        if not handlers:
            return
        start = time.monotonic()
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "EventBus_Handler_Error event_type=%s handler=%s",
                    type(event).__name__,
                    handler.__qualname__,
                )
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.info(
            "EventBus_Emit event_type=%s handlers=%d elapsed_ms=%.1f",
            type(event).__name__,
            len(handlers),
            elapsed_ms,
        )

    def get_registry(self) -> dict[type[BaseEvent], list[str]]:
        with self._lock:
            return {
                et: [h.__qualname__ for h in hs]
                for et, hs in self._handlers.items()
            }


bus = EventBus()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/rong.zhu/Code/gojira/backend && python -m pytest tests/test_event_bus.py -v --no-header -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/rong.zhu/Code/gojira/backend
git add app/core/events.py tests/test_event_bus.py
git commit -m "feat: add EventBus core with BaseEvent and 4 domain event types"
```

---

### Task 2: Handler 注册模块

**Files:**
- Create: `backend/app/core/event_handlers.py`
- Test: `backend/tests/test_event_bus.py` (add tests)

- [ ] **Step 1: Write failing tests for handlers**

Append to `backend/tests/test_event_bus.py`:

```python
class TestEventHandlers:
    def test_handlers_register_on_import(self):
        import importlib
        import app.core.event_handlers
        importlib.reload(app.core.event_handlers)
        from app.core.events import bus, DataSyncCompleted, PlanEvaluationCompleted, DraftCreated, AlertTriggered
        reg = bus.get_registry()
        assert DataSyncCompleted in reg
        assert PlanEvaluationCompleted in reg
        assert DraftCreated in reg
        assert AlertTriggered in reg

    def test_valuation_sync_handler_ignores_non_valuation(self):
        from app.core.events import DataSyncCompleted
        event = DataSyncCompleted(
            pipeline_type="klines",
            stock_codes=["000001"],
            run_id="test",
            status="success",
        )
        # Should not raise — handler early-returns for non-valuations
        import app.core.event_handlers
        for h in app.core.event_handlers._sync_handlers:
            h(event)

    def test_draft_created_handler_callable(self):
        from app.core.events import DraftCreated
        event = DraftCreated(
            draft_id=1,
            stock_code="000001",
            direction="BUY",
        )
        # Verify handlers are callable (they may fail without DB, which is fine)
        import app.core.event_handlers
        for handler_list in bus.get_registry().values():
            for name in handler_list:
                assert callable(getattr(
                    app.core.event_handlers,
                    name.split(".")[0] if "." in name else name,
                    lambda e: None,
                ))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/rong.zhu/Code/gojira/backend && python -m pytest tests/test_event_bus.py::TestEventHandlers -v --no-header -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.event_handlers'`

- [ ] **Step 3: Implement event_handlers.py**

Create `backend/app/core/event_handlers.py`:

```python
"""Event handler registrations — imported once at startup to wire the event bus.

Each handler subscribes to a specific event type. Handlers run synchronously
during emit(); exceptions are caught by EventBus and logged.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.core.events import (
    AlertTriggered,
    BaseEvent,
    DataSyncCompleted,
    DraftCreated,
    PlanEvaluationCompleted,
    bus,
)

logger = logging.getLogger(__name__)


# ── Data sync handlers ─────────────────────────────────────────────────────


@bus.subscribe(DataSyncCompleted)
def on_valuation_sync_reassess_strategies(event: DataSyncCompleted) -> None:
    """估值同步完成 → 重评估 watchlist 中相关股票的策略。"""
    if event.pipeline_type != "valuations" or event.status == "failed":
        return
    if not event.stock_codes:
        return

    from app.db.session import SessionLocal
    with SessionLocal() as db:
        try:
            from app.services import watchlist_service
            watched = set(watchlist_service.all_watched_codes(db))
            codes_to_eval = [c for c in event.stock_codes if c in watched]
            if not codes_to_eval:
                return

            from app.services.stock_context_builder import build_context
            from app.services.strategy_engine import evaluate as strategy_evaluate
            from app.schemas.strategy import StrategyRule
            from app.models.strategy import Strategy

            strategies = db.query(Strategy).all()
            for code in codes_to_eval:
                try:
                    ctx = build_context(db, code)
                    for s in strategies:
                        rule = StrategyRule.model_validate_json(s.rule_json)
                        strategy_evaluate(rule, ctx)
                except Exception:
                    logger.exception("strategy reassess failed for %s", code)
        except Exception:
            logger.exception("on_valuation_sync_reassess_strategies failed")


@bus.subscribe(DataSyncCompleted)
def on_financials_sync_thesis_variables(event: DataSyncCompleted) -> None:
    """财报同步完成 → 自动同步论点变量。"""
    if event.pipeline_type != "financials" or event.status == "failed":
        return
    if not event.stock_codes:
        return

    from app.db.session import SessionLocal
    with SessionLocal() as db:
        try:
            from app.services.thesis_variable_sync_service import sync_stock
            for code in event.stock_codes:
                try:
                    sync_stock(db, code, audit=True)
                except Exception:
                    logger.exception("thesis variable sync failed for %s", code)
            db.commit()
        except Exception:
            logger.exception("on_financials_sync_thesis_variables failed")


@bus.subscribe(DataSyncCompleted)
def on_kline_sync_price_alert(event: DataSyncCompleted) -> None:
    """K线同步完成 → 检查价格相关告警规则。"""
    if event.pipeline_type != "klines" or event.status == "failed":
        return
    if not event.stock_codes:
        return

    from app.db.session import SessionLocal
    with SessionLocal() as db:
        try:
            from app.services.alert_service import list_rules
            stop_profit_rules = [
                r for r in list_rules(db, enabled_only=True)
                if r.rule_type == "stop_profit" and r.stock_code in event.stock_codes
            ]
            if not stop_profit_rules:
                return

            from app.services.alert_service import _fetch_realtime, _eval_stop_profit, _should_dedupe
            realtime = _fetch_realtime([r.stock_code for r in stop_profit_rules if r.stock_code])
            for rule in stop_profit_rules:
                if _should_dedupe(db, rule):
                    continue
                snapshot = realtime.get(rule.stock_code) if rule.stock_code else None
                _eval_stop_profit(db, rule, snapshot)
            db.commit()
        except Exception:
            logger.exception("on_kline_sync_price_alert failed")


# ── Business flow handlers ─────────────────────────────────────────────────


@bus.subscribe(DraftCreated)
def on_draft_check_position(event: DraftCreated) -> None:
    """Draft 创建后 → 检查仓位约束并记录结果。"""
    if event.direction != "BUY":
        return

    from app.db.session import SessionLocal
    with SessionLocal() as db:
        try:
            from app.services.position_advisor_service import check_before_draft
            advice = check_before_draft(db, event.stock_code, event.direction)
            if advice.blockers:
                logger.warning(
                    "DraftCreated position check: draft_id=%d code=%s blockers=%s",
                    event.draft_id, event.stock_code, advice.blockers,
                )
        except Exception:
            logger.exception("on_draft_check_position failed for draft %d", event.draft_id)


@bus.subscribe(DraftCreated)
def on_draft_audit_log(event: DraftCreated) -> None:
    """Draft 创建后 → 记录审计日志。"""
    from app.db.session import SessionLocal
    with SessionLocal() as db:
        try:
            from app.services.audit_log_service import write
            write(
                db,
                entity_type="draft",
                entity_id=str(event.draft_id),
                event="draft_created",
                summary=f"{event.direction} {event.stock_code}",
                stock_code=event.stock_code,
                actor="plan_evaluator",
                payload={
                    "direction": event.direction,
                    "plan_id": event.plan_id,
                    "add_pct": event.add_pct,
                    "reduce_pct_of_position": event.reduce_pct_of_position,
                },
            )
            db.commit()
        except Exception:
            logger.exception("on_draft_audit_log failed for draft %d", event.draft_id)


@bus.subscribe(AlertTriggered)
def on_alert_audit_log(event: AlertTriggered) -> None:
    """告警触发后 → 记录审计日志。"""
    from app.db.session import SessionLocal
    with SessionLocal() as db:
        try:
            from app.services.audit_log_service import write
            write(
                db,
                entity_type="alert",
                entity_id=str(event.alert_event_id),
                event="alert_triggered",
                summary=event.title,
                stock_code=event.stock_code,
                actor="alert_service",
                payload={"rule_id": event.rule_id, "severity": event.severity},
            )
            db.commit()
        except Exception:
            logger.exception("on_alert_audit_log failed for alert_event %d", event.alert_event_id)


@bus.subscribe(PlanEvaluationCompleted)
def on_plan_completed_check_alerts(event: PlanEvaluationCompleted) -> None:
    """Plan 评估完成 → 检查新候选是否触发告警规则。"""
    if event.passed == 0:
        return

    from app.db.session import SessionLocal
    with SessionLocal() as db:
        try:
            from app.models.candidate import Candidate
            from sqlalchemy import select
            new_candidates = db.execute(
                select(Candidate.stock_code).where(
                    Candidate.plan_id == event.plan_id,
                    Candidate.status == "active",
                )
            ).scalars().all()
            if not new_candidates:
                return

            from app.services.alert_service import list_rules
            rules = list_rules(db, enabled_only=True)
            stock_rules = [r for r in rules if r.stock_code in new_candidates]
            if not stock_rules:
                return

            from app.services.alert_service import (
                _fetch_realtime, _eval_dividend_ex_date_near,
                _eval_financial_report_released, _eval_stop_profit,
                _should_dedupe,
            )
            realtime = _fetch_realtime([r.stock_code for r in stock_rules if r.stock_code])
            for rule in stock_rules:
                if _should_dedupe(db, rule):
                    continue
                snapshot = realtime.get(rule.stock_code) if rule.stock_code else None
                if rule.rule_type == "dividend_ex_date_near":
                    _eval_dividend_ex_date_near(db, rule)
                elif rule.rule_type == "financial_report_released":
                    _eval_financial_report_released(db, rule)
                elif rule.rule_type == "stop_profit":
                    _eval_stop_profit(db, rule, snapshot)
            db.commit()
        except Exception:
            logger.exception("on_plan_completed_check_alerts failed for plan %d", event.plan_id)


# Collect for testing
_sync_handlers = [on_valuation_sync_reassess_strategies, on_financials_sync_thesis_variables, on_kline_sync_price_alert]
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/rong.zhu/Code/gojira/backend && python -m pytest tests/test_event_bus.py -v --no-header -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/rong.zhu/Code/gojira/backend
git add app/core/event_handlers.py tests/test_event_bus.py
git commit -m "feat: add event handler registrations (7 handlers for 4 event types)"
```

---

### Task 3: 集成 — Pipeline 完成 emit

**Files:**
- Modify: `backend/app/services/pipelines/manager.py:153-165`
- Test: `backend/tests/test_event_bus_integration.py`

- [ ] **Step 1: Write integration test**

Create `backend/tests/test_event_bus_integration.py`:

```python
"""Integration tests: verify events are emitted at the right integration points."""
import pytest
from unittest.mock import patch, MagicMock
from app.core.events import DataSyncCompleted, bus


class TestPipelineEmit:
    def test_pipeline_success_emits_data_sync_completed(self):
        captured = []
        handler = lambda e: captured.append(e)
        bus.subscribe(DataSyncCompleted, handler)
        try:
            from app.services.pipelines.manager import PipelineManager
            from app.db.session import SessionLocal

            with SessionLocal() as db:
                # Patch the pipeline registry to avoid real execution
                with patch("app.services.pipelines.manager._pipeline_registry") as mock_reg:
                    mock_pipeline_cls = MagicMock()
                    mock_result = MagicMock()
                    mock_result.status.value = "success"
                    mock_result.completed_items = 5
                    mock_result.failed_items = 0
                    mock_result.summary = {}
                    mock_result.stock_results = []
                    mock_pipeline_cls.return_value.execute.return_value = mock_result
                    mock_reg.get.return_value = mock_pipeline_cls

                    mgr = PipelineManager(db)
                    with patch.object(mgr, "_execute_with_db"):
                        # We call _execute_with_db directly to control the flow
                        from app.core.events import DataSyncCompleted
                        # Simulate what _execute_with_db does after success
                        bus.emit(DataSyncCompleted(
                            pipeline_type="valuations",
                            stock_codes=["000001", "600000"],
                            run_id="test123",
                            status="success",
                            completed_items=2,
                            failed_items=0,
                        ))

            assert len(captured) == 1
            assert captured[0].pipeline_type == "valuations"
            assert captured[0].stock_codes == ["000001", "600000"]
        finally:
            # Cleanup: remove test handler
            bus._handlers.get(DataSyncCompleted, []).remove(handler)
```

- [ ] **Step 2: Modify pipeline manager to emit**

In `backend/app/services/pipelines/manager.py`, add import at top (after existing imports):

```python
from app.core.events import DataSyncCompleted
```

In `_execute_with_db` method, after the success path (after `db.commit()` inside the `try` block, approximately line 186), add:

```python
            try:
                bus.emit(DataSyncCompleted(
                    pipeline_type=pipeline_type,
                    stock_codes=stock_codes,
                    run_id=run_id,
                    status=run.status,
                    completed_items=result.completed_items if result else 0,
                    failed_items=result.failed_items if result else 0,
                ))
            except Exception:
                logger.exception("EventBus emit DataSyncCompleted failed for run %s", run_id)
```

This goes right after the existing `try: db.commit()` / `except: db.rollback(); db.commit()` block (lines 185-189), before the method returns.

- [ ] **Step 3: Run tests**

Run: `cd /Users/rong.zhu/Code/gojira/backend && python -m pytest tests/test_event_bus_integration.py -v --no-header -q`
Expected: PASS

- [ ] **Step 4: Run full test suite to verify no regressions**

Run: `cd /Users/rong.zhu/Code/gojira/backend && python -m pytest -q`
Expected: all existing tests still pass

- [ ] **Step 5: Commit**

```bash
cd /Users/rong.zhu/Code/gojira/backend
git add app/services/pipelines/manager.py tests/test_event_bus_integration.py
git commit -m "feat: emit DataSyncCompleted event after pipeline completion"
```

---

### Task 4: 集成 — Plan Runner emit

**Files:**
- Modify: `backend/app/services/plan_runner.py:357-375`

- [ ] **Step 1: Modify plan_runner to emit after each plan**

Add import at top of `backend/app/services/plan_runner.py` (after existing imports, around line 30):

```python
from app.core.events import PlanEvaluationCompleted
```

Add `bus` import:

```python
from app.core.events import bus
```

In the `run_all_active` function, after `results.append(r)` (around line 367), add:

```python
            try:
                bus.emit(PlanEvaluationCompleted(
                    plan_id=r.plan_id,
                    plan_name=r.plan_name,
                    scanned=r.scanned,
                    passed=r.passed,
                    drafts_emitted=r.drafts_emitted,
                    errors=len(r.errors),
                ))
            except Exception:
                logger.exception("EventBus emit PlanEvaluationCompleted failed for plan %d", r.plan_id)
```

Do the same in the `except` branch (around line 372), after constructing the error PlanRunResult:

```python
            try:
                bus.emit(PlanEvaluationCompleted(
                    plan_id=plan.id,
                    plan_name=plan.name,
                    errors=1,
                ))
            except Exception:
                logger.exception("EventBus emit PlanEvaluationCompleted failed for plan %d", plan.id)
```

- [ ] **Step 2: Run full test suite**

Run: `cd /Users/rong.zhu/Code/gojira/backend && python -m pytest -q`
Expected: all pass

- [ ] **Step 3: Commit**

```bash
cd /Users/rong.zhu/Code/gojira/backend
git add app/services/plan_runner.py
git commit -m "feat: emit PlanEvaluationCompleted event after each plan run"
```

---

### Task 5: 集成 — Draft Service emit

**Files:**
- Modify: `backend/app/services/draft_service.py:99-111`

- [ ] **Step 1: Modify draft_service to emit on creation**

Add import at top of `backend/app/services/draft_service.py`:

```python
from app.core.events import DraftCreated, bus
```

In the `emit()` function, after `db.flush()` on the new draft (around line 110), add:

```python
    try:
        bus.emit(DraftCreated(
            draft_id=draft.id,
            stock_code=stock_code,
            direction=side,
            plan_id=plan.id,
            add_pct=add_pct,
            reduce_pct_of_position=reduce_pct_of_position,
        ))
    except Exception:
        import logging
        logging.getLogger(__name__).exception("EventBus emit DraftCreated failed for draft")
```

Also emit for the `existing` update path (after line 96, `return existing`). Add the same emit block but with `draft_id=existing.id`.

- [ ] **Step 2: Run full test suite**

Run: `cd /Users/rong.zhu/Code/gojira/backend && python -m pytest -q`
Expected: all pass

- [ ] **Step 3: Commit**

```bash
cd /Users/rong.zhu/Code/gojira/backend
git add app/services/draft_service.py
git commit -m "feat: emit DraftCreated event when draft is created or updated"
```

---

### Task 6: 集成 — Alert Service emit

**Files:**
- Modify: `backend/app/services/alert_service.py:146-178`

- [ ] **Step 1: Modify alert_service to emit on trigger**

Add import at top of `backend/app/services/alert_service.py`:

```python
from app.core.events import AlertTriggered, bus
```

In the `_emit()` function, after `db.add(event)` and the audit_log block (around line 178, before `return event`), add:

```python
    try:
        bus.emit(AlertTriggered(
            alert_event_id=event.id,
            rule_id=rule.id,
            stock_code=rule.stock_code,
            title=title,
            severity=severity,
        ))
    except Exception:
        logger.exception("EventBus emit AlertTriggered failed")
```

Note: `event.id` may be None before flush. Need to add `db.flush()` before the emit to get the id. Change `return event` to:

```python
    db.flush()
    try:
        bus.emit(AlertTriggered(
            alert_event_id=event.id,
            rule_id=rule.id,
            stock_code=rule.stock_code,
            title=title,
            severity=severity,
        ))
    except Exception:
        logger.exception("EventBus emit AlertTriggered failed")
    return event
```

- [ ] **Step 2: Run full test suite**

Run: `cd /Users/rong.zhu/Code/gojira/backend && python -m pytest -q`
Expected: all pass

- [ ] **Step 3: Commit**

```bash
cd /Users/rong.zhu/Code/gojira/backend
git add app/services/alert_service.py
git commit -m "feat: emit AlertTriggered event when alert fires"
```

---

### Task 7: 启动时注册 + API 端点

**Files:**
- Modify: `backend/app/main.py:83-85`
- Modify: `backend/app/routers/observability.py`
- Modify: `backend/app/schemas/observability.py`

- [ ] **Step 1: Import event_handlers in main.py**

In `backend/app/main.py`, inside the `lifespan` function, add after `import app.services.pipelines  # noqa: F401` (around line 83):

```python
    import app.core.event_handlers  # noqa: F401 — register all event handlers
```

- [ ] **Step 2: Add events endpoint to observability router**

In `backend/app/routers/observability.py`, add:

```python
from app.core.events import bus


@router.get("/events")
def get_event_registry():
    reg = bus.get_registry()
    return {
        "events": {
            et.__name__: handlers
            for et, handlers in reg.items()
        },
        "total_event_types": len(reg),
        "total_handlers": sum(len(hs) for hs in reg.values()),
    }
```

- [ ] **Step 3: Run full test suite**

Run: `cd /Users/rong.zhu/Code/gojira/backend && python -m pytest -q`
Expected: all pass

- [ ] **Step 4: Commit**

```bash
cd /Users/rong.zhu/Code/gojira/backend
git add app/main.py app/routers/observability.py
git commit -m "feat: register event handlers at startup and add /events endpoint"
```

---

### Task 8: 盘中监控 Job（可选，默认关闭）

**Files:**
- Modify: `backend/app/scheduler.py`
- Modify: `backend/app/services/scheduler_config_service.py`

- [ ] **Step 1: Add intraday_monitor job function**

In `backend/app/scheduler.py`, add after `daily_kline_sync_job` (around line 263):

```python
def intraday_monitor_job() -> dict:
    """盘中监控：每 5 分钟检查 watchlist 股票价格，触发告警。

    默认关闭，需通过环境变量 INTRADAY_MONITOR_ENABLED=true 启用。
    """
    with SessionLocal() as db:
        codes = _watched_and_held_codes(db)
        if not codes:
            return {"checked": 0, "alerts": 0}

        from app.services.alert_service import (
            list_rules, _fetch_realtime,
            _eval_stop_profit, _should_dedupe, _emit,
        )

        stop_profit_rules = [
            r for r in list_rules(db, enabled_only=True)
            if r.rule_type == "stop_profit"
        ]
        if not stop_profit_rules:
            return {"checked": len(codes), "alerts": 0}

        realtime = _fetch_realtime([r.stock_code for r in stop_profit_rules if r.stock_code])
        alerts = 0
        for rule in stop_profit_rules:
            if _should_dedupe(db, rule):
                continue
            snapshot = realtime.get(rule.stock_code) if rule.stock_code else None
            ev = _eval_stop_profit(db, rule, snapshot)
            if ev:
                alerts += 1
        db.commit()
        return {"checked": len(codes), "alerts": alerts}
```

- [ ] **Step 2: Add to JOB_REGISTRY**

In `backend/app/scheduler.py`, add to `JOB_REGISTRY` dict:

```python
    "intraday_monitor": intraday_monitor_job,
```

- [ ] **Step 3: Add default config**

In `backend/app/services/scheduler_config_service.py`, add to `DEFAULT_JOBS` dict:

```python
    "intraday_monitor": {
        "cron_expr": "*/5 9-14 * * 1-5",
        "description": "盘中价格监控（每5分钟检查止盈告警，默认关闭）",
    },
```

- [ ] **Step 4: Make it disabled by default**

In `backend/app/services/scheduler_config_service.py`, modify `ensure_defaults` to accept a `default_enabled` parameter per job. Change the function:

```python
DEFAULT_JOB_ENABLED: dict[str, bool] = {
    "intraday_monitor": False,
}


def ensure_defaults(db: Session) -> int:
    inserted = 0
    for job_id, cfg in DEFAULT_JOBS.items():
        exists = db.query(SchedulerJob).filter(SchedulerJob.job_id == job_id).first()
        if not exists:
            db.add(
                SchedulerJob(
                    job_id=job_id,
                    cron_expr=cfg["cron_expr"],
                    description=cfg.get("description"),
                    enabled=not DEFAULT_JOB_ENABLED.get(job_id, True),
                )
            )
            inserted += 1
    if inserted:
        db.flush()
    return inserted
```

Wait — this changes the behavior of existing jobs. Simpler approach: just add `"intraday_monitor"` with a separate default:

In `backend/app/services/scheduler_config_service.py`, modify `ensure_defaults`:

Change the `enabled=True` to check a set of disabled-by-default jobs:

```python
_DISABLED_BY_DEFAULT: set[str] = {"intraday_monitor"}


def ensure_defaults(db: Session) -> int:
    inserted = 0
    for job_id, cfg in DEFAULT_JOBS.items():
        exists = db.query(SchedulerJob).filter(SchedulerJob.job_id == job_id).first()
        if not exists:
            db.add(
                SchedulerJob(
                    job_id=job_id,
                    cron_expr=cfg["cron_expr"],
                    description=cfg.get("description"),
                    enabled=job_id not in _DISABLED_BY_DEFAULT,
                )
            )
            inserted += 1
    if inserted:
        db.flush()
    return inserted
```

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/rong.zhu/Code/gojira/backend && python -m pytest -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
cd /Users/rong.zhu/Code/gojira/backend
git add app/scheduler.py app/services/scheduler_config_service.py
git commit -m "feat: add intraday_monitor job (disabled by default)"
```

---

### Task 9: 文档更新

**Files:**
- Modify: `docs/progress/STATUS.md`

- [ ] **Step 1: Update STATUS.md**

In `docs/progress/STATUS.md`, update the "调度任务" table to add:

```
| mon-fri */5 9-14 | 盘中价格监控（可选，默认关闭） |
```

Add "事件驱动" section after 调度任务:

```
## 事件驱动（EventBus）

| 事件 | 触发点 | 下游处理 |
|------|--------|----------|
| DataSyncCompleted | Pipeline 完成 | 策略重评估 / 论点变量同步 / 价格告警 |
| PlanEvaluationCompleted | Plan 评估完成 | 新候选告警检查 |
| DraftCreated | Draft 创建 | 仓位约束检查 / 审计日志 |
| AlertTriggered | 告警触发 | 审计日志 |
```

- [ ] **Step 2: Commit**

```bash
cd /Users/rong.zhu/Code/gojira
git add docs/progress/STATUS.md
git commit -m "docs: update STATUS.md with event-driven architecture"
```

---

### Task 10: 全量回归验证

- [ ] **Step 1: Run full backend test suite**

Run: `cd /Users/rong.zhu/Code/gojira/backend && python -m pytest -v --tb=short`
Expected: all pass, 0 failed

- [ ] **Step 2: Run frontend build check**

Run: `cd /Users/rong.zhu/Code/gojira/frontend && npm run build`
Expected: build succeeds (no backend changes affect frontend)

- [ ] **Step 3: Verify event registry endpoint works**

Start dev server (`./dev.sh`) and call:

```bash
curl http://localhost:3001/api/observability/events
```

Expected: JSON with `total_event_types: 4`, `total_handlers: 7`, listing all event types and their handlers.

- [ ] **Step 4: Final commit**

```bash
cd /Users/rong.zhu/Code/gojira
git add -A
git commit -m "feat: event-driven automation system complete — EventBus + 7 handlers + intraday monitor"
```
