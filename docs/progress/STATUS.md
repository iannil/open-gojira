# Gojira 项目进展

> 此文档是项目状态的真实来源。AI 代理应首先阅读此文件。
> 最后更新：2026-06-09（第5轮全面审计完成：P1×8 + P2×14 + P3×11，详细报告见 `docs/reports/full-audit-round5-2026-06-09.md`）

## 项目定位

Gojira 是一台 **「个人股票自动驾驶舱」**：基于 `docs/invest1/2/3` 描述的交易体系，实现「策略组合 → 自动扫描 → 候选池 → 交易信号」全流程自动化。除了在券商真实下单外，筛选 / 监控 / 告警 / 订单草稿 / 再平衡建议 / 逻辑证伪 全部自动。

技术栈：FastAPI (Python) + React 19 (TypeScript) + SQLite + Ant Design + ECharts。Lixinger（理杏仁）是唯一外部数据源。

当前分支：`feature/gojira-investment-system`。

---

## 核心流程

```
策略(Strategy) ── 原子筛选规则，可复用
  ↓ 组合
预案(Plan) ── 策略组合 + 扫描范围 + 调度 + 可选交易规则
  ↓ 产出
候选池(Candidate) ── 自动进出
  ↓ 用户提升到自选股
自选股(Watchlist) ── 确认关注
  ↓ 预案自动评估交易规则
草稿(Draft) ── 买卖建议
  ↓ 用户执行
持仓(Holding)
```

**统一预案** = 筛选 + 可选交易规则：
- 预案定义「哪些股票值得关注」（策略组合 + 扫描范围）
- 预案同时可定义「符合条件的股票怎么买卖」（可选交易规则）
- 运行时：扫描 → 更新候选池 → 对已在自选股的候选评估交易规则 → 生成草稿

---

## 模块清单

### 后端 routers

| 路由 | 用途 |
|---|---|
| `health` | 基础设施健康检查 |
| `stocks` | Lixinger 个股数据（基础/K线/股东/北向/融资融券/营收/论点变量/银行盲盒） |
| `valuation` | PE/PB 10y 分位 + DYR |
| `dividend` | 分红同步 + 汇总 |
| `financial` | 财报 + 比率 |
| `portfolio` | 持仓 CRUD + summary |
| `watchlist` | 自选股分组管理 |
| `alerts` | 告警事件总线 |
| `scheduler` | 调度任务管理 |
| `cashflow_goal` | 单例导航目标（年开销 × 倍数） |
| **`strategies`** | 策略 CRUD + 单股测试 |
| **`plans`** | 预案 CRUD + 手动运行 + 候选股列表 |
| **`candidates`** | 候选池 CRUD + 提升到自选股 |
| **`drafts`** | 订单草稿 execute/cancel |
| `cockpit` | 主看板聚合 |
| `audit_log` | 结构化审计日志 |
| `theme` | 投资主线 + 暴露分析 |
| `review` | 月度复盘 |
| `market` | 大盘指数 + 周期评估 |

### 后端核心服务

| Service | 用途 |
|---|---|
| **`strategy_engine`** | 纯函数策略评估器（StrategyRule + StockContext → EvalResult） |
| **`stock_context_builder`** | 构建单股上下文快照（聚合估值/财报/K线/Stock数据） |
| **`strategy_service`** | 策略 CRUD + rule_json 校验 |
| **`plan_service`** | 预案 CRUD（统一筛选+交易） |
| **`plan_runner`** | 执行预案：扫描 → 评估策略 → 更新候选 → 评估交易规则 → 生成 Draft |
| **`candidate_service`** | 候选股 CRUD + promote_to_watchlist |
| **`builtin_seeder`** | 启动时初始化 6 内置策略 + 4 内置预案 |
| `cockpit_service` | 聚合主看板所有数据 |
| `cycle_assessment_service` | 沪深300 PE 分位 → 5 档周期位置 |
| `position_advisor_service` | 组合级约束检查 |
| `dividend_projector_service` | 未来 12 月股息收入预测 |
| `thesis_monitor_service` | 论点变量阈值越界告警 |
| `bank_analyzer_service` | 银行股资产质量评估 |
| `draft_service` | 草稿生成与匹配 |
| `draft_matcher_service` | 交易回填智能匹配 |
| `dividend_sustainability_service` | 分红可持续性评分 |
| `market_temperature_service` | 市场温度 |

### 内置策略（6 个）

| 策略 | slug | 规则 |
|---|---|---|
| 高股息安全垫 | `high_dividend_cushion` | DYR≥4% & 分红可持续≥60 & OCF/NI≥0.8 |
| 低估值买入信号 | `undervalued_entry` | PE分位≤30% & PB分位≤30% |
| 资源类硬资产 | `resource_hard_asset` | 行业∈资源类 & DYR≥3% & 议价能力≥2 |
| 银行业精选 | `bank_select` | 银行 & DYR≥5% & 资产质量可见 & 优质区域 |
| 现金流资产 | `cashflow_asset` | OCF/NI≥1.0 & DYR≥4% & PE分位≤50% |
| 超跌逆向机会 | `contrarian_oversold` | 跌幅≥20% & DYR≥4% & 分红可持续≥50 |

### 内置预案（4 个）

| 预案 | slug | 策略组合 | 扫描范围 | 交易规则 |
|---|---|---|---|---|
| 核心价值配置 | `core_value` | 高股息安全垫 + 低估值买入信号 | 全市场 | 有（分批建仓/30%止盈） |
| 资源主线 | `resource_macro` | 资源类硬资产 + 高股息安全垫 | 资源行业 | 有（周期梯度） |
| 银行底仓 | `bank_anchor` | 银行业精选 | 银行行业 | 有（DYR触发买卖） |
| 超跌逆向 | `contrarian_scan` | 超跌逆向机会 + 现金流资产 | 全市场 | 无（纯筛选） |

### 数据库表

核心表：`stocks` / `valuations` / `holdings` / `dividends` / `financial_statements` / `price_klines` / `watchlist_groups` `watchlist_items` / `alert_rules` `alert_events` / `cashflow_goals` / `audit_logs` / **`strategies`** / **`plans`**（统一模型）/ **`candidates`** / **`drafts`** / `themes`

Alembic head: `3c5b80889c29`（strategy_driven_screening_system）。

### 前端页面

| 路径 | 页面 | 用途 |
|---|---|---|
| `/` | `CockpitPage` | 目标进度 + 持仓 + 草稿 + 告警 + 周期仪表盘 |
| `/universe` | `UniversePage` | 股票池（全市场/自选/持仓） |
| `/strategies` | `StrategiesPage` | 策略库（内置+自定义，CRUD+单股测试） |
| `/plans` | `PlansPage` | 预案管理（CRUD+运行+状态切换） |
| `/candidates` | `CandidatesPage` | 候选池（筛选结果+提升到自选） |
| `/review` | `ReviewPage` | 月度复盘 |
| `/stock/:code` | `StockDetailPage` | 个股详情（K线+基本面+变量追踪） |

---

## 调度任务（APScheduler @ Asia/Shanghai）

| Cron | 用途 |
|---|---|
| mon-fri 17:00 | Lixinger 基本面快照 |
| mon-fri 17:05 | 沪深300 周期评估 |
| mon-fri 17:15 | K线增量同步 |
| mon-fri 17:30 | 告警规则评估 |
| mon-fri 18:00 | **预案运行**（扫描全市场 → 更新候选池 → 交易规则评估） |
| mon-fri */5 9-14 | 盘中价格监控（可选，默认关闭） |

---

## 事件驱动（EventBus）

| 事件 | 触发点 | 下游处理 |
|------|--------|----------|
| DataSyncCompleted | Pipeline 完成 | 策略重评估 / 论点变量同步 / 价格告警 |
| PlanEvaluationCompleted | Plan 评估完成 | 新候选告警检查 |
| DraftCreated | Draft 创建 | 仓位约束检查 / 审计日志 |
| AlertTriggered | 告警触发 | 审计日志 |

`GET /api/observability/events` 可查看当前事件注册表。

---

## 测试

```
pytest → 388 passed, 0 failed
frontend: vite build → ✓
frontend: eslint → 0 errors, 31 warnings
```

核心测试覆盖：
- `test_strategy_engine` — 纯函数策略评估器，所有字段/运算符/逻辑组合
- `test_autopilot_foundation` — cashflow_goal / audit_log / Alembic 迁移
- `test_plan_scheduler_job` — 调度器集成
- `test_cashflow_cockpit` — cashflow 公式 / Cockpit DTO
- `test_cockpit_aggregator` — 故障隔离 / 数据聚合
- `test_theme_service` — 主题暴露分析
- `test_cycle_assessment` — 周期评估 / 仓位建议
- `test_position_advisor` — 组合约束
- 其余 — alert/holding/valuation/financial/kline/watchlist/bank_analyzer/draft 等

---

## 已删除模块（被新系统取代）

- `PlanExecHistory` 模型 + `plan_exec_history` 表
- `PlanTemplate` 模型 + `plan_templates` 表 + `plan_template_service` + `routers/plan_templates`
- 旧 `plan_evaluator.py`（逻辑提取到 plan_runner）
- 旧 `plan_snapshot.py`（功能合并到 stock_context_builder）
- `PlanEditorPage.tsx` + `PlanDiffDrawer.tsx`
- `resource_profiles` / `portfolio_settings` / `bank_profiles` 表

---

## 设计文档

- 设计方案：`~/.claude/plans/docs-invest1-2-3-invest1-2-3-jiggly-ripple.md`
- 投资理论原文：`docs/reference/investment-theory-source.md`
- 原始设计稿（归档）：`docs/archive/2026-06-04-investment-system-design.md`
