# 自动驾驶舱改造 · Step 2：预案核心

> 关联设计：`docs/invest1.md / invest2.md / invest3.md`，重定位计划见 `~/.claude/plans/docs-invest1-2-3-kind-whisper.md`。
> 上一步：`docs/progress/2026-06-06-autopilot-step1.md`。

## 目标

把"预案 DSL → 评估器 → 订单草稿"的闭环搭起来；不影响现有 UI；evaluator job 注册但默认关闭。

## 改动

### 新增模型 / 迁移

- `backend/app/models/plan.py` — `Plan` (versioned, unique on code+version)、`PlanExecHistory`（一档触发一行，含 executed_at/fill_price/fill_quantity 回填位）
- `backend/app/models/draft.py` — `Draft`（pending/executed/cancelled，含 reason 文本、与 `plan_exec_history` 一对一）
- `backend/alembic/versions/i9d0e1f2g3h4_plans_drafts.py` — 三张表 + 索引 + downgrade，head 仍单一

### Plan DSL（`backend/app/schemas/plan.py`）

- `PlanSpec`：`gates / position / buy_ladder / sell_ladder / invalidation / cooldown_days`
- `BuyTrigger.kind ∈ {price_le, dyr_ge, drawdown_from_last_buy, pe_pct_le}`
- `SellTrigger.kind ∈ {profit_pct_ge, dyr_le, pe_pct_ge}`
- `InvalidationRule.kind ∈ {ocf_to_ni_3y_lt, dividend_cut_pct_ge, thesis_manual_revoke}`
- 全部触发器以 `kind` + `value` 描述，存为 JSON，grep-friendly
- `PlanCreate` 强制 `effective_until > effective_from` 且窗口 ≤ 366 天
- 持久化：`Plan.spec_json` ↔ `parse_spec / dump_spec`

### 评估器（`backend/app/services/plan_evaluator.py`）

**纯函数**：`evaluate(spec, snapshot, *, current_status, effective_until, executed_step_keys, pending_step_keys, cooldown_until) -> EvalDecision`

判定顺序：expiry → invalidation → gates → cooldown → buy_ladder → sell_ladder（仅当有持仓）→ status transition。

执行不变量：
- `executed_step_keys` 已成交的档位永不重发
- `pending_step_keys` 已触发未成交的档位也不再发（避免重复）
- cooldown 仅压制新发，**不**压制 invalidation
- gate 任一字段缺数据 → 失败关门（fail closed）

### 输入加载（`backend/app/services/plan_snapshot.py`）

`build(db, plan)` 把 evaluator 需要的 11 个字段从现有表里拼装好：valuation（DYR、PE/PB 分位）、price_kline（最新收盘）、holding（仓位市值、均价、profit_pct）、financial（OCF/NI 3Y）、dividend（最近分红下调比例）、plan_exec_history（上次买入参考价）。后续若任一指标缺失，evaluator 自然 fail closed，不会误发草稿。

### 服务层

- `plan_service`：CRUD + 版本化 + **盘中写禁令**（09:25–15:00 Asia/Shanghai，工作日；周末/盘后放行）+ `revoke_thesis`（紧急止损绕过写禁令）
- `draft_service`：`emit / execute / cancel`，execute 自动回填 `PlanExecHistory.executed_at + fill_price + fill_quantity`，cancel 删除尚未成交的 history 行
- `plan_runner`：把 evaluator 和 DB 粘合，含 `run_for_plan / run_all_active`；每条草稿写一条 audit_log（`entity_type=draft, event=triggered, actor=evaluator`），状态变更写 plan 级 audit_log

### 路由

- `POST /api/plans` 新建预案（盘中拒）
- `GET /api/plans` 列出最新版（`?active_only=true` 仅 armed/partial）
- `GET /api/plans/{code}` 取最新版
- `PUT /api/plans/{code}` 创建新版本（盘中拒）
- `POST /api/plans/{code}/revoke` 立刻 invalidated（盘中允许）
- `POST /api/plans/{code}/evaluate` 手动评估一次
- `GET /api/drafts?status=&code=&limit=`、`POST /api/drafts/{id}/execute`、`POST /api/drafts/{id}/cancel`

### 调度器

- `scheduler.daily_plan_evaluation_job` 注册到 17:45 (Asia/Shanghai, mon-fri)
- 受 `settings.PLAN_EVALUATOR_ENABLED` kill-switch 控制（**默认 False**，Step 3 切完看板再开）
- 旧 jobs 完全未动，本步不破坏现有行为

### 配置

- `PLAN_EVALUATOR_ENABLED: bool = False`
- `TRADING_LOCK_START / TRADING_LOCK_END`（默认 `09:25 / 15:00`）

## 测试

```
$ pytest tests/test_plan_evaluator.py tests/test_plan_service.py tests/test_plan_scheduler_job.py
47 passed

$ pytest --ignore=tests/test_scheduler.py
269 passed
```

- **`test_plan_evaluator.py` 30 case**：expiry / 三种 invalidation / 三种 gate miss / 缺数据 fail closed / 单档买入触发 / dyr 不达不发 / 多档 drawdown 串联 / 缺参考价跳过 / executed 幂等 / pending 幂等 / cooldown 抑制 / cooldown 不抑制 invalidation / cooldown 过期解除 / cooldown_end helper / 无持仓不卖 / 有持仓 profit_pct 触发 / 高 PE 触发需 gate 放开 / 状态转换 armed/partial/completed / spec 拒空 ladder / position 边界校验 / trigger value 校验 / step 百分比校验
- **`test_plan_service.py` 14 case**：版本号 / 多版本不互相覆盖 / 工作日盘中拒写 / 周末放行 / revoke / window 校验 / runner 输出草稿和 audit log / 不重复发 / executed 回填 history / cancel 删 history / 有持仓时双方向草稿 / lock_window helper
- **`test_plan_scheduler_job.py` 3 case**：注册到 JOB_REGISTRY / kill-switch 关时直接跳过 / kill-switch 开时调用 runner

## 不变量

- **写盘**：盘中（09:25–15:00 工作日）`POST/PUT /api/plans` 返回 409；`revoke` 接口与 `cancel` 不受限
- **版本化**：每次 PUT 落新行，旧版可读；evaluator 只看 `latest_for_code`
- **幂等性**：同一 step 触发 → `pending` 状态直到 user 标记 executed；evaluator 在 pending 期间不再发
- **草稿可解释**：每条 Draft 必有 `reason: "{trigger_kind}: {observed} {op} {threshold}"`

## 下一步（Step 3）

- 实现 `cashflow_service`（加权 DYR、年化被动现金流、目标进度）
- 实现 `cockpit_service` 聚合接口 → `GET /api/cockpit`
- 前端新建 `/` Cockpit 主看板 + `/plans` 列表 + `/plans/:code/new` 向导
- 启用 `PLAN_EVALUATOR_ENABLED=true`
- 旧 Dashboard 路由迁到 `/legacy`，AnalysisPage 等仍保留至 Step 4 一起删
