# 事件驱动自动化系统设计

> 日期：2026-06-10
> 状态：待评审

## 背景

当前 Gojira 所有自动化任务由 APScheduler 定时驱动，存在两个结构性缺陷：

1. **无数据联动**：pipeline 完成后不会自动触发下游处理（如估值更新后不会自动重评估策略）
2. **无实时响应**：告警评估固定在 17:30，盘中异动无法及时发现

本设计引入进程内 EventBus，与 Scheduler 互补，实现"定时拉数据 + 事件驱动响应"的双层自动化架构。

## 架构决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 事件传递 | 进程内同步调用 | 零外部依赖，单进程性能足够（A股 5000+ 量级） |
| 事件持久化 | 不持久化 | handler 失败仅记录日志，不阻断发布者；定时任务会自然重跑 |
| 并发模型 | 同步（线程安全） | 现有 service 层全是同步 SQLAlchemy，保持一致 |
| 通知方式 | 仅系统内 | 记录 alert_event + audit_log，用户打开系统时可见 |
| 外部依赖 | 无新增 | 不引入 Redis/Celery/RQ |

## 核心组件

### EventBus（`app/core/events.py`）

```python
class EventBus:
    """进程内同步事件总线。"""

    def subscribe(event_type: type[BaseEvent], handler: Callable) -> None: ...
    def emit(event: BaseEvent) -> None: ...
    def get_registry() -> dict[type, list[str]]: ...  # 可观测性

bus = EventBus()  # 模块级单例
```

- `emit()` 同步调用所有注册的 handler，按注册顺序执行
- 单个 handler 抛异常时捕获并记录日志，不阻断后续 handler
- 每次调用自动关联 `trace_id`（复用 observability 模块的 `_generate_id()`）
- 线程安全：内部用 `dict[type, list]` 存储，启动时注册完毕后只读

### BaseEvent（`app/core/events.py`）

```python
class BaseEvent(BaseModel):
    """所有事件的基类。"""
    event_id: str = Field(default_factory=lambda: _generate_id())
    trace_id: str = Field(default_factory=lambda: _obs_get_trace_id() or _generate_id())
    timestamp: datetime = Field(default_factory=utcnow)
```

### 事件类型

#### 数据变更联动

```python
class DataSyncCompleted(BaseEvent):
    pipeline_type: str          # "valuations" | "financials" | "klines" | "dividends"
    stock_codes: list[str]      # 本次同步涉及的股票代码
    run_id: str                 # pipeline run ID
    status: str                 # "success" | "partial" | "failed"
    completed_items: int
    failed_items: int
```

#### 业务流程编排

```python
class PlanEvaluationCompleted(BaseEvent):
    plan_id: int
    plan_slug: str
    scanned: int
    passed: int
    drafts_emitted: int
    errors: int

class DraftCreated(BaseEvent):
    draft_id: int
    stock_code: str
    direction: str              # "buy" | "sell"
    plan_id: int | None
    quantity: float | None
    price: float | None

class AlertTriggered(BaseEvent):
    alert_event_id: int
    rule_id: int
    stock_code: str | None
    title: str
    severity: str               # "info" | "warning" | "alert"
```

### Handler 注册（`app/core/event_handlers.py`）

```python
from app.core.events import bus, DataSyncCompleted, PlanEvaluationCompleted, DraftCreated, AlertTriggered

# ── 数据变更联动 ──

@bus.subscribe(DataSyncCompleted)
def on_valuation_sync_reassess(event: DataSyncCompleted) -> None:
    """估值同步完成 → 重评估 watchlist 股票的策略。"""
    if event.pipeline_type != "valuations" or event.status == "failed":
        return
    # 调用 strategy_engine 批量重评估 event.stock_codes 中的 watchlist 股票

@bus.subscribe(DataSyncCompleted)
def on_financials_sync_thesis_vars(event: DataSyncCompleted) -> None:
    """财报同步完成 → 同步论点变量。"""
    if event.pipeline_type != "financials" or event.status == "failed":
        return
    # 调用 thesis_variable_sync_service.sync_for_codes()

@bus.subscribe(DataSyncCompleted)
def on_kline_sync_price_alert(event: DataSyncCompleted) -> None:
    """K线同步完成 → 检查价格告警。"""
    if event.pipeline_type != "klines" or event.status == "failed":
        return
    # 调用 alert_service.evaluate_rules_for_codes()

# ── 业务流程编排 ──

@bus.subscribe(DraftCreated)
def on_draft_check_position(event: DraftCreated) -> None:
    """Draft 创建 → 检查仓位约束。"""
    # 调用 position_advisor_service 检查

@bus.subscribe(DraftCreated)
def on_draft_audit_log(event: DraftCreated) -> None:
    """Draft 创建 → 记录审计日志。"""
    # 写入 audit_log

@bus.subscribe(AlertTriggered)
def on_alert_audit_log(event: AlertTriggered) -> None:
    """告警触发 → 记录审计日志。"""
    # 写入 audit_log

# ── Plan 完成后检查告警 ──

@bus.subscribe(PlanEvaluationCompleted)
def on_plan_completed_check_alerts(event: PlanEvaluationCompleted) -> None:
    """Plan 评估完成 → 检查新候选是否触发告警规则。"""
    # 对新进入候选池的股票评估告警规则
```

## 集成点

### 1. Pipeline 完成时 emit（`app/services/pipelines/manager.py`）

在 `_execute_with_db` 方法末尾，pipeline 成功后 emit：

```python
from app.core.events import bus, DataSyncCompleted

# 在 pipeline 完成后（run.status 设为成功之后）
bus.emit(DataSyncCompleted(
    pipeline_type=pipeline_type,
    stock_codes=stock_codes,
    run_id=run_id,
    status=run.status,
    completed_items=result.completed_items,
    failed_items=result.failed_items,
))
```

### 2. Plan runner 完成时 emit（`app/services/plan_runner.py`）

在 `run_all_active` 返回前，对每个 plan result emit：

```python
from app.core.events import bus, PlanEvaluationCompleted

bus.emit(PlanEvaluationCompleted(
    plan_id=result.plan_id,
    plan_slug=result.plan_slug,
    scanned=result.scanned,
    passed=result.passed,
    drafts_emitted=result.drafts_emitted,
    errors=len(result.errors),
))
```

### 3. Draft 创建时 emit（`app/services/draft_service.py`）

在创建 Draft 记录并 commit 后 emit：

```python
from app.core.events import bus, DraftCreated

bus.emit(DraftCreated(
    draft_id=draft.id,
    stock_code=draft.stock_code,
    direction=draft.direction,
    plan_id=draft.plan_id,
    quantity=draft.quantity,
    price=draft.price,
))
```

### 4. 告警触发时 emit（`app/services/alert_service.py`）

在 `_emit` 函数创建 alert_event 后 emit：

```python
from app.core.events import bus, AlertTriggered

bus.emit(AlertTriggered(
    alert_event_id=event.id,
    rule_id=rule.id,
    stock_code=rule.stock_code,
    title=title,
    severity=severity,
))
```

### 5. Handler 启动时注册（`app/main.py`）

在 lifespan 中 `start_scheduler()` 之前 import：

```python
import app.core.event_handlers  # noqa: F401 — 注册所有事件处理器
```

### 6. 盘中监控 job（`app/scheduler.py`，可选）

新增 `intraday_monitor` 定时任务，盘中每 5 分钟检查 watchlist 股票价格：

```python
JOB_REGISTRY["intraday_monitor"] = intraday_monitor_job
# cron: mon-fri 9:35-14:55 */5
```

- 仅当 `INTRADAY_MONITOR_ENABLED=true` 时启用，默认关闭
- 拉取 watchlist 股票实时价格，与告警阈值对比
- 触及阈值时 emit `AlertTriggered`

## 与 Scheduler 的关系

```
Scheduler（定时拉数据）          EventBus（数据到达后响应）
────────────────────          ────────────────────────
17:00 估值快照 ─────────────→ DataSyncCompleted → 重评估策略
17:15 K线同步  ─────────────→ DataSyncCompleted → 检查价格告警
17:45 Plan评估 ─────────────→ PlanEvaluationCompleted → 检查新候选告警
                               DraftCreated → 仓位检查 + 审计日志
                               AlertTriggered → 审计日志
9:35-14:55 盘中监控（可选） ─→ AlertTriggered（实时）
```

两者互补，不替代。

## 可观测性

- EventBus 内部每次 `emit` 记录结构化日志：事件类型、handler 数量、各 handler 执行耗时
- Handler 异常不阻断，记录 `EventBus_Handler_Error` 日志（含 trace_id、event_type、handler 名、异常栈）
- `GET /api/observability/events` 可查看事件注册表和最近触发记录

## 不做的事

- **不做事件持久化**：handler 失败不重试，下次定时任务会自然覆盖
- **不做跨进程通信**：当前单进程足够
- **不做外部通知**：仅系统内 alert_event + audit_log
- **不做事件回溯**：不需要 event sourcing

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `app/core/events.py` | 新增 | EventBus + BaseEvent + 4 个事件类型 |
| `app/core/event_handlers.py` | 新增 | 所有 handler 注册 |
| `app/services/pipelines/manager.py` | 修改 | pipeline 完成后 emit（+5 行） |
| `app/services/plan_runner.py` | 修改 | plan 完成后 emit（+5 行） |
| `app/services/draft_service.py` | 修改 | draft 创建后 emit（+5 行） |
| `app/services/alert_service.py` | 修改 | 告警触发后 emit（+5 行） |
| `app/main.py` | 修改 | import event_handlers（+1 行） |
| `app/scheduler.py` | 修改 | 新增 intraday_monitor job（可选） |
| `app/models/scheduler_config.py` | 修改 | 新增 intraday_monitor 默认配置 |
| 测试文件 | 新增 | `tests/test_event_bus.py` |
