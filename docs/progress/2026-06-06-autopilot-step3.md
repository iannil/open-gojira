# 自动驾驶舱改造 · Step 3：切看板 + 启用 evaluator

> 关联设计：`docs/invest1/2/3.md`，重定位计划见 `~/.claude/plans/docs-invest1-2-3-kind-whisper.md`。
> 前序：`docs/progress/2026-06-06-autopilot-step1.md` / `step2.md`。

## 目标

把"预案闭环"端到端跑起来：
- 后端给前端一个 cockpit 聚合接口
- 前端用 4 页（实际 3 个新页 + 沿用 1 个 StockDetail）替代旧的"分析师工具集"主导航
- 旧 11 页保留在 `/legacy/*`，本步骤不删
- 翻开 `PLAN_EVALUATOR_ENABLED` 默认值，让 evaluator 真的开始每天产生草稿

## 改动

### Step 3A · 后端聚合

- `backend/app/services/cashflow_service.py`
  - `compute(db) → CashflowMetrics`：用 cashflow_goal 单例 + holding_service.get_portfolio_summary 拼出 weighted_dyr / annual_passive_cashflow / goal_progress / total_portfolio_value
  - `quadrant_breakdown(db) → list[dict]`：按 `stocks.quadrant` 分组、计算 weight_pct，未标注归 `"unlabeled"` 桶，便于 UI 提醒补标
- `backend/app/services/cockpit_service.py`
  - 单一聚合 `build(db) → dict`：fan-out 到 cashflow / drafts / holdings / quadrant / alerts / plans
  - **故障隔离**：每段用 `_safe(name, fn, default, errors)` 包裹，任何一段抛错只塞 errors 列表，**不 500 整体**
- `backend/app/routers/cockpit.py` — `GET /api/cockpit` 直接吐 DTO
- 测试 `tests/test_cashflow_cockpit.py` 11 个：空组合 / 基本公式 / 目标为 0 时 progress=None / 现金储备计入总值 / quadrant 分组与未标注桶 / cockpit DTO 顶层键 / cashflow 公式 / quadrant 关联 / 节段故障隔离

### Step 3B · 前端

新增 3 个页面（沿用 `StockDetailPage` 作为第 4 个详情入口）：

- `frontend/src/pages/CockpitPage.tsx` — 主看板
  - 顶部 `GoalNavigator`：目标进度 Progress + 加权 DYR Statistic + 组合总值
  - 中间 `DraftList`：今日 BUY/SELL 草稿表，每行一键「已成交」/「取消」(都带 Modal 确认)
  - 左下 `QuadrantPie`：echarts 环形饼，使用 quadrant 中文标签 + 调色
  - 右下 `AlertsList`：未确认告警列表
  - 底部 `HoldingsTable` + `PlansList`
- `frontend/src/pages/PlansPage.tsx` — 预案列表：仅显示生效切换 / 编辑 / 撤销（撤销绕过盘中锁）
- `frontend/src/pages/PlanEditorPage.tsx` — 新建 / 编辑
  - 顶部 form：code / thesis / 生效区间 / gates / position（受 Pydantic 校验）
  - 底部 JSON 区：buy_ladder / sell_ladder / invalidation / cooldown_days；附两个"套用预设"按钮（高股息蓝筹 / 资源股周期）
  - 编辑模式下显示 status + 当前版本号，下方提示"盘中（09:25–15:00）写会被 409 拒，需止损请回列表点撤销"

API 客户端 / 类型：

- `frontend/src/api/types.ts` 追加 `CashflowGoalResponse / AuditLogEntry / PlanStatus / BuyTrigger / SellTrigger / InvalidationRule / BuyStep / SellStep / PlanGates / PlanPosition / PlanSpec / PlanResponse / PlanCreate / PlanUpdate / DraftResponse / Cockpit* / CockpitResponse`
- `frontend/src/api/client.ts` 追加 `fetchCockpit / fetchCashflowGoal / updateCashflowGoal / listPlans / getPlan / createPlan / updatePlan / revokePlan / evaluatePlan / listDrafts / executeDraft / cancelDraft / fetchAuditLog`

### Step 3C · 路由 + 默认值

- `frontend/src/App.tsx`
  - 新 IA 4 页放在 `/` 根空间：`/`（Cockpit）`/plans`（列表）`/plans/new`（新建）`/plans/:code`（编辑）`/stock/:code`（详情）
  - 旧 11 页 全部前缀挂到 `/legacy/*`（Dashboard→`/legacy`，Valuation→`/legacy/valuation` 等等）— 留到 Step 4 一起删
- `frontend/src/components/Layout.tsx`
  - 主导航收敛为 **驾驶舱（主看板 / 预案）** + **旧入口（旧分析台）** 两组
- `backend/app/config.py`
  - `PLAN_EVALUATOR_ENABLED` 默认值从 `False` → `True`；测试相应改为 monkeypatch
- 新增 `test_job_default_is_enabled_in_step_3` 锁住默认值

## 测试

```
$ pytest --ignore=tests/test_scheduler.py
281 passed

$ cd frontend && npm run build
✓ built in 413ms
```

新增 11 个后端测试（cashflow + cockpit）。`tests/test_scheduler.py::test_daily_snapshot_job_skips_when_no_watchlist` 仍是 step 1 之前就存在的 flake，本步未处理。

## 验收（手动）

```
$ ./dev.sh
# → http://localhost:3000/
# → 默认进入 Cockpit；
# → 顶部"现金流目标进度"显示「设定目标」（默认 annual_expense=0）
# → 进入 /plans → 新建预案 601398（套用「高股息蓝筹」预设）→ 保存
# → POST /api/scheduler/jobs/daily_plan_evaluation/run 手动触发
# → 回到 / 应看到「今日订单草稿」（基于当前 valuation/dividend 数据）
# → 点「已成交」→ 草稿清空，audit log 写入
```

## 不变量

- 主看板**只读**——人只看，不改 plan/draft 状态
- 草稿状态变更必须通过明确的「已成交 / 取消」点击，且都有 Modal 确认
- 盘中改预案 → 409，撤销 → 允许
- evaluator 默认开启，但**首次启动时无 plans → 0 草稿**，不存在"无预案就乱发"

## 下一步（Step 4）

- 删除 30+ 个旧文件（按 plan 文件第 2 节红色清单）
- 关闭对应 scheduler job：weekly_snapshot / daily_candidate_pool / daily_action_digest
- 删 `/legacy/*` 路由 + 旧前端页 + 旧 router + 旧 service + 旧 model + 旧 templates
- 删除 `action_log` 整套（已被 audit_log 取代）
- 删除对应测试
- 更新 `docs/progress/STATUS.md` 与 `docs/active/roadmap.md`
