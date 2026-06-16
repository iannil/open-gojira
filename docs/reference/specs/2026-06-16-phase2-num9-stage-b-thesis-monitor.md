# Phase 2 #9 阶段 B — Thesis Monitor 接入 设计规格

> **日期**: 2026-06-16
> **状态**: 已确认 (grill-me 会话产出,代码下次实施)
> **关联**: `docs/reference/specs/2026-06-14-serenity-skill-integration.md` Q19 | Phase 2 #9 阶段 A (`docs/progress/STATUS.md` P1-1 已 ship)

## 背景

Phase 2 #9 阶段 A (2026-06-16 ship) 让 serenity LLM 输出 structured claims,每条带 `signal` 字段 (e.g. "净息差<1.3%持续两个季度")。signal 是天然的 metric key,但当前只用于 UI 展示。

阶段 B 把 signal 字段接入 `thesis_monitor_service`,实现"失败条件真实告警"—— 这是 serenity 模块的核心用户价值,invest3 "失败预警" 闭环。

本规格定义 8 个核心决策,实施工作量 ~7 小时。

## 决策汇总

| # | 决策 | 选择 | 关键约束 |
|---|---|---|---|
| Q1 | monitor 范围 | B 仅 stock-level (持仓交集) | 数据源可控 (Lixinger),告警精准 |
| Q2 | claim → variable 转换路径 | B 半自动 LLM 提议 + 人工 review | 误报风险低,跟阶段 A 一致 |
| Q3 | 数据源映射策略 | A LLM 强制从 Lixinger shortlist 选 | 避免无数据源 claim 提议,UI 不过载 |
| Q4 | 持久化结构 | A 新表 research_claim_variables + 复制到 thesis_variables_json | thesis_monitor 不动 |
| Q5 | 触发流程 | C 半自动 (EventBus 自动提议 + 人工 review) | 跟 Q2 一致 |
| Q6 | schedule + alert 通道 | A 跟现有 alert 共用 (mon-fri 17:30) + 复用 NotificationChannel | 零新 cron,零新通道 |
| Q7 | UI 入口 | A StockDetail 提议区 + Cockpit 计数 badge | 持仓 context 完整,IA 不动 |
| Q8 | 本轮范围 | A spec-only,代码下次实施 | 跟 Phase 2 #10 模式一致 |

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
              direction, source, window_periods}]
  ↓
落 research_claim_variables (status='proposed')
  ↓
EventBus: ClaimVariablesProposed (UI 刷新提示)
─────────────────────────────────────────────────────────
用户在 StockDetail 看到"提议待 review"卡片:
  ↓
Approve → status='active' + 复制到 Stock.thesis_variables_json
Edit    → modal 改字段后 Approve
Reject  → status='rejected' (monitor 永不再看)
─────────────────────────────────────────────────────────
scheduler cron mon-fri 17:30:
  thesis_monitor_service.check_held_stocks()  (现有)
  thesis_monitor_service.check_claim_variables()  (新)
    ↓
  对每条 status='active' 的 research_claim_variable:
    按 source 路由 fetch current_value
    若 breached → emit ThesisAlertTriggered → notification_service.send()
```

## Schema

### 新表 `research_claim_variables`

```python
class ResearchClaimVariable(Base):
    __tablename__ = "research_claim_variables"

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
    direction: Mapped[str] = mapped_column(String, nullable=False)
    # "above" (希望值高于阈值) | "below" (希望值低于阈值)
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    # "%" / "倍" / null
    source: Mapped[str] = mapped_column(String, nullable=False)
    # 见下方数据源 shortlist
    window_periods: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 持续 N 期才告警,null=单点

    # 状态机
    status: Mapped[str] = mapped_column(String, nullable=False, default="proposed", index=True)
    # "proposed" | "active" | "rejected"
    proposed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    # 个人工具,固定 "user"
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 用户 reject/edit 时的备注
```

Indexes: `(research_claim_id)` / `(stock_code)` / `(status)` (活跃查询过滤用)

### 数据源 shortlist (Q3-A)

LLM prompt 强制 source 必须从以下列表选:

| source key | 描述 | fetch 路径 |
|---|---|---|
| `financial:NIM` | 净息差 (银行) | `FinancialStatement.net_interest_margin` |
| `financial:NPL` | 不良贷款率 (银行) | `FinancialStatement.npl_ratio` |
| `financial:revenue_growth` | 营收同比 (通用) | 计算 `FinancialStatement.revenue` 连续两期 |
| `financial:margin` | 毛利率 (制造业) | `FinancialStatement.gross_margin` (若 schema 有) |
| `valuation:PE_percentile` | PE 10y 分位 | `ValuationSnapshot.pe_percentile_10y` |
| `valuation:PB_percentile` | PB 10y 分位 | `ValuationSnapshot.pb_percentile_10y` |
| `kline:price_drop_52w` | 52 周跌幅 | 计算 `PriceKline` 高点跌幅 |

实施时 `_fetch_current_value(db, source, stock_code)` 按 source 路由分发。每个 source 一个 `_fetch_<source>` 函数,签名 `(db, stock_code) -> float | None`。`None` 表示数据缺失,monitor 跳过。

## API 契约

### `POST /api/research/claim-variables/{id}/approve`

approve 用户已 review 的 proposed variable。

**请求**: `{ threshold_critical?, direction?, unit?, window_periods?, note? }` (可选字段 = 用户 edit 后覆盖 LLM 提议值)

**响应 200**: `{ id, status: "active", stock_code, variable_name, ... }`

**副作用**: 
1. 更新 research_claim_variable.status='active' + reviewed_at
2. 复制到 Stock.thesis_variables_json.variables[] (按 variable_name 去重)

### `POST /api/research/claim-variables/{id}/reject`

**请求**: `{ note? }`

**响应 200**: `{ id, status: "rejected" }`

**副作用**: 
1. status='rejected' + reviewed_at
2. 若该 variable_name 已在 thesis_variables_json (历史 approve 过),从中删除

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

Cockpit badge 用,返回 proposed 计数。

**响应 200**: `{ "count": 5, "by_stock": [{"stock_code": "002049", "count": 2}, ...] }`

## EventBus 接入

### 新增 handler

`app/core/event_handlers.py`:

```python
@bus.on(ResearchRunCompleted)
def _on_run_completed_propose_claim_variables(event: ResearchRunCompleted):
    """Q5-C 自动提议 thesis variables (status='proposed')。"""
    from app.services.thesis_variable_proposal_service import propose_for_run
    db = SessionLocal()
    try:
        propose_for_run(db, event.run_id)
    except Exception:
        logger.exception("Claim variable proposal failed for run %s", event.run_id)
    finally:
        db.close()
```

### 新事件

`ClaimVariablesProposed(run_id, count)` — 提议完成后发出,前端可 polling 或 SSE 刷新。

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

### Edit Modal

```
┌─ 编辑 thesis variable 提议 ──────────────────────────────┐
│                                                            │
│  variable_name: [净息差          ]                         │
│  threshold_critical: [1.3      ] %                        │
│  direction: (•) above  ( ) below                          │
│  window_periods: [2] 期 (留空 = 单点)                      │
│  source: financial:NIM (只读)                             │
│                                                            │
│  备注 (可选): [                                          ] │
│                                                            │
│              [Cancel]  [Approve with edits]                │
└────────────────────────────────────────────────────────────┘
```

### Cockpit Badge

```
┌─ 论点变量提议 ───────────────────┐
│ 🟡 5 条待 review [查看 →]        │
│   • 002049 紫光国微 (2)          │
│   • 300348 长亮科技 (1)          │
│   • 600036 招商银行 (2)          │
└────────────────────────────────────┘
```

点击"查看 →"跳到第一个待 review 的 stock 的 StockDetail。

### 色标 / 状态显示

- proposed: 🟡 黄色 (待 review)
- active: 🟢 绿色 (已激活,正在 monitor)
- rejected: ⚪ 灰色 (用户拒绝,折叠显示)

## 后端实施工作量

| 文件 | 内容 | 行数估算 |
|---|---|---|
| `app/models/research_claim_variable.py` (新) | ORM model | ~50 |
| `alembic/versions/s5_research_claim_variables.py` (新) | migration | ~40 |
| `app/services/thesis_variable_proposal_service.py` (新) | LLM 调用 + parse + persist | ~200 |
| `app/services/thesis_monitor_service.py` (改) | 加 `check_claim_variables()` + 6-7 `_fetch_<source>` 路由 | +180 |
| `app/routers/research.py` 或新 router | approve/reject/list endpoints | ~80 |
| `app/core/event_handlers.py` (改) | ResearchRunCompleted handler | ~15 |
| `app/core/events.py` (改) | 加 ClaimVariablesProposed 事件 | ~10 |
| `tests/test_thesis_variable_proposal_service.py` (新) | LLM mock + persist tests | ~200 |
| `tests/test_thesis_monitor_claim_variables.py` (新) | 6-7 source routing + breach tests | ~250 |
| `tests/test_research_claim_variables_api.py` (新) | approve/reject endpoint tests | ~80 |
| **后端小计** | | **~1100** |

## 前端实施工作量

| 文件 | 内容 | 行数估算 |
|---|---|---|
| `src/api/client.ts` (改) | approve/reject/listClaimVariables API | ~40 |
| `src/api/types.ts` (改) | ResearchClaimVariable 类型 | ~30 |
| `src/features/stock/ClaimVariablesCard.tsx` (新) | 提议卡片列表 | ~180 |
| `src/features/stock/EditClaimVariableModal.tsx` (新) | Edit modal | ~120 |
| `src/features/cockpit/PendingClaimVariablesBadge.tsx` (新) | Cockpit badge | ~80 |
| `src/pages/StockDetailPage.tsx` 或 features/stock (改) | 挂载 ClaimVariablesCard | ~10 |
| `src/features/cockpit/CockpitPage.tsx` (改) | 挂载 badge | ~10 |
| **前端小计** | | **~470** |

**总计**: ~1570 行代码,7 小时 (含 grill + 实施 + dev server 验证 + 真实 LLM spike)

## 验收标准

- [ ] backend model + migration 创建成功
- [ ] thesis_variable_proposal_service: 给定 mock LLM 输出,正确解析 + 持久化 proposed variable
- [ ] thesis_variable_proposal_service: 无数据源可监控的 claim 跳过 (Q3-A)
- [ ] ResearchRunCompleted EventBus handler 触发提议
- [ ] approve endpoint: 复制到 thesis_variables_json + status='active'
- [ ] reject endpoint: status='rejected' + (若已在 thesis_variables_json) 删除
- [ ] check_claim_variables: 对 active variable 按 source fetch current_value
- [ ] check_claim_variables: 6-7 source 各自正确路由 (financial / valuation / kline)
- [ ] check_claim_variables: 数据缺失 (None) 跳过,不误报
- [ ] check_claim_variables: window_periods > 1 时检查连续 N 期
- [ ] 前端 StockDetail 显示 proposed 卡片
- [ ] Edit modal 改字段后 approve 正确
- [ ] Cockpit badge 显示 proposed 计数
- [ ] dev server 启动,浏览器手动验证 happy path (用 run 8 真实 claims)
- [ ] 真实 LLM spike: propose_for_run(run_id=8) 跑通,落 5+ proposed variables

## 后置 / 未来工作

- **window_periods 连续性检查** — 第一版可只支持单点 (window=None),后续加多期检查
- **更多数据源** — `financial:OCF_to_NI` / `valuation:DYR` / `kline:drawdown_max` 等,扩展 source shortlist
- **theme-level monitor (Q1-A)** — 整个 theme 的 claims (e.g. 银行业净息差) 接入,需要外部数据源 (央行/监管)
- **historical breach 追溯** — activate 后,回看过去 N 期是否已经 breached
- **multi-stock claim** — claim.stock_codes 有多个时,是否复制到所有 stock 还是只第一个 (默认: 全部)

## 关联文件索引

实施时涉及的现有文件:

| 文件 | 修改内容 |
|---|---|
| `backend/app/models/research_claim_variable.py` | **新建** |
| `backend/alembic/versions/s5_research_claim_variables.py` | **新建** migration |
| `backend/app/services/thesis_variable_proposal_service.py` | **新建** |
| `backend/app/services/thesis_monitor_service.py` | 加 `check_claim_variables` + source routing |
| `backend/app/routers/research.py` (或新 router) | approve/reject/list endpoints |
| `backend/app/core/event_handlers.py` | ResearchRunCompleted handler |
| `backend/app/core/events.py` | ClaimVariablesProposed 事件 |
| `backend/app/scheduler.py` | 在现有 17:30 alert job 加 check_claim_variables 调用 |
| `backend/tests/test_thesis_variable_proposal_service.py` | **新建** |
| `backend/tests/test_thesis_monitor_claim_variables.py` | **新建** |
| `frontend/src/api/client.ts` | approve/reject/listClaimVariables API |
| `frontend/src/api/types.ts` | ResearchClaimVariable 类型 |
| `frontend/src/features/stock/ClaimVariablesCard.tsx` | **新建** |
| `frontend/src/features/stock/EditClaimVariableModal.tsx` | **新建** |
| `frontend/src/features/cockpit/PendingClaimVariablesBadge.tsx` | **新建** |
| `frontend/src/pages/StockDetailPage.tsx` (或 features/stock) | 挂 ClaimVariablesCard |
| `frontend/src/features/cockpit/CockpitPage.tsx` | 挂 badge |
| `docs/progress/STATUS.md` | 完成后标 P2 (新) ship |

## 实施前 spike 建议

下次实施会话第一步应该 spike `thesis_variable_proposal_service` 真实跑一次 (用 run 8 的 claims):
- 验证 LLM 输出 schema 可解析
- 看实际提议数量 + source 分布
- 看误判率 (LLM 编阈值 vs 合理提议)

spike 结果会影响 LLM prompt 微调,避免实施时返工。
