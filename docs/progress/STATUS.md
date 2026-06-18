# Gojira 项目状态 (Snapshot)

> **此文档是项目当前状态的真实来源。AI 代理应首先阅读此文件。**
>
> | 字段 | 值 (实测于 2026-06-18 grill-me + F17 v2 + F21 修复后) |
> |---|---|
> | 最后更新 | 2026-06-18 (F21 — BacktestSubmit schema vs engine 字段不对齐 (`strategy_rules` vs `strategies`),所有 POST /api/backtests 永远 0 strategies → 0 trades。schema 改 `strategies: list[int]` + `target_pct: float` + 3 单测。实测 backtest 真跑 8 trades / total_return -1.9% / sharpe -0.89,metrics 全部计算正确。backtest engine 首次真实跑通) |
> | 分支 | `master` |
> | 最新 commit | (待提交) F21 backtest schema 对齐 |
> | 测试 | **1175 passed**, 0 failed (`pytest`) |
> | 测试函数数 | 1175 (1172 + F21×3) |
> | Alembic head | `s10_1_in_circle_filter_default_off` |
> | Alembic 版本文件数 | 50 |
> | 后端代码 | ~33,000 行 (app/) + ~20,000 行 (tests/) |
> | 前端代码 | ~18,500 行 (src/) |
> | 远程仓库 | 暂无 (`git remote -v` 为空) |
> | 真实使用 | **DB 2026-06-18 F17 v2 后状态**: 0 holdings / 0 trades / 10 drafts (pending,plan 1×6 + plan 3×3 + plan 5×1) / 12 active candidates (plan 1×4 + plan 3×7 + plan 5×1) / 0 research_runs / 0 backtests / 0 thesis 告警。**核心闭环跑通,6 内置 plan 现在 4 个真实可用 (plan 1/3/4/5)** — plan 2 仍 0 候选 (高息低估值 AND 太严),plan 6 因 F10 (qiu_score 全 0)。 |

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
候选池(Candidate) ── 自动进出 (source: rule_based | serenity)
  ↓ (重审 2026-06-13:去 watchlist 闸门)
草稿(Draft) ── 买卖建议 (220 累积,等用户审阅)
  ↓ 用户执行
持仓(Holding) ── 0 当前
  ↓ 自动审计
审计日志(AuditLog)
```

**统一预案** = 筛选 + 可选交易规则:
- 预案定义「哪些股票值得关注」(策略组合 + 扫描范围)
- 预案同时可定义「符合条件的股票怎么买卖」(可选交易规则)
- 运行时:扫描 → 更新候选池 → 对候选评估交易规则 → 生成草稿 (无 watchlist 闸门,重审 #1+#4)

---

## 3. 模块清单 (实测)

### 3.1 后端 Routers (22 个业务模块)

| 路由 | 用途 |
|---|---|
| `health` | 基础设施健康检查 (含 DB / Lixinger Token / Zhipu API 三层深度探针) |
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

**Serenity 研究模块 (Q1-Q19 决策, Phase 1 + Phase 2 已 ship)**:
- `research_runner_service` — Q10 异步 ThreadPoolExecutor + Q13 三重硬约束 + Q17 EventBus + LLM log dumping
- `research_persistence_service` — LLM 输出 → 6 子表 + schema 校验
- `research_context_builder` — Lixinger 行业成分股装配
- `research_export_service` — Q3 D 导出 watchlist + candidate (Phase 2 加 candidate via plan_id nullable)
- `research_scheduler_service` — Q6 周度自动刷新 + Q12 跳过 failed
- `llm/zhipu_client` + `llm/prompts` — GLM SDK 封装 + serenity system prompt
- `cockpit_service` 扩展 — Phase 2 加 `_get_latest_serenity_summary` + `_get_monthly_serenity_spend`

### 3.3 数据库表 (~41 个 ORM 模型,2026-06-15 实测)

核心表 (S0-S5 ship): `stocks` / `valuations` / `holdings` / `trades` / `dividends` / `financial_statements` / `price_klines` / `historical_klines` / `historical_valuations` / `historical_financials` / `watchlist_groups` / `watchlist_items` / `alert_rules` / `alert_events` / `cashflow_goals` / `audit_logs` / `themes` / **`strategies`** / **`plans`** (统一模型) / **`candidates`** (Phase 2 加 source + plan_id nullable) / **`drafts`** / `backtest_runs` / `corp_actions` / `cash_balance` / `cash_adjustment` / `broker_fee_config` / `holding_risk_rule` / `notification_channels` / `system_alerts` / `data_freshness` / `business_patterns` / `trading_calendar` / `scheduler_jobs` / `pipeline_runs`

Serenity 研究表 (7 个,Q14 stock_code × 3 表 index): `research_themes` / `research_runs` / `value_chain_layers` / `scarce_layers` / `research_company_universe` / `research_evidence` / `research_company_ranking`

Alembic 迁移链: 50 个版本文件 (实测 2026-06-18),head = `s10_1_in_circle_filter_default_off`。

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

最新审计报告: `docs/reports/completed/full-audit-round6-2026-06-11.md` (历史) + `docs/reports/2026-06-15-completeness-audit.md` (最新三层完成度审计)

### 5.2 最近里程碑 (按时间倒序)

**2026-06-18**: 功能审计 — 5 P0/CRITICAL 全修 + 核心闭环首次真跑通。`/grill-me` 会话清空 DB 验证 Batch 1-5,实测发现此前的 6 轮审计 + 5 个 Batch ship 全部基于空 DB,1157 tests 通过 ≠ 真实链路跑通。发现并修复 5 项: F4 AdaptiveThrottler 死代码 wire / F5 429 retry / F7 avoid_overvalued_tech invalid op / F8 stock_context_builder bank industry 双语 / F12 (CRITICAL) Batch 5 M2 in_circle filter 默认翻转 + migration `s10_1`。修后 plan_runner (plan 1) 自动产出 4 candidates + 6 drafts,Cockpit API 正确返回。1157 测试通过 (+2)。详见 `docs/progress/2026-06-18-feature-audit-drift-findings.md`。

**2026-06-17 (深夜)**: invest1/2/3 对齐审计 Batch 3 ship (spike 验证 + 文档对齐)。grill-me 会话验证 Batch 1/2 实施情况,发现 D3 6/7 红旗中 3/7 是死代码 + 5 missed 概念。spike `backend/spikes/probe_redflag_metrics.py` 用 4 真实股票 (宝丰能源/南山铝业/芭田股份/紫金矿业) 验证 Lixinger metric keys: `bs.ar.t` (应收账款) + `m.i_tor.t` (存货周转) + `auditOpinionType` (审计意见 top-level) 全部 4/4 股票 200 + 实际数据; `ps.np_wd_s_r.t` (扣非净利率) + `bs.inv.t` (存货绝对值) 确认 400 ValidationError 不支持。补 `models/financial.py` audit_opinion 字段 + `alembic s7_1_audit_opinion_field` migration + `financial_service.py` 3 字段映射 (含 metrics list 加 bs.ar.t + m.i_tor.t) + `red_flag_detector_service` 新增 `_check_non_standard_audit_opinion` 红旗 + `lixinger_client.get_financials` defaults 加 bs.ar.t。1126 测试通过 (+5)。原审计 78% 对齐度口径修正为 75% (3 红旗激活 + audit_opinion 新增,但 5 missed 概念文档化为限制)。详见 `docs/reports/completed/plan-invest-alignment-batch3-2026-06-17.md`。

**2026-06-17 (夜)**: invest1/2/3 对齐审计 Batch 2 ship (拓 schema)。实施 3 项决策: D2 新增 optionality_leader 策略 + moat_leader plan 激活 power_tier (选择权位阶); D3 拓 FinancialStatement 4 字段 + alembic s6_1_red_flag_fields migration + red_flag_detector_service 6 红旗 (商誉/OCF/分红可持续/应收/存货周转/非经常损益) + plan_runner 集成过滤; D4 新增 portfolio_risk_service 从 historical_klines 推算年化波动率/30-90日回撤/夏普代理 + Cockpit "组合风险"卡片。1121 测试通过 (+37)。Lixinger 字段键未 spike 验证 → graceful degradation (现有字段红旗立即生效,新字段等用户 spike)。详见 `docs/reports/completed/plan-invest-alignment-batch2-2026-06-17.md`。

**2026-06-17 (晚)**: invest1/2/3 对齐审计 Batch 1 ship。grill-me 会话对照 `docs/reference/invest{1,2,3}.md` 全面审计,产出 11 项决策 + 求字→选择权 命名重构 + 两批 ship 计划。Batch 1 (低风险高价值) 实施: D1 bank_select 加 bank_blind_box==可见 (顺带修 industry ["bank"]→["银行","bank"] 永不匹配 Lixinger 实际返回值的潜伏 bug) / D5 extreme_high 新开仓 warning→blocker (保留加仓赢家通道) / D6-A 新增 avoid_overvalued_tech 策略 + D6-B 验证中游 filter 已就绪 / D7-D10 文档化决策 / 命名重构 (字段名 power_tier 保留,UI/文档改"选择权位阶"文案)。1084 测试通过 (+9)。详见 `docs/reference/specs/2026-06-17-invest-system-alignment-audit.md` + `docs/reports/completed/plan-invest-alignment-batch1-2026-06-17.md`。

**2026-06-17**: Phase 2 #9 阶段 B v2 thesis monitor ship + Bug 1/2/3 修复。grill-me 会话产出 9 项决策 (严格 ship 口径 + 4 项产出物 + 4 source 单测补齐 + EventBus/handler/scheduler 3 项测试补齐 + Bug 1 P0 notification 修复 + Bug 2 dedup 干净验证 + dev server 3 场景截图 + STATUS/ADR/spec/reports/MEMORY 同步)。实施: Bug 1 (event_handlers.py 3 处 SystemAlert 字段不存在) 修复 → SystemAlert thesis 行 0→22 / Bug 2 不复现 (spike/dev 残留) / Bug 3 (cockpit theme_exposure schema mismatch 顺带修)。1075 测试通过 (+12)。dev session 验证: 工商银行 NIM 持续 2 期 1.2% < 1.3% → audit + EventBus + SystemAlert + dispatch_alert。⚠️ **2026-06-18 audit F13 复核**: 当时声称的"真实生产链路跑通"基于 dev session 临时数据,后续 DB 清空后 `audit_logs` / `system_alerts` 表 0 行 — dev session 截图不是持久化生产数据。代码链路本身通过 unit test 验证,但 end-to-end 持久化从未真实跑通。详见 `docs/reports/completed/plan-thesis-monitor-v2-2026-06-17.md` + `docs/reports/thesis-monitor-v2-acceptance-2026-06-17.md`。

**2026-06-15 (晚)**: 三层完成度审计 + Phase 2 commit。grill-me 会话产出三层审计报告 (Phase 2 未提交批次 / Phase 1 ship 清单 / P0 阻塞链),发现 7 个 bug + Sentinel Plan 是绕路 + STATUS.md 严重过期 + backtest 0-metrics 根因。Phase 2 commit `e0a915f` 落地: schema plan_id nullable + Sentinel Plan 移除 + 7 个 bug 修复 + 976 测试通过。详见 `docs/reports/2026-06-15-completeness-audit.md`。

**2026-06-15 (午)**: serenity-skill 集成 Phase 1 完成 + Phase 2 同期 ship。grill-me 会话产出 19 项决策 (Q1-Q9 核心架构 + Q10-Q19 实施细节),实施 7 张新表 / 10 个 API endpoint / 4 个 service / 异步 LLM 调用 + EventBus 告警 / Q14 反向链接 index / 34 个 Phase 1 测试 + 4 个 Phase 2 测试 (976 总通过)。Phase 2 包含: Candidate.source 区分来源 / plan_id nullable / Cockpit "今日 serenity" 卡片 + monthly_token_spend / StockDetail 反向链接 panel / Candidates source badge / `/api/health/zhipu` / LLM log dumping。GLM 账号余额不足阻塞 spike 真实验证,等充值后跑 2 次真实研究 (Phase 1 #9 唯一 external blocker)。详见 `docs/reference/specs/2026-06-14-serenity-skill-integration.md` + `docs/progress/2026-06-15-serenity-skill-integration.md`。

**2026-06-13**: production-readiness-plan 重审。grill-me 会话产出 7 项决策 (删 PROMOTE / 合并 EXECUTE / 保留 backtest / watchlist 去闸门 / 跳过 S6 / draft 全表现 / 双层闸门)。**实测发现 296 候选股被 watchlist 闸门静默吞掉 → 0 draft**。重审决策已全部落地 (`plan_runner.py:10-13` docstring 明示)。详见 `docs/reference/specs/2026-06-13-revisit-production-readiness-plan.md`。

**2026-06-12**: production-readiness S0-S5 全部 ship (trades / cash / T+1 / Lixinger 防御 / 公司行为 / 回测 / 盘中监控 / 通知)。S6 Docker/DR 重审后跳过。完整执行记录见 `docs/active/production-readiness-plan.md`。

**2026-06-11**: 第 6 轮全面深度审计,6 维度 32 项发现全部修复 (P0×5 + P1×15 + P2×12)。最严重的 P0 是 Plan DSL `_strategy_definitely_fails` 忽略 AND/OR 逻辑,导致 OR 预案完全失效。同步完成架构级重构 (自定义异常 / EventBus 异步 / 批量查询 / 33 端点补 response_model / domain dataclass 转 Pydantic)。详见 `docs/reports/completed/full-audit-round6-2026-06-11.md`。

**2026-06-09**: 数据管理模块精细化升级。新增 5 个 Tab (健康概览 / Pipeline 控制 / 股票池 / 质量评估 / 数据清理),14 个前端组件,3 个后端服务。sync 操作统一到 Pipeline 入口。详见 `docs/reports/completed/data-management-audit-2026-06-09.md`。

**2026-06-09**: 全链路可观测系统上线。装饰器驱动 + 模块级批量注入,158 个函数自动 instrument,前后端独立观测。详见 `docs/reference/specs/2026-06-09-observability-design.md`。

**2026-06-05**: 业务闭环 (分析→决策→持仓) 自动接力打通。详见 `docs/reports/completed/2026-06-05-business-loop-closure.md`。

### 5.3 待修复项 (从 roadmap.md + 2026-06-15 审计报告 摘录)

完整路线图见 `docs/active/roadmap.md`,审计报告见 `docs/reports/2026-06-15-completeness-audit.md`。

**P0 (2026-06-16 重排 — 阻塞真实使用)**:

- ~~**P0-1** 解 GLM 账号余额~~ ✅ **已充值并实测** (2026-06-16) — `spikes/glm_token_verification.py` 跑通 ping + structured 双 stage。Artifact: `backend/spikes/output/glm_token_verification_2026-06-16T05-55-01Z.json`。
- ~~**P0-2** 验证 Lixinger token~~ ✅ **已实测有效并 artifact 化** (2026-06-16) — `spikes/lixinger_token_verification.py` 跑通,500 股返回,首条 `920126 永大股份`。Artifact: `backend/spikes/output/lixinger_token_verification_2026-06-16T02-33-56Z.json`。
- ~~**原 P0-1** 修 backtest derived fields~~ ✅ **审计错误** (2026-06-15 晚) — `build_stock_context_at` 已计算 3/4 derived fields。600519 (茅台) 0 trades 是因为标的不匹配保守策略,**正确行为**。`dividend_sustainability` PIT 版本 2026-06-16 已实现 (3/4 因子,详见 P1)。
- ~~**Phase 1 spec ship 标准 #9** 真实研究 ≥ 3 次~~ 🟡 **部分完成** (2026-06-16) — Path B 两步法跑通 1 次 (run_id=6),15 真实 search_results / 86% evidence URL 来自 search / failure_conditions_md 基于真实证据。剩 2 次等用户主动触发或周度调度。

**已完成项 (从 P0/P1 移除)**:

- ✅ ~~P0-1 (旧) 解 Lixinger token~~ → 状态变化 (token 在 .env,有效性未验证)
- ✅ ~~P0-2 (旧) 跑首个 backtest~~ → 实测 3 runs 已跑 (但 metrics 全 0,见 P0-1 新)
- ✅ ~~P0-3 (旧) 去 watchlist 闸门~~ → 已完成 (`plan_runner.py:10-13`)
- ✅ ~~P1-1 删 PROMOTE 流程~~ → ship
- ✅ ~~P1-2 合并 EXECUTE+TRADE_ENTRY~~ → ship
- ✅ ~~P1-3 Cockpit draft 按 Qiu 排序~~ → ship
- ✅ ~~P1-4 强制 DisciplineChecklistModal~~ → ship
- ✅ ~~P1-5 CandidatesPage source filter UI~~ → ship (commit `e6e2518`)
- ✅ ~~P1-6 PIT `dividend_sustainability`~~ → ship (2026-06-16, 3/4 factor, max 80 分)

**P1 (架构改动 — Phase 2.5 / 下次 grill)**:

- ~~**P1-1** Phase 2 #9 — 失败条件 → 论点变量转译~~ ✅ **ship** (2026-06-16) — schema 改为 structured claims (subject/predicate/signal/outcome/stock_codes/layer_index),研究新表 research_claims。MD 字段 derive 保留作 backward-compat。实测 run_id=8 LLM 严格按 schema 输出,signal 字段质量极高 (e.g. "净息差<1.3%持续两个季度")。
- ~~**P1-2** Phase 2 #10 — 历史 Run diff 视图~~ ✅ **ship** (2026-06-16) — 3 维度 diff (ranking/claims/scarce_layers) + API endpoint + Drawer UI。实测 run 4 vs 8 (legacy 降级) 路径正常。⚠️ claims_diff happy path (两 Run 都有 structured claims) 需用户重跑一次 Path B 研究才能完整验证。详见 `docs/reference/specs/2026-06-16-phase2-num10-run-diff.md`。
- ⏭️ **P1-3** 配置 server_chan 通道 — 跳过 (2026-06-13 用户决策,基础设施类延后)
- ⏭️ **P1-4** 远程 Git 仓库 + push — 跳过 (2026-06-13 用户决策)
- ⏭️ **P1-5** CI (GitHub Actions) — 跳过 (2026-06-13 用户决策)

**P2 (体验补全)**:
- ~~**P2-1 [高]**: Phase 2 #9 阶段 B — thesis monitor 接入~~ ✅ **ship** (2026-06-17) — v2 14 项决策全落地 + Bug 1/2/3 修复 + 1075 测试通过 + dev session 截图 4 张 (⚠️ 2026-06-18 audit F13 发现"真实生产链路跑通"声明基于 dev 临时数据,DB 清空后 `audit_logs`/`system_alerts` 0 行,代码链路 unit test 覆盖但 end-to-end 持久化未真跑)。详见 `docs/reports/completed/plan-thesis-monitor-v2-2026-06-17.md` + `docs/reports/thesis-monitor-v2-acceptance-2026-06-17.md`。
- 月度复盘视图增强、预案 diff 视图、StockDetail 新建预案回填、候选池筛选持久化、统一 GLM model 配置 (3 个名浮动)

**P3 (技术债)**: holding_service 拆纯计算+持久查询两层、datetime.utcnow() → datetime.now(UTC)、前端 bundle 分块、STATUS.md 自动化生成

### 已知限制 (D8/D9/D10 + Lixinger 字段键 — 2026-06-17 invest-alignment audit)

- **D8 资产配置范围**: Gojira 定位为「个人**股票**自动驾驶舱」。房产/黄金实物/货币基金/债券基金**不在范围**。invest2 §23 加权 DYR 4-5% 已实现 (`holding_service.target_weighted_dyr=0.045`),是非股票资产可量化部分。invest2 §23 顺周期/逆周期/困境反转/金融 4 块分类**不引入 Plan.cyclicality 字段**——`Plan.theme_id` (能源/资源/金融/粮食安全) 已提供类似维度。
- **D9 100 万门槛**: invest2 §24 是元层面建议 (劳动收入 vs 投资权重),非交易规则。不机械实现,用户自行判断本金状态。
- **D10 EPS 真相 (永续债/优先股)**: Lixinger 标准 API 不提供永续债利息 / 优先股股息细分 (银行/地产年报附注才披露)。`adjusted_eps` 未实现。用户需手动查年报附注。
- **进度条战法 / 治理瑕疵 / 60% 分红承诺 / 数人头量化 / 个股周期拐点** (Batch 3 grill 2026-06-17): invest1/2/3 五大概念 Lixinger 不提供数据维度 (矿权进度/减持公告/分红承诺/门店数/商品价格)。架构尽可能简化原则下不扩数据源,文档化为已知限制。
- **D3 红旗数据源 (Batch 3 ship 2026-06-17)**: spike `backend/spikes/probe_redflag_metrics.py` 验证后,6/7 红旗生效 (goodwill + OCF/NI + dividend_sustainability + **ar_growth + inventory_turnover_drop + non_standard_audit**)。`non_recurring_dominant` 红旗是死代码:Lixinger fs 端点不支持 `ps.np_wd_s_r.t` (扣非净利率) — 保留检测器作为设计意图。`auditOpinionType` 是 Lixinger top-level 字段 (非 metric key),`financial_service.py:164` 已映射到 `audit_opinion` 列。
- **D6 invalidation 架构** (Batch 3 决策 2026-06-17): `plan.invalidation:[]` schema 字段保留但**不启用**。中游非成本龙头过滤走 `plan_runner._should_filter_as_midstream_non_leader` 代码路径 (line 127-151),`disable_midstream_filter=False` 默认开启。红旗过滤走 `plan_runner.red_flag_count > 0` 检查 (line 635/661)。两条代码路径而非 `invalidation` schema,因为代码已 ship 且测试覆盖;重构 schema 表达需 1-1.5 天且无功能增量。
- **资源股 7 维实际 6 维**: `resource_hard_asset` 策略 6 个 condition 覆盖 invest3 §12 7 维中的 5 维 (资源禀赋/估值/股息/地缘/扩产)。缺成本 (cost_leader) 与管理 (management quality) 两个细分维度作为已知限制。
- **M6 行业第一性原理公式化** (Batch 5 grill 2026-06-17): invest1 第5-8章 行业公式 (煤油比价/铝产业链期权价值/磷矿景气度) 未公式化,`BusinessPattern.first_principle_variable` 仅字符串描述。Lixinger 不提供商品价格 series;Batch 4 N3 thesis_variables 已部分覆盖 (煤价/油价/磷矿价 manual 变量)。用户读字符串自行判断阈值。
- **M7 避坑指南伪逻辑识破** (Batch 5 grill 2026-06-17): invest1 附录"利用常识识破高大上的伪逻辑"是元层面心法,无机械规则。已被 D3 财报红旗 + D6 中游排除覆盖部分,剩余"高大上叙事"属纯认知问题,跳过。

### Batch 5 ship (2026-06-17 invest-alignment 3rd grill) — 6 项实质 + 1 命名重构

3rd grill-me 聚焦"前 4 批漏检项",产出 8 项决策:

| ID | 决策 | 涉及 |
|---|---|---|
| **Q2** | `Stock.tier` 字段值 `watch` → `satellite` (专业金融名词,Core-Satellite Model) | `stock.py` + alembic s9_1 + `builtin_seeder.py` + 前端 4 处 |
| **M1** | DisciplineChecklist 加 3 条心法闸门 (a/b/c) + `cockpit_service.psychology_alerts` 回本强迫症检测 | 前端 DisciplineChecklistModal + cockpit_service |
| **M2** | 新增 `Stock.in_circle: bool` (默认 False) + UI toggle + plan_runner filter + `Plan.disable_in_circle_filter` 逃生口 | `stock.py` + alembic s9_1 + `plan_runner.py` + `plan.py` model + 前端 |
| **M3** | DisciplineChecklist 扩到 5 条 (加 d 反损失厌恶 / e 反锚定) + `cycle_assessment.extreme_low/extreme_high` 非阻塞 banner | 前端 + cockpit_service |
| **M4** | thesis breach → EventBus → `draft_service.create_thesis_breach_sell_draft` 自动 SELL draft + supersede 该 stock pending BUY drafts (渣男理论) | event_handlers + draft_service + Draft.plan_id nullable (alembic s9_2) |
| **M5** | `position_advisor` 加 `MAX_SINGLE_BY_TIER={'core':0.5,'satellite':0.1,None:0.5}` + `TOTAL_SATELLITE_MAX=0.20` | position_advisor_service + plan_runner `_compute_suggested_buy_quantity` tier-clamp |
| **M6+M7** | 跳过 + 文档化 (见上) | STATUS.md |
| **Q9** | 单 Batch 5 一个 commit,7 步实施 | — |

**Batch 5 新增测试**: 14 个 (M2 filter 4 / M4 thesis breach 6 / M5 tier-aware 4)

**对齐度评估**: Batch 4 后 ~80% → Batch 5 后 ~86-88% (3 个新维度激活: 心法 / 能力圈 / 渣男换股 + 2 个补齐: extreme_low 布局 / satellite 仓位上限)

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
10. **Serenity 集成 19 项决策 (2026-06-14)**: Q1-Q9 核心架构 (B 完整工作流 / A 新 ResearchTheme / D 6 张表 + 手动导出 / D LLM Web Search / GLM-5.2 / D 手动+可选调度 / D 多入口 UI / C 硬约束+软上限 / D spike 先验证) + Q10-Q19 实施细节 (异步 ThreadPoolExecutor / 不查 Checklist / 跳过 failed / 三重硬约束 / index 反向链接 / Phase 1 仅列表 / 不抽 LLMProvider / 复用 NotificationChannel / react-markdown / 失败条件 Phase 2 不做)。详见 `docs/reference/specs/2026-06-14-serenity-skill-integration.md`。
11. **Candidate.plan_id nullable (2026-06-15 Phase 2)**: Phase 2 临时用 Sentinel Plan 绕开 FK NOT NULL,审计后发现是绕路非 spec。改为 `plan_id nullable` (s2 migration),serenity Candidate 写 NULL,rule_based Candidate 业务层校验必须有 plan_id。删除 `_get_or_create_serenity_export_plan` 全部复杂度。
12. **~~Backtest derived fields 是已知限制,不是 bug~~** (修正于 2026-06-15 晚): 原审计错误地认为 `backtest_engine.py:30-35` docstring 反映现状。实测 `point_in_time_context_service.build_stock_context_at` **已经计算** 3/4 derived fields (pe_pct_10y / pb_pct_10y / price_drop_pct / ocf_to_ni)。docstring 是过期的,本次同步修正。只有 `dividend_sustainability` 缺失 (需历史分红事件表),影响 2/6 策略 (高股息安全垫 / 超跌逆向)。600519 (茅台) 0 trades 是因为标的不匹配任何保守策略 (PE/PB 分位 0.51 + DYR 0.024),**正确行为**。详见 `docs/reports/2026-06-15-completeness-audit.md` 文末"审计错误更正记录"。
13. **Thesis Monitor v2 双源不复制 + breach_when 机械字段 (2026-06-17 Phase 2 #9 阶段 B v2)**: `research_claim_variables` 表与 `thesis_variables_json` 各为真相源,monitor 跑两个 check 函数 (check_held_stocks + check_claim_variables),approve 不复制 JSON。`breach_when: "lt"|"gt"` 字面对齐 signal 文本比较符 (替代易错的 `direction`)。独立 `thesis_evaluation_job` (17:32 mon-fri,避让 alert_evaluation 17:30) + `last_alerted_at` 7 天 dedup。Bug 1 教训: SystemAlert 模型字段是 `severity/category/message/detail_json`,event_handlers.py 创建时勿用 `title/source/payload/triggered_at` (会被 broad except 静默吞掉,notification 链路全断)。详见 `docs/reference/specs/2026-06-16-phase2-num9-stage-b-thesis-monitor.md` + `docs/reports/completed/plan-thesis-monitor-v2-2026-06-17.md`。

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
