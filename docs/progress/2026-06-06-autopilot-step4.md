# 自动驾驶舱改造 · Step 4：删 30+ 旧文件

> 关联设计：`docs/invest1/2/3.md`，重定位计划见 `~/.claude/plans/docs-invest1-2-3-kind-whisper.md`。
> 前序：`step1.md` / `step2.md` / `step3.md`。

## 目标

把 Step 1-3 留下的旧"分析师工具集"全部删干净，让代码库只剩自动驾驶舱所需。每个 phase 一个独立 commit，可独立 revert。

## 已删

### Phase 1 commit `83e5144` — 前端死代码

- **10 个旧页面**：Dashboard / Valuation / Screener / Watchlist / Financial / Portfolio / Discipline / Compare / Alerts / Journal
- **7 个组件目录**：`components/{analysis, dashboard, discipline, financial, portfolio, valuation, watchlist}`
- **1 个未引用 zustand store**：`src/store/stockStore.ts`
- 精简 `StockDetailPage`：移除 `fetchDashboard / PreTradeChecklist` 依赖；纳入"为该股新建/编辑预案"入口
- 重写 `api/client.ts` 与 `api/types.ts`，只保留实际用到的接口与类型（约 -800 行）
- `App.tsx` 收敛到 4 页路由，删除 `/legacy/*` 兜底
- `Layout.tsx` 删除"旧入口"导航组和告警徽章

净变化：-8612 行（前端）

### Phase 2 commit `4cdfdd5` — 后端 router

- 删除 **7 个 router**：`action_log` / `analysis` / `bank_profile` / `candidates` / `discipline` / `resource_profile` / `snapshots`
- 裁剪 `portfolio` router：移除 `rebalancing-guide` / `position-plan` / `position-plan/evaluation` / `themes`
- 修复 `stocks` router 中 `joinedload(Stock.analyses)`（关系不存在）
- `main.py` 同步删 7 个 `include_router`

净变化：-425 行

### Phase 3 commit `c337fc1` — 后端 service / model / schema / template

- 删除 **10 个 service**：action_log / analysis / industry_scoring / bank_profile / candidate_pool / decision_review / discipline / position_plan / resource_profile / snapshot
- 删除 **6 个 model**：action_log / analysis_snapshot / bank_profile / candidate_pool / discipline / resource_profile
- 删除 **4 个 schema**：analysis / bank_profile / discipline / resource_profile
- 删除 **6 个行业模板 JSON**：`templates/industries/` 整目录
- 迁移调用点：`alert_service` 与 `holding_service` 中 3 个 `action_log_service.log` 调用改写为 `audit_log_service.write`
- `scheduler.py` 删除 3 个 job：`weekly_snapshot` / `daily_candidate_pool` / `daily_action_digest`
- `stats` router 简化（移除 AnalysisSnapshot 计数，新增 active_plans）
- `data_service.stock_to_response` 移除 analysis_count
- `models/__init__.py` 同步删除导出
- 删除 12 个旧测试文件 + 改写 2 个

净变化：-3604 行

### Phase 4 commit `6c0cf96` — Alembic 收尾迁移

新增 `j0e1f2g3h4i5_drop_legacy_tables.py`，删除 6 张表：
`action_logs` / `analysis_snapshots` / `bank_profiles` / `candidate_pools` / `discipline_checks` / `resource_profiles`。

每张表用 `has_table` 检查保持幂等；downgrade 显式不支持。

### Phase 5（本 commit）— 文档收尾

- 重写 `docs/progress/STATUS.md` 为自动驾驶舱视角
- 重写 `docs/active/roadmap.md`，标 Step 1-4 完成，列出 P1-P3 后续
- 新增本文件

## 验证

```
$ pytest
214 passed

$ cd frontend && npm run build
✓ built in 328ms
```

Alembic chain: `3d11e6a6f1d2` → ... → `i9d0e1f2g3h4` → `j0e1f2g3h4i5`（单一 head）。
App import sanity：`from app.main import app; print(len(app.routes))` → 95。

## 当前代码库形状（Step 4 完成后）

```
backend/app/
├── models/   (15 个)  alert, audit_log, cashflow_goal, dividend, draft,
│                     financial, holding, plan(+exec_history), portfolio_settings,
│                     price_kline, screener, stock, valuation, watchlist
├── routers/  (17 个)  health, stats, stocks, market, valuation, dividend,
│                     financial, portfolio, watchlist, alerts, screener,
│                     scheduler + cashflow_goal, audit_log, plans, drafts,
│                     cockpit
├── services/ (23 个)  数据接入（lixinger_client, data_service, kline_service,
│                     stocks_detail_service, stocks_sync_service, market_service,
│                     dividend_service, financial_service, valuation_service,
│                     screener_service, watchlist_service, alert_service,
│                     holding_service）+ 自动驾驶舱（cashflow_goal_service,
│                     cashflow_service, cockpit_service, plan_service,
│                     plan_evaluator, plan_runner, plan_snapshot, draft_service,
│                     audit_log_service）
└── schemas/  (10 个)  对应 routers 的请求/响应模型

frontend/src/
├── pages/    (4 个)   Cockpit, Plans, PlanEditor, StockDetail
└── components/ Layout, ErrorBoundary, stock/KlineChart
```

总计 4 步、5 个 commit、约 **-8500 行净删除**、214 测试全通过、前端 build 干净。
