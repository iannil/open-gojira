# Gojira 第六轮审计修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复第六轮审计发现的 P0×5 + P1×15 问题，按批次优先级递减执行。

**Architecture:** 按问题域分 6 批次修复：Plan DSL 逻辑 → 持仓计算 → 估值逻辑 → 安全 → API 契约 → 架构。每批次独立可测试，完成后运行 `pytest` 验证无回归。

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy / Pydantic v2 / pytest, TypeScript / React 19

---

## Batch 1: Plan DSL AND/OR 逻辑修复 (P0-01, P0-02, P1-03)

### Task 1: 修复 `_strategy_definitely_fails` 感知策略 AND/OR 逻辑

**Files:**
- Modify: `backend/app/services/plan_runner.py:88-101`
- Test: `backend/tests/test_plan_runner.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_plan_runner.py` 中添加（如果文件不存在则创建）:

```python
"""Tests for plan_runner — dual-pass screening AND/OR logic."""

import pytest
from unittest.mock import MagicMock, patch

from app.services.strategy_engine import StockContext, _resolve_field, _evaluate_condition
from app.schemas.strategy import Condition, StrategyRule


def _make_ctx(**overrides) -> StockContext:
    defaults = dict(
        code="000001",
        name="测试股票",
        industry="银行",
        dyr=0.05,
        pe_pct_10y=0.30,
        dividend_sustainability=None,
        ocf_to_ni=None,
    )
    defaults.update(overrides)
    return StockContext(**defaults)


class TestStrategyDefinitelyFails:
    """P0-01: _strategy_definitely_fails must respect strategy AND/OR logic."""

    def test_and_strategy_one_condition_fails_should_eliminate(self):
        """AND strategy: one condition with available data fails → eliminate."""
        from app.services.plan_runner import _strategy_definitely_fails
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="dyr", op=">=", value=0.04),
            Condition(field="pe_pct_10y", op="<=", value=0.50),
        ])
        ctx = _make_ctx(dyr=0.03, pe_pct_10y=0.30)
        # dyr 0.03 < 0.04 fails, pe_pct 0.30 <= 0.50 passes
        # AND: one fail → definitely fails
        assert _strategy_definitely_fails(rule, ctx) is True

    def test_and_strategy_all_conditions_pass_should_not_eliminate(self):
        """AND strategy: all available conditions pass → keep."""
        from app.services.plan_runner import _strategy_definitely_fails
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="dyr", op=">=", value=0.04),
            Condition(field="pe_pct_10y", op="<=", value=0.50),
        ])
        ctx = _make_ctx(dyr=0.05, pe_pct_10y=0.30)
        assert _strategy_definitely_fails(rule, ctx) is False

    def test_or_strategy_one_condition_fails_should_not_eliminate(self):
        """P0-01: OR strategy: one condition fails but another passes → keep."""
        from app.services.plan_runner import _strategy_definitely_fails
        rule = StrategyRule(logic="OR", conditions=[
            Condition(field="dyr", op=">=", value=0.10),
            Condition(field="pe_pct_10y", op="<=", value=0.50),
        ])
        ctx = _make_ctx(dyr=0.04, pe_pct_10y=0.30)
        # dyr 0.04 < 0.10 fails, but pe_pct 0.30 <= 0.50 passes
        # OR: one pass → NOT definitely fails
        assert _strategy_definitely_fails(rule, ctx) is False

    def test_or_strategy_all_conditions_fail_should_eliminate(self):
        """OR strategy: ALL available conditions fail → eliminate."""
        from app.services.plan_runner import _strategy_definitely_fails
        rule = StrategyRule(logic="OR", conditions=[
            Condition(field="dyr", op=">=", value=0.10),
            Condition(field="pe_pct_10y", op="<=", value=0.10),
        ])
        ctx = _make_ctx(dyr=0.04, pe_pct_10y=0.60)
        assert _strategy_definitely_fails(rule, ctx) is True

    def test_or_strategy_unavailable_data_mixed(self):
        """OR strategy: one unavailable, one passes → should NOT eliminate."""
        from app.services.plan_runner import _strategy_definitely_fails
        rule = StrategyRule(logic="OR", conditions=[
            Condition(field="dividend_sustainability", op=">=", value=60),
            Condition(field="dyr", op=">=", value=0.04),
        ])
        ctx = _make_ctx(dividend_sustainability=None, dyr=0.05)
        # dividend_sustainability unavailable, dyr passes
        # OR: one pass → keep
        assert _strategy_definitely_fails(rule, ctx) is False

    def test_or_strategy_all_unavailable_should_not_eliminate(self):
        """OR strategy: all data unavailable → inconclusive, keep for Pass 2."""
        from app.services.plan_runner import _strategy_definitely_fails
        rule = StrategyRule(logic="OR", conditions=[
            Condition(field="dividend_sustainability", op=">=", value=60),
            Condition(field="ocf_to_ni", op=">=", value=0.80),
        ])
        ctx = _make_ctx(dividend_sustainability=None, ocf_to_ni=None)
        # All unavailable → can't determine → keep for Pass 2
        assert _strategy_definitely_fails(rule, ctx) is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/rong.zhu/Code/gojira/backend && source .venv/bin/activate && pytest tests/test_plan_runner.py::TestStrategyDefinitelyFails -v`
Expected: `test_or_strategy_one_condition_fails_should_not_eliminate` FAILS

- [ ] **Step 3: 修复 `_strategy_definitely_fails`**

在 `backend/app/services/plan_runner.py` 中替换 `_strategy_definitely_fails`:

```python
def _strategy_definitely_fails(rule, ctx: StockContext) -> bool:
    """Check if a strategy definitely fails given available context data.

    For AND logic: returns True if any available condition fails (fail-fast).
    For OR logic: returns True only if all available conditions fail.
    Returns False if the outcome is uncertain (all data unavailable for OR).
    """
    available_results = []
    has_unavailable = False

    for cond in rule.conditions:
        actual = resolve_field(ctx, cond.field)
        if actual is None:
            has_unavailable = True
            continue
        cond_result = _evaluate_condition(cond, ctx)
        available_results.append(cond_result.passed)

    if not available_results:
        # No data available → can't determine → keep for Pass 2
        return False

    if rule.logic == "OR":
        # OR: if any available condition passes, strategy may pass
        if any(available_results):
            return False
        # All available fail → definitely fails only if no unavailable fields
        # (unavailable fields might pass in Pass 2)
        return not has_unavailable
    else:
        # AND: if any available condition fails, strategy definitely fails
        return not all(available_results)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/rong.zhu/Code/gojira/backend && pytest tests/test_plan_runner.py::TestStrategyDefinitelyFails -v`
Expected: ALL PASS

- [ ] **Step 5: 运行全量测试无回归**

Run: `cd /Users/rong.zhu/Code/gojira/backend && pytest tests/test_strategy_engine.py tests/test_plan_runner.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/plan_runner.py backend/tests/test_plan_runner.py
git commit -m "fix: respect AND/OR logic in _strategy_definitely_fails for Plan DSL Pass 1 screening (P0-01)"
```


### Task 2: 修复 Pass 1 筛选感知 plan composition AND/OR 逻辑

**Files:**
- Modify: `backend/app/services/plan_runner.py:274-293`
- Test: `backend/tests/test_plan_runner.py`

- [ ] **Step 1: 写失败测试**

```python
class TestPass1CompositionLogic:
    """P0-02: Pass 1 must respect plan-level composition AND/OR."""

    def test_or_composition_keeps_stock_if_any_strategy_survives(self):
        """OR composition: one strategy fails, another passes → stock survives."""
        from app.services.plan_runner import _strategy_definitely_fails
        # Simulate: strategy 1 fails (dyr too low), strategy 2 passes (pe good)
        rule1 = StrategyRule(logic="AND", conditions=[
            Condition(field="dyr", op=">=", value=0.10),
        ])
        rule2 = StrategyRule(logic="AND", conditions=[
            Condition(field="pe_pct_10y", op="<=", value=0.50),
        ])
        ctx = _make_ctx(dyr=0.04, pe_pct_10y=0.30)

        # OR composition: strategy 1 definitely fails, strategy 2 does not
        assert _strategy_definitely_fails(rule1, ctx) is True
        assert _strategy_definitely_fails(rule2, ctx) is False
        # The calling code must check: for OR, only eliminate if ALL strategies fail

    def test_and_composition_eliminated_if_any_strategy_fails(self):
        """AND composition: any strategy fails → stock eliminated."""
        from app.services.plan_runner import _strategy_definitely_fails
        rule1 = StrategyRule(logic="AND", conditions=[
            Condition(field="dyr", op=">=", value=0.10),
        ])
        ctx = _make_ctx(dyr=0.04)

        assert _strategy_definitely_fails(rule1, ctx) is True
        # AND: any fail → eliminated
```

- [ ] **Step 2: 运行测试确认行为**

Run: `cd /Users/rong.zhu/Code/gojira/backend && pytest tests/test_plan_runner.py::TestPass1CompositionLogic -v`

- [ ] **Step 3: 修复 Pass 1 筛选逻辑**

在 `backend/app/services/plan_runner.py` 中替换 Pass 1 筛选（约 line 274-293）:

```python
        # Pass 1: Fail-fast screening — eliminate stocks that definitely fail
        surviving_codes = []
        for code in codes:
            ctx = lightweight_contexts.get(code)
            if ctx is None:
                ctx = StockContext(code=code)

            if comp.logic == "OR":
                # OR composition: only eliminate if ALL strategies definitely fail
                eliminated = all(
                    _strategy_definitely_fails(
                        StrategyRule.model_validate_json(s.rule_json), ctx
                    )
                    for s in strategies
                )
            else:
                # AND composition: eliminate if ANY strategy definitely fails
                eliminated = False
                for s in strategies:
                    rule = StrategyRule.model_validate_json(s.rule_json)
                    if _strategy_definitely_fails(rule, ctx):
                        eliminated = True
                        break

            if not eliminated:
                surviving_codes.append(code)
```

- [ ] **Step 4: 运行全量测试**

Run: `cd /Users/rong.zhu/Code/gojira/backend && pytest tests/test_plan_runner.py tests/test_strategy_engine.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/plan_runner.py
git commit -m "fix: respect plan composition AND/OR in Pass 1 screening (P0-02)"
```

---

## Batch 2: 持仓权重与计算修复 (P0-03, P0-04, P0-05, P1-04)

### Task 3: 统一 Universe 与 Portfolio 权重计算基数 + 修复 total_pnl 不可用时为 None

**Files:**
- Modify: `backend/app/routers/stocks.py:89-108`
- Modify: `backend/app/services/holding_service.py:368-374`
- Test: `backend/tests/test_holding_service.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_holding_service.py` 中添加:

```python
class TestPortfolioSummaryPnl:
    """P0-04: total_pnl should be None when all prices unavailable."""

    def test_total_pnl_none_when_no_prices(self, db):
        """When price fetch fails for all holdings, total_pnl should be None, not 0."""
        from app.services import holding_service
        from app.models.holding import Holding
        from app.models.stock import Stock

        stock = Stock(code="999999", name="测试", industry="测试")
        db.add(stock)
        db.flush()

        h = Holding(stock_code="999999", buy_price=10.0, quantity=100)
        db.add(h)
        db.flush()

        # Mock price fetch to return None
        with patch.object(holding_service, "_get_cached_price", return_value=None):
            summary = holding_service.get_portfolio_summary(db)

        assert summary["total_pnl"] is None
        assert summary["total_pnl_pct"] is None

    def test_total_pnl_calculated_when_prices_available(self, db):
        """When price fetch succeeds, total_pnl should be calculated normally."""
        from app.services import holding_service
        from app.models.holding import Holding
        from app.models.stock import Stock

        stock = Stock(code="999998", name="测试2", industry="测试")
        db.add(stock)
        db.flush()

        h = Holding(stock_code="999998", buy_price=10.0, quantity=100)
        db.add(h)
        db.flush()

        with patch.object(holding_service, "_get_cached_price", return_value=12.0):
            summary = holding_service.get_portfolio_summary(db)

        assert summary["total_pnl"] is not None
        assert summary["total_pnl"] == pytest.approx(200.0)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/rong.zhu/Code/gojira/backend && pytest tests/test_holding_service.py::TestPortfolioSummaryPnl -v`
Expected: `test_total_pnl_none_when_no_prices` FAILS (total_pnl is 0 not None)

- [ ] **Step 3: 修复 get_portfolio_summary 中的 total_pnl 逻辑**

在 `backend/app/services/holding_service.py` 中替换 line 368-374:

```python
    total_cost = sum(h["buy_price"] * h["quantity"] for h in holding_dicts)
    # Track whether we have any real prices (vs cost-basis fallback)
    has_any_price = any(h["current_value"] is not None for h in holding_dicts)
    total_value = sum(
        h["current_value"] if h["current_value"] is not None else h["buy_price"] * h["quantity"]
        for h in holding_dicts
    )
    if has_any_price:
        total_pnl = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost) * 100 if total_cost != 0 else 0.0
    else:
        total_pnl = None
        total_pnl_pct = None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/rong.zhu/Code/gojira/backend && pytest tests/test_holding_service.py::TestPortfolioSummaryPnl -v`

- [ ] **Step 5: 修复 Universe 权重计算使用市值基数**

在 `backend/app/routers/stocks.py` 中替换 line 89-108 的权重计算部分:

```python
    # Weight calculation — use current market value (consistent with portfolio summary)
    from app.services.holding_service import _get_cached_price
    all_holdings = db.query(Holding).filter(Holding.sell_date.is_(None)).all()
    holdings_by_code: dict[str, list] = {}
    for h in all_holdings:
        holdings_by_code.setdefault(h.stock_code, []).append(h)

    total_value = 0.0
    holding_values: dict[str, float] = {}
    for code, hs in holdings_by_code.items():
        price = _get_cached_price(code)
        val = sum(
            (price * h.quantity) if price is not None else (h.buy_price * h.quantity)
            for h in hs
        )
        holding_values[code] = val
        total_value += val
    total_value = total_value or 1.0
```

然后修改 per-stock weight 计算:

```python
        weight = None
        if is_held:
            weight = holding_values.get(code, 0) / total_value * 100
```

并删除原来的 per-stock Holdings 查询 (`db.query(Holding).filter(Holding.stock_code == code...)`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/holding_service.py backend/app/routers/stocks.py backend/tests/test_holding_service.py
git commit -m "fix: unify weight calculation base (market value) and set total_pnl=None when prices unavailable (P0-03, P0-04)"
```

### Task 4: 修复行业权重前检查基数一致性 (P0-05)

**Files:**
- Modify: `backend/app/services/holding_service.py:121-152`

- [ ] **Step 1: 修复 `_industry_breach_after_buy`**

当前 `_industry_breach_after_buy` 在 line 147 用 `h.get("current_value")` 计算，与 portfolio summary 的逻辑一致。但 `base_value = summary["total_value"] + new_cost` 中的 `summary["total_value"]` 现在已统一用市值。所以前检查和后警告的基数已通过 Task 3 的修复对齐。

验证: 运行 `pytest tests/test_holding_service.py -v`

- [ ] **Step 2: Commit**

```bash
git commit -m "fix: industry weight pre-check now uses same market-value base as portfolio summary (P0-05, fixed by P0-03)"
```

### Task 5: 添加年化收益率上限 (P1-04)

**Files:**
- Modify: `backend/app/services/holding_service.py:267-274`

- [ ] **Step 1: 修复年化收益率极端值**

在 `backend/app/services/holding_service.py` line 274 后添加上限:

```python
    # Annualized return — geometric, based on hold days. None if missing inputs.
    annualized_return_pct: Optional[float] = None
    if holding.buy_date and current_value is not None and cost > 0:
        days = (date.today() - holding.buy_date).days
        if days >= 30:
            ratio = current_value / cost
            if ratio > 0:
                raw = (ratio ** (365.0 / days) - 1) * 100
                annualized_return_pct = max(-100.0, min(raw, 500.0))
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/holding_service.py
git commit -m "fix: clamp annualized return to [-100%, 500%] to avoid extreme values (P1-04)"
```

---

## Batch 3: 估值与业务逻辑修复 (P1-05, P1-07, P1-08)

### Task 6: 修复分红可持续性全零返回"健康" (P1-07)

**Files:**
- Modify: `backend/app/services/valuation_service.py:176-211`
- Test: `backend/tests/test_valuation_service.py`

- [ ] **Step 1: 写失败测试**

```python
class TestDividendSustainability:
    """P1-07: All-zero params should not return 'healthy'."""

    def test_all_zero_returns_data_unavailable(self):
        from app.services.valuation_service import check_dividend_sustainability
        result = check_dividend_sustainability(0, 0, 0)
        assert result["status"] != "healthy"
        assert result["status"] == "data_unavailable"

    def test_normal_healthy_case(self):
        from app.services.valuation_service import check_dividend_sustainability
        result = check_dividend_sustainability(100, 50, 20)
        assert result["status"] == "healthy"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/rong.zhu/Code/gojira/backend && pytest tests/test_valuation_service.py::TestDividendSustainability -v`

- [ ] **Step 3: 修复**

在 `backend/app/services/valuation_service.py` 的 `check_dividend_sustainability` 函数开头添加:

```python
def check_dividend_sustainability(
    operating_cash_flow: float,
    net_profit: float,
    dividends_paid: float,
) -> dict:
    if operating_cash_flow == 0 and net_profit == 0 and dividends_paid == 0:
        return {
            "status": "data_unavailable",
            "message": "三项指标均为 0，数据不可用",
        }
    # ... rest of function unchanged
```

- [ ] **Step 4: 运行测试 + Commit**

```bash
pytest tests/test_valuation_service.py -v
git add backend/app/services/valuation_service.py backend/tests/test_valuation_service.py
git commit -m "fix: return data_unavailable when all dividend sustainability params are zero (P1-07)"
```

### Task 7: 修复负 payout_avg 不截断 (P1-08)

**Files:**
- Modify: `backend/app/services/valuation_service.py:142-143`

- [ ] **Step 1: 修复**

在 `backend/app/services/valuation_service.py` line 143 修改:

```python
    # Cap payout at [0, 1.0] to avoid unrealistic forward DYR
    payout_capped = max(0.0, min(payout_avg, 1.0)) if payout_avg is not None else None
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/valuation_service.py
git commit -m "fix: clamp negative payout_avg to 0 before forward DYR calculation (P1-08)"
```

---

## Batch 4: 安全修复 (P1-01, P1-02)

### Task 8: 修复 LIKE 通配符注入 (P1-01)

**Files:**
- Modify: `backend/app/routers/stocks.py:149-151`

- [ ] **Step 1: 修复**

在 `backend/app/routers/stocks.py` 的 `get_full_universe` 函数中，替换 line 149-151:

```python
    if keyword:
        escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        kw = f"%{escaped}%"
        q = q.filter(
            (Stock.code.like(kw, escape="\\")) | (Stock.name.like(kw, escape="\\"))
        )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/routers/stocks.py
git commit -m "fix: escape LIKE wildcards in stock search keyword (P1-01)"
```

### Task 9: 添加 Scheduler 手动触发并发保护 (P1-02)

**Files:**
- Modify: `backend/app/scheduler.py:599-633`

- [ ] **Step 1: 添加并发保护**

在 `backend/app/scheduler.py` 文件顶部（import 区域后）添加:

```python
_running_jobs_lock = threading.Lock()
_running_jobs: set[str] = set()
```

修改 `run_job_now` 函数:

```python
def run_job_now(job_id: str) -> dict:
    """Run a registered job immediately. Raises if already running."""
    with _running_jobs_lock:
        if job_id in _running_jobs:
            raise ValueError(f"Job {job_id} is already running")
        _running_jobs.add(job_id)
    try:
        func = JOB_REGISTRY.get(job_id)
        if not func:
            raise KeyError(f"Unknown job: {job_id}")
        db = SessionLocal()
        try:
            exec_ = record_start(db, job_id)
            db.commit()
            result = func()
            record_finish(db, exec_.id, status="success")
            db.commit()
            return {"status": "ok", "job_id": job_id}
        except Exception as e:
            record_finish(db, exec_.id if 'exec_' in dir() else None, status="error", error=str(e))
            db.commit()
            raise
        finally:
            db.close()
    finally:
        with _running_jobs_lock:
            _running_jobs.discard(job_id)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/scheduler.py
git commit -m "fix: add concurrency protection to scheduler manual job triggers (P1-02)"
```

---

## Batch 5: API 契约修复 (P1-12, P1-13)

### Task 10: 修复 updateThesisVariables 返回类型 (P1-12)

**Files:**
- Modify: `frontend/src/api/client.ts:290-295`

- [ ] **Step 1: 修复前端返回类型**

在 `frontend/src/api/client.ts` 中替换 line 290-295:

```typescript
export async function updateThesisVariables(
  code: string,
  variables: ThesisVariable[],
): Promise<StockResponse> {
  const res = await apiClient.put<StockResponse>(`/stocks/${code}/thesis-variables`, variables);
  return res.data;
}
```

- [ ] **Step 2: 验证前端构建**

Run: `cd /Users/rong.zhu/Code/gojira/frontend && npm run build`
Expected: 成功

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "fix: updateThesisVariables returns StockResponse instead of void (P1-12)"
```

### Task 11: 修复 CockpitDraft 缺失 source 字段 (P1-13)

**Files:**
- Modify: `backend/app/services/cockpit_service.py:63-76`

- [ ] **Step 1: 修复序列化**

在 `backend/app/services/cockpit_service.py` 的 `_serialize_draft` 函数中添加 `source` 字段:

```python
def _serialize_draft(d) -> dict:
    return {
        "id": d.id,
        "plan_id": d.plan_id,
        "code": d.code,
        "side": d.side,
        "status": d.status,
        "step_kind": d.step_kind,
        "step_index": d.step_index,
        "add_pct": d.add_pct,
        "reduce_pct_of_position": d.reduce_pct_of_position,
        "reason": d.reason,
        "source": getattr(d, "source", None),
        "triggered_at": str(d.triggered_at) if d.triggered_at else None,
    }
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/cockpit_service.py
git commit -m "fix: add missing source field to CockpitDraft serialization (P1-13)"
```

---

## Batch 6: 架构修复 (P1-14, P1-15)

### Task 12: 引入自定义业务异常替代 Service 层 HTTPException (P1-14)

**Files:**
- Create: `backend/app/core/exceptions.py`
- Modify: `backend/app/services/holding_service.py` (示例修复)
- Modify: `backend/app/routers/portfolio.py` (示例捕获)

- [ ] **Step 1: 创建自定义异常**

创建 `backend/app/core/exceptions.py`:

```python
"""Domain exceptions for the service layer.

Services raise these; routers catch and convert to HTTPException.
"""


class EntityNotFound(Exception):
    """Raised when a requested entity does not exist."""
    def __init__(self, entity_type: str, identifier: str | int):
        self.entity_type = entity_type
        self.identifier = identifier
        super().__init__(f"{entity_type} {identifier} not found")


class DuplicateEntity(Exception):
    """Raised when creating an entity that already exists."""
    def __init__(self, entity_type: str, identifier: str):
        self.entity_type = entity_type
        self.identifier = identifier
        super().__init__(f"{entity_type} {identifier!r} already exists")


class BusinessRuleViolation(Exception):
    """Raised when a business rule would be violated."""
    def __init__(self, message: str):
        super().__init__(message)


class InvalidState(Exception):
    """Raised when an operation is invalid for the current state."""
    def __init__(self, message: str):
        super().__init__(message)
```

- [ ] **Step 2: 添加全局异常处理器**

在 `backend/app/main.py` 的全局异常处理器区域添加:

```python
from app.core.exceptions import EntityNotFound, DuplicateEntity, BusinessRuleViolation, InvalidState

@app.exception_handler(EntityNotFound)
async def entity_not_found_handler(request, exc):
    return JSONResponse(status_code=404, content={"detail": str(exc)})

@app.exception_handler(DuplicateEntity)
async def duplicate_entity_handler(request, exc):
    return JSONResponse(status_code=409, content={"detail": str(exc)})

@app.exception_handler(BusinessRuleViolation)
async def business_rule_handler(request, exc):
    return JSONResponse(status_code=409, content={"detail": str(exc)})

@app.exception_handler(InvalidState)
async def invalid_state_handler(request, exc):
    return JSONResponse(status_code=409, content={"detail": str(exc)})
```

- [ ] **Step 3: 修复 holding_service.py**

替换 `backend/app/services/holding_service.py` 中的 HTTPException:

```python
from app.core.exceptions import EntityNotFound, BusinessRuleViolation

# line 78:
raise EntityNotFound("Stock", data.get("stock_code"))
# line 87-94:
raise BusinessRuleViolation(
    f"买入后{breach['industry']}行业仓位 {breach['weight_pct']:.1f}% "
    f"将超过 {MAX_INDUSTRY_WEIGHT}% 上限，请调整数量或换行业；"
    "如确需强制买入，请在请求中传 force=true"
)
```

- [ ] **Step 4: 运行测试 + Commit**

```bash
pytest tests/test_holding_service.py -v
git add backend/app/core/exceptions.py backend/app/main.py backend/app/services/holding_service.py
git commit -m "refactor: introduce domain exceptions to replace HTTPException in service layer (P1-14)"
```

### Task 13: 移除 Service 层手动 db.commit() (P1-15)

**Files:**
- Modify: `backend/app/services/holding_service.py` (示例)
- Modify: 其他 services 逐步迁移

> **注意**: 这是一个大规模重构，建议分多次 commit 逐步完成。此 task 仅修复 `holding_service.py` 作为范例。

- [ ] **Step 1: 移除 holding_service.py 中的手动 commit**

删除 `holding_service.py` 中所有 `db.commit()` 调用:
- line 98, 117 (`create_holding`)
- line 165 (`update_holding`)
- line 190 (`delete_holding`)
- line 211, 233 (`sell_holding`)
- line 305 (`_get_or_init_settings`)

保留 `_sync_stop_profit_rules` 和 `audit_log_service.write` 的调用，因为它们内部有自己的 session 管理。

- [ ] **Step 2: 运行测试验证**

Run: `cd /Users/rong.zhu/Code/gojira/backend && pytest tests/test_holding_service.py -v`
Expected: PASS (get_db 自动 commit)

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/holding_service.py
git commit -m "refactor: remove manual db.commit() from holding_service, rely on get_db auto-commit (P1-15)"
```

---

## 验证清单

每个 Batch 完成后:

- [ ] `cd backend && pytest` — 全量测试通过
- [ ] `cd frontend && npm run build` — 前端构建成功
- [ ] `cd frontend && npm run lint` — 无新增 lint 错误

全部完成后:

- [ ] 运行 `pytest` 确认测试总数不变或增加
- [ ] 手动启动 `./dev.sh` 验证 Cockpit、Universe、Plans 页面
- [ ] 更新 `docs/progress/2026-06-11-audit-round6.md` 标记已修复项
