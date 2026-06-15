# Gojira 项目状态 (Snapshot)

> **此文档是项目当前状态的真实来源。AI 代理应首先阅读此文件。**
>
> | 字段 | 值 (实测于 2026-06-15) |
> |---|---|
> | 最后更新 | 2026-06-15 |
> | 分支 | `master` |
> | 测试 | **972 passed**, 0 failed (`pytest`) |
> | 测试函数数 | 972 (含 S0-S5 + serenity-skill 集成 34 个新测试) |
> | Alembic head | `s1_serenity_research_module` |
> | Alembic 版本文件数 | 20 |
> | 后端代码 | ~20,500 行 (app/) + ~7,650 行 (tests/) |
> | 前端代码 | ~10,900 行 (src/) |
> | 远程仓库 | 暂无 (`git remote -v` 为空) |
> | 真实使用 | **0 trades / 0 holdings / 0 drafts / 0 backtests** (production-readiness ship 但未实盘) |

---

## 1. 项目定位

Gojira 是一台 **「个人股票自动驾驶舱」**:基于 `docs/reference/invest1/2/3.md` 描述的交易体系,实现「策略组合 → 自动扫描 → 候选池 → 交易信号」全流程自动化。除了在券商真实下单外,筛选 / 监控 / 告警 / 订单草稿 / 再平衡建议 / 逻辑证伪 全部自动。

技术栈: FastAPI (Python 3.14) + React 19 (TypeScript) + SQLite + Ant Design 6 + ECharts 6。Lixinger (理杏仁) 是唯一外部数据源。

---

## 2. 核心业务流程

```
策略(Strategy) ── 原子筛选规则,可复用
  ↓ 组合
预案(Plan) ── 策略组合 + 扫描范围 + 调度 + 可选交易规则
  ↓ 自动产出
候选池(Candidate) ── 自动进出
  ↓ 用户提升到自选股
自选股(Watchlist) ── 确认关注
  ↓ 预案自动评估交易规则
草稿(Draft) ── 买卖建议
  ↓ 用户执行
持仓(Holding)
  ↓ 自动审计
审计日志(AuditLog)
```

**统一预案** = 筛选 + 可选交易规则:
- 预案定义「哪些股票值得关注」(策略组合 + 扫描范围)
- 预案同时可定义「符合条件的股票怎么买卖」(可选交易规则)
- 运行时:扫描 → 更新候选池 → 对已在自选股的候选评估交易规则 → 生成草稿

---

## 3. 模块清单 (实测)

### 3.1 后端 Routers (22 个业务模块)

| 路由 | 用途 |
|---|---|
| `health` | 基础设施健康检查 (含 DB / Token 深度探针) |
| `stocks` | Lixinger 个股数据 (基础/K线/股东/北向/融资融券/营收/论点变量/银行盲盒) |
| `valuation` | PE/PB 10y 分位 + DYR |
| `dividend` | 分红同步 + 汇总 |
| `financial` | 财报 + 比率 |
| `portfolio` | 持仓 CRUD + summary |
| `watchlist` | 自选股分组管理 |
| `alerts` | 告警事件总线 |
| `scheduler` | 调度任务管理 + 手动触发 |
| `cashflow_goal` | 单例导航目标 (年开销 × 倍数) |
| `audit_log` | 结构化审计日志 |
| `theme` | 投资主线 + 暴露分析 |
| `review` | 月度复盘 |
| `market` | 大盘指数 + 周期评估 |
| **`strategies`** | 策略 CRUD + 单股测试 |
| **`plans`** | 预案 CRUD + 手动运行 + 候选股列表 |
| **`candidates`** | 候选池 CRUD + 提升到自选股 |
| **`drafts`** | 订单草稿 execute/cancel |
| `cockpit` | 主看板聚合 |
| **`data_management`** | 数据同步 / Pipeline / 股票池 / 质量 / 清理 |
| **`observability`** | Trace / Span / Event 查询接口 |
| **`research`** | serenity-skill 研究工作流 (主题 / Run / 导出 / 反向链接) |

### 3.2 后端核心 Services (46 个,按职能分组)

**业务引擎**:
- `strategy_engine` — 纯函数策略评估器 (StrategyRule + StockContext → EvalResult)
- `stock_context_builder` — 构建单股上下文快照 (聚合估值/财报/K线/Stock数据)
- `strategy_service` — 策略 CRUD + rule_json 校验
- `plan_service` — 预案 CRUD (统一筛选+交易)
- `plan_runner` — 执行预案:扫描 → 评估 → 更新候选 → 评估交易规则 → 生成 Draft
- `candidate_service` — 候选股 CRUD + promote_to_watchlist

**数据分析**:
- `cockpit_service` — 聚合主看板所有数据
- `cycle_assessment_service` — 沪深300 PE 分位 → 5 档周期位置
- `position_advisor_service` — 组合级约束检查
- `dividend_projector_service` — 未来 12 月股息收入预测
- `dividend_sustainability_service` — 分红可持续性评分
- `thesis_monitor_service` — 论点变量阈值越界告警
- `bank_analyzer_service` — 银行股资产质量评估
- `market_temperature_service` — 市场温度
- `thesis_variable_sync_service` — 论点变量行业模板 + 自动同步

**交易/持仓**:
- `draft_service` — 草稿生成与匹配
- `draft_matcher_service` — 交易回填智能匹配
- `holding_service` — 持仓 CRUD + Portfolio Summary
- `rebalance_service` — 再平衡建议
- `cashflow_service` — 加权 DYR / 象限 / 年化被动现金流
- `cashflow_goal_service` — 现金流目标 CRUD
- `periodic_review_service` — 月度复盘

**数据接入 (Lixinger)**:
- `lixinger_client` — Lixinger API 客户端 (唯一外部数据源)
- `data_service` — 数据加载与缓存
- `data_management_service` — 数据管理协调器
- `data_quality_service` — 数据质量评估
- `stocks_sync_service` — 股票列表同步 (Lixinger HTTP shape)
- `deep_sync_service` — 财务/K线/分红 深度同步
- `kline_service` — K线增量同步
- `valuation_service` / `financial_service` / `dividend_service` / `market_service` — 各类数据查询
- `universe_service` — 全市场股票池

**Pipelines (子模块,11 个)**:
- `pipelines/manager` — Pipeline 编排器 (sync 统一入口)
- `pipelines/base` / `checkpoint` / `dead_letter` / `metrics` / `throttler` — Pipeline 基础设施
- `pipelines/{dividend,financial,kline,valuation,universe_bootstrap}_pipeline` — 各数据类型 Pipeline

**支撑**:
- `alert_service` / `audit_log_service` / `scheduler_config_service` / `theme_service` / `review_service` / `watchlist_service` / `builtin_seeder` (启动时初始化 6 策略 + 4 预案)

**Serenity 研究模块 (Q1-Q19 决策)**:
- `research_runner_service` — Q10 异步 ThreadPoolExecutor + Q13 三重硬约束 + Q17 EventBus
- `research_persistence_service` — LLM 输出 → 6 子表 + schema 校验
- `research_context_builder` — Lixinger 行业成分股装配
- `research_export_service` — Q11 Phase 1 仅 watchlist 导出
- `research_scheduler_service` — Q6 周度自动刷新 + Q12 跳过 failed
- `llm/zhipu_client` + `llm/prompts` — GLM SDK 封装 + serenity system prompt

### 3.3 数据库表 (24 个 ORM 模型)

核心表: `stocks` / `valuations` / `holdings` / `dividends` / `financial_statements` / `price_klines` / `watchlist_groups` / `watchlist_items` / `alert_rules` / `alert_events` / `cashflow_goals` / `audit_logs` / `themes` / **`strategies`** / **`plans`** (统一模型) / **`candidates`** / **`drafts`**

Serenity 研究表 (7 个,Q14 stock_code × 3 表 index): `research_themes` / `research_runs` / `value_chain_layers` / `scarce_layers` / `research_company_universe` / `research_evidence` / `research_company_ranking`

辅助表: `scheduler_jobs` (调度配置) / `pipeline_runs` (Pipeline 运行记录)

Alembic 迁移链: 20 个版本文件,head = `s1_serenity_research_module`。

### 3.4 前端页面 (11 个)

| 路径 | 页面 | 用途 |
|---|---|---|
| `/` | `CockpitPage` | 目标进度 + 持仓 + 草稿 + 告警 + 周期仪表盘 |
| `/universe` | `UniversePage` | 股票池 (全市场/自选/持仓) |
| `/strategies` | `StrategiesPage` | 策略库 (内置+自定义, CRUD+单股测试) |
| `/research` | `ResearchThemesPage` | serenity 研究方向列表 + 新建 |
| `/research/:themeId` | `ResearchThemeDetailPage` | 研究详情 (6 tab: 概览/价值链/公司/证据/失败/历史) |
| `/plans` | `PlansPage` | 预案管理 (CRUD+运行+状态切换) |
| `/candidates` | `CandidatesPage` | 候选池 (筛选结果+提升到自选,7 个筛选条件) |
| `/review` | `ReviewPage` | 月度复盘 |
| `/stock/:code` | `StockDetailPage` | 个股详情 (K线+基本面+变量追踪) |
| `/data` | `DataManagementPage` | 数据管理 (5 Tab: 健康/Pipeline/股票池/质量/清理) |
| `/scheduler` | `SchedulerPage` | 定时任务管理 |

关键组件: `Layout` / `PageHeader` / `ErrorBoundary` / `QiuScorerWizard` / `DisciplineChecklistModal` / `KlineChart` / `data-management/*` (8 个子组件)

### 3.5 调度任务 (APScheduler @ Asia/Shanghai)

| Cron | 用途 |
|---|---|
| mon-fri 17:00 | Lixinger 基本面快照 |
| mon-fri 17:05 | 沪深300 周期评估 |
| mon-fri 17:15 | K线增量同步 |
| mon-fri 17:30 | 告警规则评估 |
| mon-fri 18:00 | **预案运行** (扫描全市场 → 更新候选池 → 交易规则评估) |
| mon-fri */5 9-14 | 盘中价格监控 (可选,默认关闭) |

### 3.6 EventBus 事件注册表

| 事件 | 触发点 | 下游处理 |
|------|--------|----------|
| `DataSyncCompleted` | Pipeline 完成 | 策略重评估 / 论点变量同步 / 价格告警 |
| `PlanEvaluationCompleted` | Plan 评估完成 | 新候选告警检查 |
| `DraftCreated` | Draft 创建 | 仓位约束检查 / 审计日志 |
| `AlertTriggered` | 告警触发 | 审计日志 |

`GET /api/observability/events` 可查看当前事件注册表。

---

## 4. 内置策略 (6 个) + 内置预案 (4 个)

### 内置策略

| 策略 | slug | 规则 |
|---|---|---|
| 高股息安全垫 | `high_dividend_cushion` | DYR≥4% & 分红可持续≥60 & OCF/NI≥0.8 |
| 低估值买入信号 | `undervalued_entry` | PE分位≤30% & PB分位≤30% |
| 资源类硬资产 | `resource_hard_asset` | 行业∈资源类 & DYR≥3% & 议价能力≥2 |
| 银行业精选 | `bank_select` | 银行 & DYR≥5% & 资产质量可见 & 优质区域 |
| 现金流资产 | `cashflow_asset` | OCF/NI≥1.0 & DYR≥4% & PE分位≤50% |
| 超跌逆向机会 | `contrarian_oversold` | 跌幅≥20% & DYR≥4% & 分红可持续≥50 |

### 内置预案

| 预案 | slug | 策略组合 | 扫描范围 | 交易规则 |
|---|---|---|---|---|
| 核心价值配置 | `core_value` | 高股息安全垫 + 低估值买入信号 | 全市场 | 有 (分批建仓/30%止盈) |
| 资源主线 | `resource_macro` | 资源类硬资产 + 高股息安全垫 | 资源行业 | 有 (周期梯度) |
| 银行底仓 | `bank_anchor` | 银行业精选 | 银行行业 | 有 (DYR触发买卖) |
| 超跌逆向 | `contrarian_scan` | 超跌逆向机会 + 现金流资产 | 全市场 | 无 (纯筛选) |

定义位置: `backend/app/services/builtin_seeder.py` (硬编码,启动时初始化)。

---

## 5. 当前状态

### 5.1 累计审计修复汇总

| 审计轮次 | 日期 | P0 | P1 | P2 | P3 | 状态 |
|---|---|---|---|---|---|---|
| 第 1 轮 (init) | 2026-06-04 | — | — | — | — | 项目初稿 |
| 第 2 轮 | 2026-06-06 | 0 | 0 | 0 | 0 | 全部修复 |
| 第 4 轮 (round4) | 2026-06-05 | 1 | 6 | 7 | 3 | 全部修复 (375 测试) |
| 第 5 轮 (round5) | 2026-06-09 | 0 | 8 | 14 | 11 | 全部修复 |
| 第 6 轮 (round6) | 2026-06-11 | **5** | **15** | **12** | 0 | **全部修复 (402 测试)** |

最新审计报告: `docs/reports/completed/full-audit-round6-2026-06-11.md`

### 5.2 最近里程碑 (按时间倒序)

**2026-06-15**: serenity-skill 集成 Phase 1 完成。grill-me 会话产出 19 项决策 (Q1-Q9 核心架构 + Q10-Q19 实施细节),实施 7 张新表 / 10 个 API endpoint / 4 个 service / 异步 LLM 调用 + EventBus 告警 / Q14 反向链接 index / 34 个新测试 (972 总通过)。GLM 账号余额不足阻塞 spike 真实验证,等充值后跑 2 次真实研究。详见 `docs/reference/specs/2026-06-14-serenity-skill-integration.md` + `docs/progress/2026-06-15-serenity-skill-integration.md`。

**2026-06-13**: production-readiness-plan 重审。grill-me 会话产出 7 项决策 (删 PROMOTE / 合并 EXECUTE / 保留 backtest / watchlist 去闸门 / 跳过 S6 / draft 全表现 / 双层闸门)。**实测发现 296 候选股被 watchlist 闸门静默吞掉 → 0 draft**。详见 `docs/reference/specs/2026-06-13-revisit-production-readiness-plan.md`。

**2026-06-12**: production-readiness S0-S5 全部 ship (trades / cash / T+1 / Lixinger 防御 / 公司行为 / 回测 / 盘中监控 / 通知)。S6 Docker/DR 重审后跳过。完整执行记录见 `docs/active/production-readiness-plan.md`。

**2026-06-11**: 第 6 轮全面深度审计,6 维度 32 项发现全部修复 (P0×5 + P1×15 + P2×12)。最严重的 P0 是 Plan DSL `_strategy_definitely_fails` 忽略 AND/OR 逻辑,导致 OR 预案完全失效。同步完成架构级重构 (自定义异常 / EventBus 异步 / 批量查询 / 33 端点补 response_model / domain dataclass 转 Pydantic)。详见 `docs/reports/completed/full-audit-round6-2026-06-11.md`。

**2026-06-09**: 数据管理模块精细化升级。新增 5 个 Tab (健康概览 / Pipeline 控制 / 股票池 / 质量评估 / 数据清理),14 个前端组件,3 个后端服务。sync 操作统一到 Pipeline 入口。详见 `docs/reports/completed/data-management-audit-2026-06-09.md`。

**2026-06-09**: 全链路可观测系统上线。装饰器驱动 + 模块级批量注入,158 个函数自动 instrument,前后端独立观测。详见 `docs/reference/specs/2026-06-09-observability-design.md`。

**2026-06-05**: 业务闭环 (分析→决策→持仓) 自动接力打通。详见 `docs/reports/completed/2026-06-05-business-loop-closure.md`。

### 5.3 待修复项 (从 roadmap.md 摘录)

完整路线图见 `docs/active/roadmap.md`。优先级排序简摘:

**P0 (2026-06-13 重审后新增 — 阻塞真实使用)**:

- **P0-1 [最高]**: **解 Lixinger token** (2026-06-13 实测 expired, 14 critical alerts silent, 一切停摆)
- **P0-2 [最高]**: **去 watchlist 闸门** (`plan_runner.py:494 if code not in watchlisted: return` 静默吞 296 候选 → 0 draft)。重审决策 #1+#4
- **P0-3 [高]**: **跑首个 backtest** (回测引擎 ship 但 0 runs。重审 #7B 要求先验证策略再信任 draft)

**P1 (架构改动 — 重审决策落地)**:

- **P1-1 [最高]**: 删除 PROMOTE 流程 (重审 #1)
- **P1-2 [高]**: 合并 EXECUTE + TRADE_ENTRY modal (重审 #2)
- **P1-3 [高]**: Cockpit draft 按 Qiu 评分排序 (重审 #6)
- **P1-4 [高]**: 强制 DisciplineChecklistModal 通过才能执行 (重审 #7B)
- **P1-5 [中]**: 配置 server_chan 通道 (当前仅 in_app, alerts silent)
- **P1-6 [中]**: 端到端手动验收 (重审改动后回归)
- **P1-7 [中]**: 远程 Git 仓库 + push
- **P1-8 [中]**: CI (GitHub Actions)
- **P1-9 [低]**: cashflow_goal UI 编辑入口

**P2 (体验补全)**: 月度复盘视图增强、预案 diff 视图、StockDetail 新建预案回填、候选池筛选持久化

**P3 (技术债)**: holding_service 拆纯计算+持久查询两层、datetime.utcnow() → datetime.now(UTC)、前端 bundle 分块

---

## 6. 关键架构决策 (ADR-style)

1. **统一预案模型**: 筛选规则与交易规则合并到 Plan,删除了 PlanExecHistory / PlanTemplate / resource_profiles / portfolio_settings / bank_profiles 表 (2026-06-06)。
2. **Pydantic-first 序列化**: 所有 ORM→Response 转换走 Pydantic schemas + `response_model`,禁用裸 dict 返回。详见 `docs/standards/serialization.md`。
3. **Lixinger 唯一数据源**: 不接 Yahoo / Tushare / AkShare,所有 A 股数据走 Lixinger API。
4. **SQLite + WAL**: 单机部署,启用 WAL 模式 + busy_timeout + foreign_keys;并发场景有限,不引入 PostgreSQL。
5. **EventBus 与 Scheduler 互补**: Scheduler 负责定时拉数据,EventBus 负责数据到达后的自动响应链 (策略重评估/告警/审计)。EventBus 异步非阻塞派发。
6. **可观测性装饰器驱动**: `@tracked` 装饰器 + 模块级批量注入,158 函数自动埋点;trace_id 全链路唯一,span_id 步骤级,JSON 结构化日志。
7. **行业模板硬编码**: 内置 6 策略 + 4 预案硬编码在 `builtin_seeder.py`,不读外部 JSON (与早期设计文档不同)。
8. **个人使用,无认证**: 项目定位为个人投资工具,S-01 (认证) 已排除。CORS / Rate Limit / 文件上传校验等基础防护已就位。
9. **重审 7 项决策 (2026-06-13)**: production-readiness-plan ship 后实测 0 真实使用,根因是 watchlist 闸门吞 296 候选。重审产出 7 项架构决策: 删 PROMOTE / 合并 EXECUTE+TRADE_ENTRY / 保留 backtest (作 #7B 前置) / watchlist 去闸门留股池 / 跳过 S6 / draft 全表现+Qiu 排序 / 双层闸门 (backtest 验证 + DisciplineChecklistModal)。详见 `docs/reference/specs/2026-06-13-revisit-production-readiness-plan.md`。

---

## 7. 文档导航

| 路径 | 语义 | 何时读 |
|---|---|---|
| `docs/progress/STATUS.md` | **当前快照** (本文件) | AI 代理首先读此文件 |
| `docs/progress/*.md` | 时间线 (按日期的进度日志) | 想了解某次修改的过程 |
| `docs/active/roadmap.md` | 下一步计划 (P1/P2/P3) | 决定下一个迭代做什么 |
| `docs/standards/serialization.md` | 序列化标准 (持续生效) | 写新的 router/service 时 |
| `docs/templates/*.md` | 文档骨架模板 | 写新的 progress/completed/acceptance 文档时复制 |
| `docs/reports/*.md` | 验收报告 | 想看某次修改是否真的通过验收 |
| `docs/reports/completed/*.md` | 终态报告 (历史快照) | 想看某次完成的修改细节 (含 4 轮审计) |
| `docs/reference/invest{1,2,3}.md` | 投资理论体系 (本地,gitignored) | 想理解业务背景与投资方法论 |
| `docs/reference/investment-theory-source.md` | 投资理论原文合集 | 同上,完整版 |
| `docs/reference/specs/2026-06-08-data-management-design.md` | 数据管理 5 Tab 设计 | 修改 DataManagement 页面/Pipeline 时 |
| `docs/reference/specs/2026-06-09-observability-design.md` | 可观测性装饰器设计 | 修改 tracker/observability 时 |
| `docs/reference/specs/2026-06-10-candidates-filter-design.md` | 候选池 7 筛选条件设计 | 修改 Candidates 页面时 |
| `docs/reference/specs/2026-06-10-event-driven-automation-design.md` | EventBus + 自动化设计 | 修改事件相关代码时 |
| `docs/reference/specs/2026-06-13-revisit-production-readiness-plan.md` | production-readiness-plan 重审 7 项决策 | 修改 plan_runner / drafts UI / watchlist / DisciplineChecklist 时 |
| `docs/archive/*.md` | 归档的早期设计稿 | 想了解项目演进历史 |

### 路径变更记录 (2026-06-11 整理)

- `docs/active/code-audit.md` → `docs/reports/completed/code-audit-2026-06-05.md`
- `docs/active/lixinger-api-audit.md` → `docs/reports/completed/lixinger-api-audit-2026-06-05.md`
- `docs/active/serialization-standard.md` → `docs/standards/serialization.md`
- `docs/invest{1,2,3}.md` → `docs/reference/invest{1,2,3}.md` (gitignored, 本地移动)
- `docs/reports/full-audit-{2026-06-05,round5-2026-06-09}.md` → `docs/reports/completed/full-audit-round{4,5}-*.md`
- `docs/progress/2026-06-11-audit-round6.md` → `docs/reports/completed/full-audit-round6-2026-06-11.md`
- `docs/reports/{data-management,full-acceptance}-audit-*.md` → `docs/reports/completed/`
- `docs/superpowers/plans/*.md` → `docs/reports/completed/plan-*.md`
- `docs/superpowers/specs/*.md` → `docs/reference/specs/`
- `docs/screenshots/lifecycle/lifecycle_report.md` → 删除 (一次性测试输出)

### docs/ 目录树概览 (2026-06-11 整理后)

```
docs/
├── progress/          # 时间线 + STATUS.md (本文件,AI 首读)
│   ├── STATUS.md
│   ├── 2026-06-05-phase1-kline-screener.md
│   ├── 2026-06-05-phase2-financial-watchlist-alerts.md
│   ├── 2026-06-05-stock-selection-audit{,-v2}.md
│   ├── 2026-06-06-{audit-round2,autopilot-step{1,2,3,4},investment-system-alignment}.md
│   └── 2026-06-09-data-management-upgrade.md
├── active/            # 持续生效的计划
│   └── roadmap.md
├── standards/         # 持续生效的代码规范
│   └── serialization.md
├── templates/         # 文档骨架模板
│   ├── progress-entry.md
│   ├── completed-report.md
│   └── acceptance-report.md
├── reports/           # 验收报告 (根目录)
│   ├── 2026-06-06-e2e-lifecycle-verification.md
│   ├── 2026-06-11-docs-cleanup-acceptance.md
│   └── completed/    # 已完成的修改 (13 个,含 4 轮审计)
├── reference/         # 参考资料
│   ├── invest{1,2,3}.md  (gitignored)
│   ├── investment-theory-source.md
│   └── specs/        # 已确认的设计规格 (4 个)
└── archive/          # 早期归档
    └── 2026-06-04-investment-system-design.md
```

---

## 8. 后续阅读

- 项目规范: `CLAUDE.md`
- 路线图: `docs/active/roadmap.md`
- 最新审计: `docs/reports/completed/full-audit-round6-2026-06-11.md`
- 投资理论: `docs/reference/invest1.md` (起点)
