# Phase 2 #9 阶段 B — Thesis Monitor 接入 设计规格

> **日期**: 2026-06-16
> **状态**: v2 已确认 (二次 grill-me 会话更新,代码下次实施)
> **关联**: `docs/reference/specs/2026-06-14-serenity-skill-integration.md` Q19 | Phase 2 #9 阶段 A (`docs/progress/STATUS.md` P1-1 已 ship)

## v2 更新摘要 (2026-06-16 二次 grill)

二次 grill-me 会话发现 14 项修正(详见下方各 Q 章节内的"v2 更新"块),主要是:

1. **Q1 — schema 统一**: `thesis_variables_json` 当前 3 套不兼容 schema,标准化为 monitor schema + 修 `sync_stock` 字段名
2. **Q4(翻转)— 双源不复制**: `research_claim_variables` 表与 `thesis_variables_json` 各为真相源,monitor 跑两个 check 函数;原 Q4-A"approve 时复制"作废
3. **Q3 数据源 — 加 NIM 列**: `FinancialStatement` 加 `net_interest_margin` 列 + pipeline 持久化(`financial_pipeline.py` 已在拉)
4. **新字段 `breach_when`**: 机械对齐 signal 文本比较符(`<` → `lt`),消除 direction 语义翻转错误
5. **window_periods 多期检查**: v1 实现真多期检查,非"单点延后"
6. **propose 业务级 dedup + DB 唯一约束**: 跨 run 同 signal 不重复提议
7. **过滤 open holdings**: `check_claim_variables` 跟 `check_held_stocks` 对称,卖出即静默
8. **per-var try/except 隔离**: 单 fetch 失败不影响其它 var
9. **独立 thesis_evaluation_job + last_alerted_at dedup**: 不寄生 `alert_evaluation_job`,7 天窗口
10. **audit + EventBus + notification 三处落地**: 跟 CLAUDE.md 一致
11. **LLM 失败 audit + Cockpit red badge**: 失败可见
12. **PATCH endpoint**: active var 可编辑
13. **TanStack 30s polling**: 不引入 SSE
14. **migration 命名 s5_3_**: 接现有 s5_1 / s5_2 链

工作量从 ~7 小时调到 **~10 小时**。Q4 翻转 + Q3 加列 + 多期检查 + 独立 job + 新 endpoint 是主要增量。

## 背景

Phase 2 #9 阶段 A (2026-06-16 ship) 让 serenity LLM 输出 structured claims,每条带 `signal` 字段 (e.g. "净息差<1.3%持续两个季度")。signal 是天然的 metric key,但当前只用于 UI 展示。

阶段 B 把 signal 字段接入 `thesis_monitor_service`,实现"失败条件真实告警"—— 这是 serenity 模块的核心用户价值,invest3 "失败预警" 闭环。

本规格定义 14 个核心决策(v2),实施工作量 ~10 小时。

## 决策汇总

### v1 决策 (一轮 grill)

| # | 决策 | 选择 | 关键约束 |
|---|---|---|---|
| Q1 | monitor 范围 | B 仅 stock-level (持仓交集) | 数据源可控 (Lixinger),告警精准 |
| Q2 | claim → variable 转换路径 | B 半自动 LLM 提议 + 人工 review | 误报风险低,跟阶段 A 一致 |
| Q3 | 数据源映射策略 | A LLM 强制从 Lixinger shortlist 选 | 避免无数据源 claim 提议,UI 不过载 |
| Q5 | 触发流程 | C 半自动 (EventBus 自动提议 + 人工 review) | 跟 Q2 一致 |
| Q7 | UI 入口 | A StockDetail 提议区 + Cockpit 计数 badge | 持仓 context 完整,IA 不动 |
| Q8 | 本轮范围 | A spec-only,代码下次实施 | 跟 Phase 2 #10 模式一致 |

### v2 决策 (二轮 grill,2026-06-16)

| # | 决策 | 选择 | 关键约束 |
|---|---|---|---|
| Q1' | `thesis_variables_json` schema 统一 | A 标准化为 monitor schema + 修 sync | 3 套 schema 并存导致 monitor 哑火 |
| Q3' | `financial:NIM` 数据源 | A FinancialStatement 加 net_interest_margin 列 + pipeline 持久化 | 列不存在但 pipeline 已在拉数据 |
| Q4' | 持久化结构 (翻转 Q4-A) | C 双源不复制:research_claim_variables 与 thesis_variables_json 各为真相源 | 避免两 writer 写同一 JSON 的混乱 |
| Q-new | direction 语义防错 | 加 `breach_when: "lt" \| "gt"` 机械字段,字面对齐 signal 文本比较符 | LLM 易把 `<` 翻转成 direction=below 导致反向告警 |
| Q-new | window_periods 多期检查 | A v1 即实现真多期 (拉过去 N 期连续 breach) | signal 文本"持续两季"是 invest3 高频句式 |
| Q-new | propose 去重 | 业务级 dedup (stock+variable+source, status IN proposed/active) + DB 唯一约束 (research_claim_id, stock_code, variable_name) | 跨 run / 同 claim 重复触发都覆盖 |
| Q-new | 持仓过滤 | check_claim_variables INNER JOIN holdings WHERE sell_date IS NULL | 卖出即静默,跟 check_held_stocks 对称 |
| Q-new | fetch 失败隔离 | per-var try/except + 结构化日志 + summary 报 checked/breached/failed | 单 source 失败不影响整批 |
| Q6' | schedule + alert 通道 | A2 独立 `thesis_evaluation_job` (17:30) + B1 last_alerted_at 7 天 dedup | scheduler 当前不调 check_held_stocks,需新 wiring;复用 NotificationChannel |
| Q-new | 告警落地 | A 三处:audit_log (同步) + EventBus ThesisAlertTriggered + notification_service.send | 跟 CLAUDE.md audit / EventBus 约定一致 |
| Q-new | LLM 失败 UX | A audit_log (proposed/failed) + Cockpit red/yellow badge | 失败必须可见,GLM 偶发 hang |
| Q-new | active var 编辑 | A PATCH /api/research/claim-variables/{id} + audit_log before/after | reject 重 propose 被 dedup 阻塞,需直接编辑路径 |
| Q-new | Cockpit badge 刷新 | A TanStack useQuery refetchInterval=30s | 项目已用 TanStack,无 SSE 基础设施 |
| Q-new | migration 命名 | `s5_3_research_claim_variables.py` + `s5_4_net_interest_margin.py` (或合并) | 接 s5_1 / s5_2 链 |

## 数据流

```
serenity Run completed (EventBus: ResearchRunCompleted)
  ↓
handler: thesis_variable_proposal_service.propose_for_run(run_id)
  ↓
LLM 二次调用:
  - 拿 research_claims (claim.signal + claim.stock_codes)
  - prompt 含 Lixinger 数据源 shortlist (强制选)
  - 输出 list[{claim_id, stock_code, variable_name, threshold_critical,
              breach_when, source, window_periods, unit}]
                ↑↑↑
              v2: breach_when ("lt"|"gt") 替代 direction,字面对齐 signal 文本比较符
  ↓
propose 前业务级 dedup:
  SELECT WHERE stock_code=? AND variable_name=? AND source=? AND status IN ('proposed','active')
  → 已存在则 skip (Q-new v2)
  ↓
落 research_claim_variables (status='proposed')
  ↓
audit_log: event="claim_variable_proposed" (count, run_id, failed_claims?)
  ↓
EventBus: ClaimVariablesProposed (UI polling 刷新提示, backend 内部用)
─────────────────────────────────────────────────────────
LLM 失败时 (Q-new v2):
  audit_log: event="claim_variable_proposal_failed" (run_id, error)
  Cockpit red badge 显示 "上次 propose 失败"
─────────────────────────────────────────────────────────
用户在 StockDetail 看到"提议待 review"卡片:
  ↓
Approve → status='active' (v2: 不复制到 thesis_variables_json,Q4'-C)
Edit    → modal 改字段后 Approve
Reject  → status='rejected' (monitor 永不再看)
Edit active → PATCH endpoint 改 threshold/breach_when/window (Q-new v2)
─────────────────────────────────────────────────────────
scheduler cron mon-fri 17:30 (Q6'-A2 v2 独立 job):
  thesis_evaluation_job:
    thesis_monitor_service.check_held_stocks()    # 现有,thesis_variables_json
    thesis_monitor_service.check_claim_variables()  # 新,research_claim_variables
      ↓
    INNER JOIN holdings WHERE sell_date IS NULL   # Q-new v2 持仓过滤
    对每条 status='active' 的 research_claim_variable:
      try:
        按 source 路由 fetch current_value (单点 or 过去 N 期, Q-window_periods v2)
        if window_periods > 1: 检查连续 N 期 breach
        else: 单点检查 breach_when (=lt→value<threshold / =gt→value>threshold)
        若 breached AND last_alerted_at IS NULL OR >7d ago:
          audit_log (sync): event="thesis_alert_triggered" (Q-new v2)
          emit ThesisAlertTriggered
          handler: notification_service.send() via NotificationChannel
          UPDATE last_alerted_at = now()
      except Exception:
        logger.warning(...) 带 claim_var_id/source/stock_code (Q-new v2 per-var 隔离)
```

## Schema

### 新表 `research_claim_variables` (v2)

```python
class ResearchClaimVariable(Base):
    __tablename__ = "research_claim_variables"
    __table_args__ = (
        # v2 Q-new: DB 兜底,防同 claim 重复 propose
        UniqueConstraint("research_claim_id", "stock_code", "variable_name",
                         name="uq_claim_var_claim_stock_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    research_claim_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("research_claims.id"), nullable=False, index=True
    )
    stock_code: Mapped[str] = mapped_column(
        String, ForeignKey("stocks.code"), nullable=False, index=True
    )

    # LLM 提议的结构化字段
    variable_name: Mapped[str] = mapped_column(Text, nullable=False)
    # e.g. "净息差" / "毛利率" / "PE 分位"
    threshold_critical: Mapped[float] = mapped_column(Float, nullable=False)
    breach_when: Mapped[str] = mapped_column(String, nullable=False)
    # v2 Q-new: "lt" | "gt" — 字面对齐 signal 文本比较符
    #   signal "净息差<1.3%" → breach_when="lt", threshold_critical=1.3
    #   monitor 检查: if breach_when=="lt" and value < threshold → breach
    # 老字段 `direction` 废弃,monitor 内部 lt→above / gt→below 推导
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    # "%" / "倍" / null
    source: Mapped[str] = mapped_column(String, nullable=False)
    # 见下方数据源 shortlist
    window_periods: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 持续 N 期才告警,null=单点。v2 Q-new: monitor 真实现多期检查

    # 状态机
    status: Mapped[str] = mapped_column(String, nullable=False, default="proposed", index=True)
    # "proposed" | "active" | "rejected"
    proposed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    # 个人工具,固定 "user"
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 用户 reject/edit 时的备注

    # v2 Q6'-B1: 7 天告警 dedup
    last_alerted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

Indexes: `(research_claim_id)` / `(stock_code)` / `(status)` / `(stock_code, variable_name, source)` (业务级 dedup 用)

### `thesis_variables_json` 标准化 (v2 Q1')

monitor 跟 sync_service 共用此 JSON,标准化 schema (字段名 + 必填 threshold):

```json
{
  "variables": [
    {
      "name": "净息差",
      "value": 1.45,
      "unit": "%",
      "threshold_low": 1.5,
      "threshold_critical": 1.3,
      "direction": "above",
      "source": "lixinger",
      "synced_at": "2026-06-15"
    }
  ]
}
```

**改动**:
1. `thesis_variable_sync_service.sync_stock` (line 161-168): `"current_value"` → `"value"`;保留 existing 的 threshold_*/direction/unit 字段(已存在)
2. `thesis_monitor_service.check_variable` (line 56-83): 不变,本就读 `value`
3. v2 Q4'-C: `approve` / `reject` / `PATCH` **不再** 读写此 JSON,claim var 真相源是 `research_claim_variables` 表

### 数据源 shortlist (Q3-A,v2 加 NIM 列)

LLM prompt 强制 source 必须从以下列表选:

| source key | 描述 | fetch 路径 |
|---|---|---|
| `financial:NIM` | 净息差 (银行) | `FinancialStatement.net_interest_margin` (**v2 Q3' 需加列**) |
| `financial:NPL` | 不良贷款率 (银行) | `FinancialStatement.npl_ratio` |
| `financial:revenue_growth` | 营收同比 (通用) | `FinancialStatement.revenue_growth` (列已存在) |
| `financial:margin` | 毛利率 (制造业) | `FinancialStatement.gross_margin` (列已存在) |
| `valuation:PE_percentile` | PE 10y 分位 | `ValuationSnapshot.pe_percentile_10y` |
| `valuation:PB_percentile` | PB 10y 分位 | `ValuationSnapshot.pb_percentile_10y` |
| `kline:price_drop_52w` | 52 周跌幅 | 计算 `PriceKline` 高点跌幅 |

实施时 `_fetch_current_value(db, source, stock_code, window_periods=1)` 按 source 路由分发,签名 `(db, stock_code, n) -> list[float] | None`(返回最近 N 期值,单点时 list 长度 1)。每个 source 一个 `_fetch_<source>` 函数。`None` 或空 list 表示数据缺失,monitor 跳过。

### 多期检查 (v2 Q-window_periods)

```python
def _check_breach(values: list[float], threshold: float, breach_when: str,
                  window_periods: int | None) -> bool:
    """v2: 真多期检查。window_periods=None 或 1 = 单点。"""
    n = window_periods or 1
    if len(values) < n:
        return False  # 数据不足,不告警
    recent = values[:n]
    for v in recent:
        if breach_when == "lt" and v >= threshold: return False
        if breach_when == "gt" and v <= threshold: return False
    return True  # 连续 N 期都 breach
```

### FinancialStatement 加 `net_interest_margin` 列 (v2 Q3')

```python
# backend/app/models/financial.py — 加列
net_interest_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
# 净息差 (银行),来自 Lixinger `nim.t`

# backend/app/services/pipelines/financial_pipeline.py — 已经 _get_nested(m, "nim.t"),
# 改为 column_map["net_interest_margin"] = "nim.t" 持久化

# backend/alembic/versions/s5_3_*.py — 加列 migration (老数据 NULL)
```

## API 契约

### `POST /api/research/claim-variables/{id}/approve`

approve 用户已 review 的 proposed variable。

**请求**: `{ threshold_critical?, breach_when?, unit?, window_periods?, note? }` (可选字段 = 用户 edit 后覆盖 LLM 提议值)

**响应 200**: `{ id, status: "active", stock_code, variable_name, ... }`

**副作用**: 
1. 更新 research_claim_variable.status='active' + reviewed_at + reviewed_by='user'
2. audit_log: `event="claim_variable_approved"` (before/after)
3. **v2 Q4'-C**: 不复制到 thesis_variables_json

### `POST /api/research/claim-variables/{id}/reject`

**请求**: `{ note? }`

**响应 200**: `{ id, status: "rejected" }`

**副作用**: 
1. status='rejected' + reviewed_at
2. audit_log: `event="claim_variable_rejected"`
3. **v2 Q4'-C**: 不动 thesis_variables_json (没复制过)

### `PATCH /api/research/claim-variables/{id}` (v2 Q-new)

编辑 active var 的 threshold / breach_when / window_periods / unit。status 必须是 'active'。

**请求**: `{ threshold_critical?, breach_when?, window_periods?, unit?, note? }` (至少一个字段)

**响应 200**: `{ id, status: "active", updated_fields: [...], before: {...}, after: {...} }`

**副作用**: 
1. 更新对应字段
2. audit_log: `event="claim_variable_edited"` (before/after, updated_fields)

### `GET /api/stocks/{code}/claim-variables`

获取该 stock 的所有 claim_variables (含所有 status)。

**响应 200**:
```json
{
  "proposed": [{...}, ...],
  "active":   [{...}, ...],
  "rejected": [{...}, ...]
}
```

### `GET /api/cockpit/claim-variables-pending`

Cockpit badge 用,返回 proposed 计数 + 最近 propose 失败状态 (v2 Q-new LLM 失败 UX)。

**响应 200**:
```json
{
  "count": 5,
  "by_stock": [{"stock_code": "002049", "count": 2}, ...],
  "last_proposal": {
    "status": "ok" | "failed" | null,
    "run_id": 8,
    "at": "2026-06-16T14:30:00Z",
    "failed_claims": [12, 15]
  }
}
```

## EventBus 接入

### 新增 handler

`app/core/event_handlers.py`:

```python
@bus.on(ResearchRunCompleted)
def _on_run_completed_propose_claim_variables(event: ResearchRunCompleted):
    """v2 Q5-C 自动提议 thesis variables (status='proposed')。"""
    from app.services.thesis_variable_proposal_service import propose_for_run
    db = SessionLocal()
    try:
        result = propose_for_run(db, event.run_id)
        # v2 Q-new: propose 结果 audit (成功带 count, 部分成功带 failed_claims)
        audit_log_service.write(
            db, entity_type="research_run", entity_id=str(event.run_id),
            event="claim_variable_proposed" if not result.failed_claims
                  else "claim_variable_proposal_partial",
            actor="system",
            summary=f"proposed {result.count}/{result.total} (failed: {result.failed_claims})",
        )
        bus.emit(ClaimVariablesProposed(run_id=event.run_id, count=result.count))
    except Exception as e:
        logger.exception("Claim variable proposal failed for run %s", event.run_id)
        # v2 Q-new: 失败也 audit (Cockpit red badge 用)
        audit_log_service.write(
            db, entity_type="research_run", entity_id=str(event.run_id),
            event="claim_variable_proposal_failed",
            actor="system",
            summary=f"error: {type(e).__name__}: {str(e)[:200]}",
        )
    finally:
        db.close()


@bus.on(ThesisAlertTriggered)  # v2 Q-new
def _on_thesis_alert_triggered(event: ThesisAlertTriggered):
    """breach 后发 notification (last_alerted_at dedup 已在 check 时跑过)。"""
    from app.services.notification_service import send
    db = SessionLocal()
    try:
        send(db, channels="all", title=f"论点告警: {event.variable_name}",
             message=event.message, severity="alert",
             metadata={"stock_code": event.code, "claim_var_id": event.claim_var_id})
    finally:
        db.close()
```

### 新事件 (v2 加 ThesisAlertTriggered)

`app/core/events.py`:

```python
class ClaimVariablesProposed(BaseEvent):
    run_id: int
    count: int

class ThesisAlertTriggered(BaseEvent):  # v2 Q-new
    claim_var_id: int
    code: str
    stock_name: str
    variable_name: str
    current_value: float | None
    threshold_value: float
    breach_when: str  # "lt" | "gt"
    message: str
```

## UI 设计 (Q7-A)

### StockDetail 提议区

在现有"论点变量"卡片下方加新卡片:

```
┌─ 论点变量提议 (5 条待 review) ─────────────────────────────┐
│                                                              │
│  ┌─ 净息差 ─────────────────────────────────────────────┐  │
│  │ source: financial:NIM  来自: Run 8 claim #2          │  │
│  │ 阈值: < 1.3% 持续 2 期  direction: above             │  │
│  │ signal (原文): "净息差<1.3%持续两个季度"              │  │
│  │ outcome: 息差触底反弹逻辑失效                          │  │
│  │ [Approve] [Edit] [Reject]                              │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─ 毛利率 ─────────────────────────────────────────────┐  │
│  │ source: financial:margin  来自: Run 8 claim #4       │  │
│  │ ...                                                    │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### Edit Modal (v2: 支持 proposed 与 active 两态)

```
┌─ 编辑 thesis variable (proposed 或 active) ──────────────┐
│                                                            │
│  variable_name: [净息差          ] (只读)                  │
│  threshold_critical: [1.3      ] %                        │
│  breach_when: (•) lt (<阈值告警)  ( ) gt (>阈值告警)       │
│   ↑ v2: 字面对齐 signal 文本比较符                          │
│  window_periods: [2] 期 (留空 = 单点)                      │
│  source: financial:NIM (只读)                             │
│                                                            │
│  备注 (可选): [                                          ] │
│                                                            │
│  Cancel | [Approve with edits] (proposed 态)              │
│  Cancel | [Save changes]      (active 态 → PATCH)         │
└────────────────────────────────────────────────────────────┘
```

### Cockpit Badge (v2: red/yellow 双态)

```
正常态:
┌─ 论点变量提议 ───────────────────┐
│ 🟡 5 条待 review [查看 →]        │
│   • 002049 紫光国微 (2)          │
│   • 300348 长亮科技 (1)          │
│   • 600036 招商银行 (2)          │
└────────────────────────────────────┘

v2 失败态 (Q-new):
┌─ 论点变量提议 ───────────────────┐
│ 🔴 上次 propose 失败 (run 8)    │
│   [查看错误 →]                  │
│ ────────────────────────────  │
│ 🟡 3 条待 review (旧)           │
└────────────────────────────────────┘
```

TanStack Query: `useQuery({refetchInterval: 30_000})` polling `/api/cockpit/claim-variables-pending`。

点击"查看 →"跳到第一个待 review 的 stock 的 StockDetail。

### 色标 / 状态显示

- proposed: 🟡 黄色 (待 review)
- active: 🟢 绿色 (已激活,正在 monitor)
- rejected: ⚪ 灰色 (用户拒绝,折叠显示)
- propose 失败: 🔴 红色 badge (v2 Q-new)

## 后端实施工作量 (v2)

| 文件 | 内容 | 行数估算 |
|---|---|---|
| `app/models/research_claim_variable.py` (新) | ORM model + UniqueConstraint | ~60 |
| `app/models/financial.py` (改 v2 Q3') | 加 net_interest_margin 列 | +2 |
| `app/services/pipelines/financial_pipeline.py` (改 v2 Q3') | column_map 加 nim.t → net_interest_margin | +3 |
| `alembic/versions/s5_3_research_claim_variables.py` (新) | 新表 + net_interest_margin 列 + last_alerted_at | ~60 |
| `app/services/thesis_variable_sync_service.py` (改 v2 Q1') | sync_stock 字段名 current_value → value,保留 threshold 字段 | +15 |
| `app/services/thesis_variable_proposal_service.py` (新) | LLM 调用 + parse + dedup + persist + audit | ~250 |
| `app/services/thesis_monitor_service.py` (改) | `check_claim_variables()` + 6-7 `_fetch_<source>` 路由 + 多期检查 + per-var try/except + last_alerted_at dedup | +250 |
| `app/routers/research.py` 或新 router | approve/reject/PATCH/list endpoints + audit | ~120 |
| `app/routers/cockpit.py` (改) | claim-variables-pending endpoint + last_proposal 状态 | +30 |
| `app/core/event_handlers.py` (改) | ResearchRunCompleted + ThesisAlertTriggered handler | ~50 |
| `app/core/events.py` (改) | ClaimVariablesProposed + ThesisAlertTriggered | ~25 |
| `app/scheduler.py` (改 v2 Q6'-A2) | thesis_evaluation_job 注册 (17:30 mon-fri,独立) | +30 |
| `tests/test_thesis_variable_proposal_service.py` (新) | LLM mock + persist + dedup + audit tests | ~250 |
| `tests/test_thesis_monitor_claim_variables.py` (新) | 6-7 source routing + 多期 + 持仓过滤 + dedup tests | ~300 |
| `tests/test_research_claim_variables_api.py` (新) | approve/reject/PATCH endpoint tests | ~120 |
| `tests/test_scheduler_thesis_job.py` (新 v2) | thesis_evaluation_job 触发测试 | ~50 |
| **后端小计** | | **~1565** |

## 前端实施工作量 (v2)

| 文件 | 内容 | 行数估算 |
|---|---|---|
| `src/api/client.ts` (改) | approve/reject/PATCH/listClaimVariables API | ~50 |
| `src/api/types.ts` (改) | ResearchClaimVariable + breach_when + last_proposal 类型 | ~40 |
| `src/features/stock/ClaimVariablesCard.tsx` (新) | 提议卡片列表 + active/rejected 三态 | ~220 |
| `src/features/stock/EditClaimVariableModal.tsx` (新) | Edit modal 支持 proposed/active 两态 | ~150 |
| `src/features/cockpit/PendingClaimVariablesBadge.tsx` (新) | Cockpit badge red/yellow 双态 + 30s polling | ~110 |
| `src/pages/StockDetailPage.tsx` 或 features/stock (改) | 挂载 ClaimVariablesCard | ~10 |
| `src/features/cockpit/CockpitPage.tsx` (改) | 挂载 badge | ~10 |
| **前端小计** | | **~590** |

**总计**: ~2155 行代码,**~10 小时** (含二轮 grill + 实施 + dev server 验证 + 真实 LLM spike)

## 验收标准 (v2)

### 后端 model + migration
- [ ] backend `ResearchClaimVariable` model + UniqueConstraint 建表成功
- [ ] `FinancialStatement.net_interest_margin` 列加上 (v2 Q3')
- [ ] `financial_pipeline` 持久化 NIM 数据(下次 Lixinger pull 时填充)
- [ ] migration `s5_3_*` 接 s5_2 链,跑通 upgrade/downgrade

### proposal service (含 v2 dedup)
- [ ] thesis_variable_proposal_service: 给定 mock LLM 输出,正确解析 + 持久化 proposed variable
- [ ] thesis_variable_proposal_service: 无数据源可监控的 claim 跳过 (Q3-A)
- [ ] thesis_variable_proposal_service: 业务级 dedup — 同 (stock, variable_name, source) 已有 proposed/active 时 skip (v2 Q-new)
- [ ] thesis_variable_proposal_service: DB UniqueConstraint 兜底,重复 INSERT 抛 IntegrityError 时 graceful 处理 (v2 Q-new)
- [ ] thesis_variable_proposal_service: signal 文本 "<X" 正确映射 breach_when="lt",threshold=X (v2 Q-new)
- [ ] ResearchRunCompleted EventBus handler 触发提议 + audit_log
- [ ] LLM 失败时 audit_log event="claim_variable_proposal_failed" (v2 Q-new)
- [ ] 部分失败时 audit_log event="claim_variable_proposal_partial" 带 failed_claims (v2 Q-new)

### thesis_variables_json schema 统一 (v2 Q1')
- [ ] `sync_stock` 写入字段名 `value` (不是 `current_value`)
- [ ] `sync_stock` 保留 existing 的 threshold_*/direction 字段不被覆盖
- [ ] `check_variable` 读 `value` 正常工作(本就如此)

### monitor (含 v2 多期 + 持仓过滤 + 隔离 + dedup)
- [ ] check_claim_variables: INNER JOIN holdings WHERE sell_date IS NULL (v2 Q-new)
- [ ] check_claim_variables: 对 active variable 按 source fetch current_value
- [ ] check_claim_variables: 6-7 source 各自正确路由 (financial / valuation / kline)
- [ ] check_claim_variables: NIM source 正确读 net_interest_margin 列 (v2 Q3')
- [ ] check_claim_variables: 数据缺失 (None) 跳过,不误报
- [ ] check_claim_variables: window_periods > 1 时拉过去 N 期,连续 N 期都 breach 才告警 (v2 Q-window)
- [ ] check_claim_variables: 单 var fetch 异常 try/except,继续下一条 (v2 Q-new)
- [ ] check_claim_variables: 同 var 7 天内不重发 (last_alerted_at dedup, v2 Q6'-B1)
- [ ] check_claim_variables: breach 时 audit_log + emit ThesisAlertTriggered
- [ ] ThesisAlertTriggered handler 调 notification_service.send

### API endpoints
- [ ] approve endpoint: status='active' + audit_log (不复制到 thesis_variables_json, v2 Q4'-C)
- [ ] reject endpoint: status='rejected' + audit_log
- [ ] PATCH endpoint: 改 threshold/breach_when/window_periods + audit_log before/after (v2 Q-new)
- [ ] GET /api/stocks/{code}/claim-variables: 返回 proposed/active/rejected 三组
- [ ] GET /api/cockpit/claim-variables-pending: 返回 count + last_proposal 状态 (v2 Q-new)

### scheduler (v2 Q6')
- [ ] `thesis_evaluation_job` 注册在 17:30 mon-fri,独立于 alert_evaluation_job
- [ ] job 跑通 check_held_stocks + check_claim_variables

### 前端
- [ ] 前端 StockDetail 显示 proposed 卡片
- [ ] Edit modal 改字段后 approve 正确 (proposed 态)
- [ ] Edit modal 改字段后 PATCH 正确 (active 态, v2 Q-new)
- [ ] Cockpit badge 显示 proposed 计数,30s 自动刷新 (v2 Q-new)
- [ ] Cockpit badge 失败态红色显示 (v2 Q-new)

### dev server + 真实 LLM spike
- [ ] dev server 启动,浏览器手动验证 happy path (用 run 8 真实 claims)
- [ ] 真实 LLM spike: propose_for_run(run_id=8) 跑通,落 5+ proposed variables
- [ ] spike 报告: LLM prompt 微调建议 + source 分布 + breach_when 翻转正确率

## 后置 / 未来工作 (v2 已实现项移除)

- ~~window_periods 多期检查~~ — **v2 已实现 (Q-window_periods)**
- ~~multi-stock claim~~ — **schema 已支持,LLM prompt 明确"per (claim × relevant stock) 输出一行"即可**
- **更多数据源** — `financial:OCF_to_NI` / `valuation:DYR` / `kline:drawdown_max` 等,扩展 source shortlist
- **theme-level monitor (Q1-A)** — 整个 theme 的 claims (e.g. 银行业净息差) 接入,需要外部数据源 (央行/监管)
- **historical breach 追溯** — activate 后,回看过去 N 期是否已经 breached
- **watch list (非持仓观察)** — check_claim_variables 当前过滤持仓,若用户想观察未持仓股,需新增 watch entity

## 关联文件索引 (v2)

| 文件 | 修改内容 |
|---|---|
| `backend/app/models/research_claim_variable.py` | **新建** ORM + UniqueConstraint |
| `backend/app/models/financial.py` | **改** 加 `net_interest_margin` 列 (v2 Q3') |
| `backend/app/services/pipelines/financial_pipeline.py` | **改** column_map 加 nim.t 映射 (v2 Q3') |
| `backend/alembic/versions/s5_3_research_claim_variables.py` | **新建** migration (新表 + net_interest_margin 列 + last_alerted_at) |
| `backend/app/services/thesis_variable_proposal_service.py` | **新建** LLM + dedup + audit |
| `backend/app/services/thesis_variable_sync_service.py` | **改** 字段名 + 保留 threshold (v2 Q1') |
| `backend/app/services/thesis_monitor_service.py` | 加 `check_claim_variables` + source routing + 多期 + 持仓过滤 + per-var try/except + last_alerted_at dedup |
| `backend/app/routers/research.py` (或新 router) | approve/reject/PATCH/list endpoints + audit |
| `backend/app/routers/cockpit.py` | 加 claim-variables-pending endpoint (含 last_proposal) |
| `backend/app/core/event_handlers.py` | ResearchRunCompleted + ThesisAlertTriggered handler |
| `backend/app/core/events.py` | ClaimVariablesProposed + ThesisAlertTriggered |
| `backend/app/scheduler.py` | 新建独立 `thesis_evaluation_job` (v2 Q6'-A2,不寄生 alert_evaluation_job) |
| `backend/tests/test_thesis_variable_proposal_service.py` | **新建** |
| `backend/tests/test_thesis_monitor_claim_variables.py` | **新建** |
| `backend/tests/test_research_claim_variables_api.py` | **新建** |
| `backend/tests/test_scheduler_thesis_job.py` | **新建** (v2) |
| `frontend/src/api/client.ts` | approve/reject/PATCH/listClaimVariables API |
| `frontend/src/api/types.ts` | ResearchClaimVariable + breach_when + last_proposal 类型 |
| `frontend/src/features/stock/ClaimVariablesCard.tsx` | **新建** |
| `frontend/src/features/stock/EditClaimVariableModal.tsx` | **新建** (proposed/active 两态) |
| `frontend/src/features/cockpit/PendingClaimVariablesBadge.tsx` | **新建** (red/yellow 双态 + 30s polling) |
| `frontend/src/pages/StockDetailPage.tsx` (或 features/stock) | 挂 ClaimVariablesCard |
| `frontend/src/features/cockpit/CockpitPage.tsx` | 挂 badge |
| `docs/progress/STATUS.md` | 完成后标 P2 (新) ship |

## 实施前 spike 建议 (v2)

下次实施会话第一步应该 spike `thesis_variable_proposal_service` 真实跑一次 (用 run 8 的 claims):
- 验证 LLM 输出 schema 可解析 (含 `breach_when` 字段)
- **v2 重点**: 看信号文本 `<` / `>` 翻译成 `breach_when` 的正确率 (≥80% 算 prompt 过关)
- 看实际提议数量 + source 分布 (NIM 提议比例)
- 看误判率 (LLM 编阈值 vs 合理提议)
- 验证业务级 dedup 跨 run 是否生效

spike 结果会影响 LLM prompt 微调,避免实施时返工。

## v2 grill-me 会话决策日志 (2026-06-16)

二次 grill-me 会话产出 14 项决策(详见各章节"v2"标记):

1. **Q1' schema 统一** — `thesis_variables_json` 3 套 schema 标准化为 monitor schema + 修 `sync_stock` 字段名 + 保留 threshold
2. **Q3' NIM 列** — `FinancialStatement` 加 `net_interest_margin` + pipeline 持久化(Lixinger 已在拉)
3. **Q4' 翻转双源不复制** — `research_claim_variables` 表与 `thesis_variables_json` 各为真相源,monitor 双 check 函数;原 Q4-A"approve 时复制"作废
4. **breach_when 机械字段** — `lt`/`gt` 字面对齐 signal 文本,替代易错的 `direction`
5. **window_periods 多期检查** — v1 真实现拉过去 N 期连续 breach 检查
6. **propose 业务级 dedup + DB UniqueConstraint** — 同 (stock, name, source) 已有 proposed/active 时 skip
7. **过滤 open holdings** — check_claim_variables INNER JOIN holdings WHERE sell_date IS NULL
8. **per-var try/except 隔离** — 单 source 失败不影响整批,summary 报 checked/breached/failed
9. **Q6' 独立 thesis_evaluation_job + last_alerted_at 7 天 dedup** — 不寄生 alert_evaluation_job
10. **告警三处落地** — audit_log (同步) + EventBus ThesisAlertTriggered + notification_service.send
11. **LLM 失败 UX** — audit_log + Cockpit red/yellow badge
12. **PATCH endpoint** — active var 可编辑 threshold/breach_when/window_periods
13. **TanStack 30s polling** — 不引入 SSE 基础设施
14. **migration 命名 s5_3_** — 接 s5_1 / s5_2 链

## v2 实施完成章节 (2026-06-17 验收)

> **状态**: ship (1075 测试通过 + 真实生产链路跑通 + 4 张 dev server 截图)
> **关联报告**: `docs/reports/completed/plan-thesis-monitor-v2-2026-06-17.md` + `docs/reports/thesis-monitor-v2-acceptance-2026-06-17.md`

### 40 项验收清单实测结果

**后端 model + migration (4/4)**: ResearchClaimVariable 模型 + UniqueConstraint 建表 ✅ / FinancialStatement.net_interest_margin 列 + pipeline 持久化 ✅ / migration s5_3 接 s5_2 链 ✅ / alembic head = s5_3_claim_variables ✅

**proposal service (8/8)**: mock LLM 解析+持久化 ✅ / 业务级 dedup ✅ / DB UniqueConstraint 兜底 ✅ / signal→breach_when 准确率 100% (8/8 真实 spike) ✅ / EventBus 触发+audit ✅ / LLM 失败 audit event ✅ / 部分失败 audit event ✅ / DB 实测 9 claim_variables (6 active / 2 proposed / 1 rejected)

**thesis_variables_json schema 统一 (3/3)**: sync_stock 字段名 value ✅ / 保留 threshold/direction 字段 ✅ / check_variable 读 value ✅

**monitor (10/10)**: INNER JOIN holdings WHERE sell_date IS NULL ✅ / 按 source fetch ✅ / **7/7 source 单测覆盖** (NIM/NPL/PE_percentile/revenue_growth/margin/PB_percentile/price_drop_52w) ✅ / NIM 真实读 net_interest_margin 列 (工商银行 NIM=1.2 触发) ✅ / 数据缺失跳过 ✅ / 多期 window_periods ✅ / per-var try/except 隔离 ✅ / 7 天 dedup (单测 + 真实 db 复现验证) ✅ / breach → audit + EventBus + SystemAlert + dispatch_alert (实测 SystemAlert thesis 行 22 条) ✅

**API endpoints (5/5)**: approve / reject / PATCH / GET /api/stocks/{code}/claim-variables / GET /api/cockpit/claim-variables-pending — 全部测试通过 + 截图验证 UI

**scheduler (2/2)**: thesis_evaluation_job 注册 (cron `32 17 * * 1-5`,spec 写 17:30 实际 17:32 避让 alert_evaluation) + thesis_evaluation_job_invokes_both_checks 测试 + run_job_now_thesis_evaluation_executes 测试

**前端 (5/5 + 1⚠️)**: StockDetail 三态卡片 (截图 02) ✅ / Edit modal proposed 态 (截图 03) ✅ / Edit modal active 态 PATCH (截图 04) ✅ / Cockpit badge proposed 计数 + 30s 刷新 (截图 01) ✅ / **Cockpit badge 失败态红色** ⚠️ — 代码完备但当前 GLM 账号未触发过真实 propose 失败,数据条件未达

**dev server + 真实 LLM spike (3/3)**: 4 张截图全部通过 / propose_for_run(run_id=8) 跑通 8 proposals + 9 dedup skipped / breach_when_accuracy=1.0 (spec 要求 ≥0.8)

### 实施期发现并修复的 bug

1. **Bug 1 (P0) — SystemAlert 字段不存在**: `event_handlers.py` 3 处 SystemAlert 创建 (serenity 失败 / 月度预算超限 / thesis 告警) 误用 `title` / `source` / `payload` / `triggered_at`,被 broad except 静默吞掉,所有 thesis 告警的 SystemAlert + notification 链路全断 (实测 SystemAlert thesis 表 0 行)。修复后实测 22 行。详见 acceptance report 步骤 39。
2. **Bug 2 (suspicion 澄清) — dedup 1分38秒10条同 cv_id**: audit_log 显示 cv_id=1 在 1分38秒内连续 10 条 thesis_alert_triggered,初看违反 7 天 dedup。干净环境复现验证:**dedup 工作正常** (Run 1 suppressed / Run 2 breached + 写入 last_alerted_at / Run 3 suppressed),原始现象是 spike/dev 测试残留 (含非持仓股 000001 的 mock 数据)。详见 acceptance report 步骤 40。
3. **Bug 3 (P0 顺带) — cockpit theme_exposure schema mismatch**: 不属于 v2 范围,但阻塞 dev server 验证。前端 `ThemeExposure` 类型期望 `{themes, targets, warnings}` 但后端 `/themes/exposure/analysis` 返回 `{exposure, targets, warnings}`,Cockpit 加载崩溃。新增 `ThemeExposureAnalysis` + `ThemeExposureItem` 类型对齐。

### cron 调整说明

spec Q6'-A2 写 `thesis_evaluation_job` 在 17:30 mon-fri。实际实施时为避让 `alert_evaluation` (17:30 同时刻)，**调整为 17:32** (`scheduler_config_service.py:43-47`)。语义无差异（独立 job + 独立 cron），仅时间错开 2 分钟避免单进程同时跑两个 job 的潜在竞态。

### 后置项 (Known Issues,不阻塞 ship)

- 5 个 source 未真实 LLM 链路验证: revenue_growth / margin / PB_percentile / price_drop_52w + PE_percentile 仅单测覆盖,真实 LLM spike 因 run_id=8 是银行 theme 只产 NIM/NPL。下次跑非银行 theme (半导体 / 资源) 时自动覆盖。跟踪于 `docs/active/roadmap.md` P2。
- Cockpit badge 失败态红色: 代码 + 类型完备,当前 GLM 账号余额充足未触发真实失败。配额耗尽时自动激活。
- cockpit theme_exposure schema cleanup: `ThemeExposure` 旧 type 标 `@deprecated` 保留,全量删除可放下一轮 cleanup (不在 v2 范围)。

