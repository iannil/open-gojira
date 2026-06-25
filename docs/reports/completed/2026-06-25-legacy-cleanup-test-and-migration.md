# 历史遗留问题处理：测试套件 + Alembic 迁移链

> 日期：2026-06-25 ｜ 状态：已完成 ｜ 背景：v2-rewrite 后遗留的两类破损，在 trading-philosophy Phase 2 工作中暴露并处理。

## 1. 测试套件：删除 56 个 v1 死测试

**问题**：v2-rewrite 删除了 v1 概念模块（plan / strategy_engine / candidate / research_* / watchlist / backtest_* / business_pattern / builtin_seeder 等），但留下 56 个测试文件在 **import 时**就引用这些已删模块 → 56 个 collection error，`tests/` 根目录套件无法收集。

**处理**：删除这 56 个文件（它们测试的代码已被设计性移除，无法修复也无法迁移）。

**结果**：collection 干净 —— 618 tests collected, 0 errors（原先 56 errors）。`tests/v2/` 全程不受影响（63 passed）。

## 2. Alembic：迁移链断根，压缩为单一基线

**问题**：35 条迁移中**无 base**（无 `down_revision=None`）。原始 base 迁移 `3c5b80889c29`（创建 `stocks` + 核心 Lixinger 表）在早期清理中被删，导致从空库 `alembic upgrade head` 失败（`no such table: stocks`）—— **clean-slate 全量发布无法进行**，违反发布约定。另有 1 个孤儿迁移 `n4o5p6q7r8s9`（指向另一个已删祖先，不在 head 链上）。

**处理（决策：squash）**：
- 新建 `alembic/versions/v2_baseline_squash.py`（`down_revision=None`），`upgrade()` 直接从当前模型 `Base.metadata.create_all` 建全量 schema，`downgrade()` drop 全部。
- 删除原 52 个迁移文件（34 链上 + 孤儿 + 中间历史）。当前模型 == 旧 34 条迁移累积效果，故对新部署等价，且保证迁移 schema 与代码一致。

**验证**：空库 `alembic upgrade head` → 34 张表全部创建（stocks / research_reports / theme_scan_reports / financial_statements / price_klines …）。单 head：`v2_baseline_squash`。

### 现有 dev DB（data/gojira.db, 1.2GB）收尾 —— ✅ 已执行（2026-06-25）

dev DB 实测已含 `theme_scan_reports` 表（37 张表，schema 完整），无需补建。仅需对齐 alembic 标记。

**注意**：直接 `alembic stamp v2_baseline_squash` 会失败 —— 因当前 `alembic_version` 仍指向已删的 `v2_1_initial_cleanup`，alembic 先校验当前修订无法定位。须加 `--purge` 重置标记：

```bash
cd backend
alembic stamp v2_baseline_squash --purge   # 仅重置 alembic_version 表，不动数据
```

**结果（实测）**：`alembic current` → `v2_baseline_squash (head)`；`alembic_version` 表 = `['v2_baseline_squash']`；`theme_scan_reports` 存在。alembic 命令恢复正常。

## 3. 重大发现：22 个失败测试其实在抓 v2-rewrite 的真实破损（已部分修复）

triage 揭示：这 22 个文件**不是 stale 测试**，而是在抓 **v2-rewrite 遗留的真实生产 bug**。v2-rewrite 删除了 v1 概念（cashflow_goal / plan / theme / rebalance / cycle_assessment 等），但多个 LIVE service 仍引用它们，仅靠 try/except fallback 掩盖。

### 已修复（已验证，clean + isolated）
1. **`trade_service.py:160`** —— 调用未定义的 `available_quantity_at`（应为 `_available_quantity_at`，少个下划线）。**导致所有卖出交易崩溃**（NameError）。改为正确函数名。
2. **`holding_service._get_or_init_settings`** —— import 已删的 `cashflow_goal` 模型 → **portfolio summary + holding 端点全崩**。重构为：`cash_reserve` 取真实 `CashBalance` 账本，`target_weighted_dyr` 用方法论常量 0.045，彻底去掉 cashflow_goal 依赖。

### 已确认意图（据 v2 设计文档）
- **cashflow_goal v2 故意删除**（`v2-implementation-plan.md:60`，`/cashflow-goal` router 也删）。引用它的 service 是 v1 残留，应重构/删除，**不是要恢复模型**。
- **v2 持仓来自 CSV 导入；trades 是独立账本，无 trade→holding 同步**（`redesign-decisions-v2.md:206,209`）。故 `_available_quantity_at` 读 Holding 是设计如此；`test_trades_api` / `test_trade_service_constraints` 里「BUY 交易→可卖」是 **v1 模型 → stale 测试**，应改写为「对 CSV Holding 卖出」。

### 🔴 重大系统性破损：cockpit 整个 dashboard 在 v2 已死
`app/services/cockpit_service.py` **完全无法 import** —— 顶层 import 了已删的 `plan_service` / `theme_service` / `rebalance_service` / `cycle_assessment_service`，外加坏掉的 `cashflow_service`（后者 import 不存在的 `cashflow_goal_service`）。cockpit router 只能靠**惰性 import** 才让 app 启动，实际任何 cockpit 请求都会崩。
- **本质**：cockpit_service 是 v1 工件，v2 计划「改造 CockpitPage → 信号优先 dashboard」但 **service 层从未重写**。
- **修复 = v2 feature 级重写**（信号优先 dashboard），非 bug 修补。`cashflow_service` 删除 + 面板移除应并入此重写（用户已决策移除面板）。
- `market_temperature_service`：真死代码（无引用方）+ 坏（import cashflow_goal），属同一清理批次。

### 待办（建议作为「完成 v2 service 层重写」专项）
- 重写 `cockpit_service` 为 v2 信号优先 dashboard（去 plan/theme/rebalance/cycle/cashflow 依赖）。
- 删除 `cashflow_service.py` + `market_temperature_service.py`（随 cockpit 重写一并）。
- 改写 `test_trades_api` / `test_trade_service_constraints` 为 v2 持仓模型。
- 复核其余失败文件（test_scheduler / event_bus / corp_action / notifications_api / security_theme 等）是否同类残留。

> **当前已提交价值**：2 个真实生产 bug 已修（卖出崩溃 + portfolio/holding 崩溃），money-path 测试 72 passed。

## 4. 任务 #14 进展：v2 service 层清理（2026-06-25）

调查发现 cockpit 的真相：**`cockpit_service.py` 完全孤立**（v2 cockpit router 是有意的 Phase-3 stub，根本不调用它；grep 命中只是注释）。即「cockpit 已死」属实，但无关紧要——它是孤立 v1 残留。

### 已执行
- **删除 `app/services/cockpit_service.py`**：孤立 v1 残留（无任何 importer），引用 ~10 个已删服务。v2 cockpit 走 router stub，等 Phase-3 信号优先 dashboard 重建。
- **删除 `app/services/cashflow_service.py` + `market_temperature_service.py`**：cashflow_service 原仅被 cockpit_service 引用、market_temperature 无引用方；均坏（import 已删 cashflow_goal）。
- **修 `holding_service._get_or_init_settings`**（live bug）：去 cashflow_goal 依赖 → `cash_reserve` 取真实 `CashBalance`、`target_weighted_dyr`=0.045 常量。修复 portfolio summary 端点。
- **修 `trade_service.py:160`**（live bug）：`available_quantity_at` → `_available_quantity_at`，修复所有卖出交易崩溃。
- **更新 `test_cockpit_response_model`**：从 v1 schema 断言改为 v2 stub 契约。

### 净效果
全套测试 **130 failed → 81 failed**（+49 passing）。`tests/v2/` + cockpit 全绿（64 passed）。app 正常启动（131 routes）。

### 待办（#14 剩余，~81 failures 逐文件 triage）
- `test_trades_api` / `test_trade_service_constraints`：v1「交易建仓」模型 stale 测试 → 改写为 v2 持仓模型（对 CSV Holding 卖出）。
- 其余失败文件（scheduler / event_bus / corp_action / notifications_api / security_theme / thesis_alert_handler 等）：逐个判 stale vs 真实 bug。
- Phase-3 cockpit 信号优先 dashboard 重建（独立 feature，非本清理范围）。

待 triage 文件清单：
```
tests/routers/test_portfolio.py        tests/routers/test_stocks.py
tests/test_annualized_return.py        tests/test_available_quantity_api.py
tests/test_business_patterns_router.py tests/test_cockpit_response_model.py
tests/test_corp_action_api.py          tests/test_corp_action_processor.py
tests/test_event_bus.py                tests/test_holding_service.py
tests/test_notifications_api.py        tests/test_plan_runner_cycle_gate.py
tests/test_plan_scheduler_job.py       tests/test_research_router.py
tests/test_risk_rules_api.py           tests/test_scheduler.py
tests/test_scheduler_alerting.py       tests/test_security_theme.py
tests/test_thesis_alert_handler.py     tests/test_trade_service.py
tests/test_trade_service_constraints.py tests/test_trades_api.py
```
优先级建议：先看守护核心资金路径的 `test_trade_service(_constraints)` / `test_trades_api` / `test_holding_service` / `test_available_quantity_api`（T+1 / 费用 / 卖出约束）。
