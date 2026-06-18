# 自动驾驶舱改造 · Step 1：地基

> 关联设计：`docs/invest1.md / invest2.md / invest3.md`，重定位计划见 `~/.claude/plans/docs-invest1-2-3-kind-whisper.md`。

## 目标

为后续预案闭环铺设地基，不影响现有 UI：
1. 单例 `cashflow_goal` 表（自动驾驶舱的"导航目标"）
2. 结构化 `audit_logs` 表（黑匣子，并行旧 `action_logs`，Step 4 才删旧）
3. `stocks.quadrant` 列（资产四象限标签：procyclical / countercyclical / distressed_reversal / financial）

## 改动

### 新增

- `backend/app/models/cashflow_goal.py` — 单例 CashflowGoal (id=1, annual_expense, goal_multiple 默认 15, currency 默认 CNY, notes)。**导出指标在读取时计算，不入库**。
- `backend/app/models/audit_log.py` — AuditLog (entity_type, entity_id, event, actor, stock_code, summary, payload JSON-encoded)。
- `backend/app/schemas/{cashflow_goal,audit_log}.py` — Pydantic v2 schemas。
- `backend/app/services/cashflow_goal_service.py` — `get_or_create / update / target_annual_cashflow`。
- `backend/app/services/audit_log_service.py` — `write / recent`（flush-only，复用调用方事务，参考现有 `action_log_service`）。
- `backend/app/routers/cashflow_goal.py` — `GET/PUT /api/cashflow-goal`，PUT 自动写 audit log。
- `backend/app/routers/audit_log.py` — `GET /api/audit-log`（只读，支持按 entity_type/entity_id/event/stock_code 过滤）。
- `backend/alembic/versions/h8c9d0e1f2g3_autopilot_foundation.py` — 幂等迁移（has_table/has_column 检查），含 downgrade。
- `backend/tests/test_autopilot_foundation.py` — 18 个 service-level + schema + migration 测试。

### 修改

- `backend/app/models/stock.py` — 新增 `quadrant: Mapped[str | None]` 列。
- `backend/app/models/__init__.py` — 注册 `CashflowGoal`, `AuditLog`。
- `backend/app/main.py` — 注册两个新 router。

### 未改动

- 旧的 `action_log` 模块照常保留，将在 Step 4 与其它废弃模块一同删除。
- 任何前端代码：本步骤不影响现有 UI。

## 验证

```
$ pytest tests/test_autopilot_foundation.py
18 passed

$ pytest --ignore=tests/test_scheduler.py
222 passed
```

`tests/test_scheduler.py::test_daily_snapshot_job_skips_when_no_watchlist` 在本步骤前已失败（main 头亦失败），与 Step 1 无关，将在 Step 2 改造 scheduler 时一并处理。

## 设计要点

- **CashflowGoal 是单例**：`get_or_create` 总返回 id=1 行；保证主看板"唯一目标进度"语义。
- **目标进度的派生指标不入库**：`target_annual_cashflow = annual_expense × goal_multiple` 在 router 层算；`weighted_dyr` 在 Step 3 由 `cockpit_service` 联结持仓 + 估值快照算。
- **AuditLog 与旧 ActionLog 并存**：新代码统一写 audit_logs（结构化 entity_type/event/actor），旧 action_logs 写入路径保持原状，Step 4 一并删除。
- **quadrant 列暂为字符串**：枚举值约定 `procyclical | countercyclical | distressed_reversal | financial | NULL`；Step 3 cockpit 饼图前会做枚举校验或建独立 lookup 表。

## 下一步（Step 2）

- 新增 `plan` / `plan_version` / `plan_exec_history` / `draft` 模型
- 实现 Plan DSL 解析器与 ≥20 单测
- 实现 `plan_evaluator` 服务（gates / buy_ladder / sell_ladder / invalidation / cooldown）
- 在 `scheduler.py` 注册 `daily_plan_evaluation` job（默认关闭，由 settings 开关）
- 新增前端 `/plans` 列表 + 编辑器（YAML/表单双视图）
