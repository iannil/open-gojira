# Gojira v2 架构与进展全景（LLM 友好）

> **用途**：给接手的 LLM / 人类一份「读完即可迭代」的 v2 当前真相。
> **配套**：`docs/progress/STATUS.md`（高频快照）· `docs/standards/trading-philosophy.md`（交易思想权威）· `docs/active/redesign-decisions-v2.md`（26 决策工程锚点）· `docs/active/v2-implementation-plan.md`（8-Phase 蓝图）· `memory/MEMORY.md`（沉积记忆）。
> **最后更新**：2026-06-26（v2 大重写 2026-06-24 起；纸面交易 P0 后端闭环完成）。

---

## 0. 一句话定位

Gojira 是**个人 A 股自动驾驶舱**：规则筛选 + LLM 深度研究 + 规则/人工审批的混合架构，把「选股 → 深研 → 买卖草稿 → 持仓审计 → 论点跟踪」全流程自动化，**唯一不自动的是券商真实下单**。数据源 Lixinger（理杏仁）+ Zhipu GLM web_search。

## 1. v1 → v2 发生了什么（必读）

2026-06-24 起进行了一次**大重写**，删除了整个 v1「规则策略引擎」范式：

| v1（已删除） | v2（现行） |
|---|---|
| Strategy / Plan / Candidate DSL（`strategy_engine`/`plan_runner`/`builtin_seeder`） | 双引擎选股 + LLM `deep_research` 出报告 |
| `WatchlistItem` 手动股池 | `StockLifecycle` 状态机（观察池/候选/持仓） |
| `Holding` 模型（独立持仓表） | 持仓/盈亏 = `Trade` 账本派生（`position_service`，`holdings` 表已删，migration `v2_4`） |
| 多渠道通知 `NotificationChannel` | 仅 in-app `system_alert`（`notification_service.dispatch_alert` 现为 no-op） |
| 止损/再平衡 service | 不做止损；卖出走 4 信号触发 |
| invest{1,2,3}.md 散落约定 | `trading-philosophy.md` 双引擎权威 |

> **陷阱**：旧文档（被本轮纠正前的 STATUS/CLAUDE/roadmap）仍描述 v1，且引用已不存在的 `docs/reference/specs/`、`invest{1,2,3}.md`。遇到这些名字一律视为历史。

## 2. 双引擎交易体系（来自 trading-philosophy.md）

- **两条独立选股来源，不互相裁决**：
  - **价值复利引擎**（ai-berkshire 四大师：段永平/巴菲特/芒格/李录）→ `quality_screen` sourcing。
  - **产业链卡点引擎**（serenity 产业链卡点）→ `theme_scan` sourcing。
- **hybrid 汇合**：serenity 决定 WHICH（选股），ai-berkshire 决定 PRICE+RISK（估值 + 8 红线）→ 汇成一张草稿。
- **评分 hybrid**：LLM 算分=advisory，**Python 按 source profile 复核为权威分**（`app/core/scoring_config.py` 的 `PROFILE_WEIGHTS`，quality_screen 偏复利 / theme_scan 偏主题：李录降权 + 卡点维度）。
- **三层去重**（防同一信号被多师重复计分）：① 持久优势三镜（卡点≈护城河≈好生意）同源整师折叠；② 证据分级两层（条目 strong/med/weak/lead + 包级 A/B/C）；③ serenity 失败条件并入芒格 `failure_scenarios`。
- **防御三层**：Prompt 约束 + 代码后验（单股 ≤5%）+ Pipeline 熔断（冲突率 >20%）+ **8 条红线否决**。
- **预算**：生产 $150/月硬熔断 + 测试 $100/月（`cost_tracker`）。

## 3. 后端架构（Routers → Services → Models + Schemas）

实测计数（2026-06-26）：**22 routers · 36 services + llm(10) + pipelines(11 + pipelines/llm 6) · 27 models · 21 schemas · core(14) · 3 alembic 迁移**。

### 3.1 Routers（22，`app/routers/`，全部在 `app/main.py:225-246` 注册）

| Router | 职责 |
|---|---|
| `health` | DB / Lixinger / Zhipu 三层健康探针 |
| `stocks` | Lixinger 个股数据（基础/K线/股东/北向/营收等） |
| `valuation` | PE/PB 10y 分位 + DYR |
| `financial` | 财报 + 比率 |
| `dividend` | 分红同步 + 汇总 |
| `portfolio` | 持仓汇总（派生自 Trade） |
| `market` | 大盘指数 + 周期评估 |
| `trades` | 交易记账（唯一写持仓的入口） |
| `cash` | 现金余额 + 出入金调整 |
| `fee_configs` | 券商费率配置 CRUD |
| `corp_actions` | 公司行动（送转/派现/退市） |
| `drafts` | 订单草稿 应买/应卖 execute/cancel（execute 回填实际价→Trade） |
| `cockpit` | 信号优先单看板聚合（v2 dashboard） |
| `research_v2` | **v2 LLM 深度研究**：`POST /api/research/{code}` + latest/history/reports/health |
| `theme_scan` | **v2 产业链主题扫描**（serenity sourcing） |
| `alerts` | 告警规则 + 事件总线 |
| `system_alerts` | in-app 系统告警（信号/调度/基础设施） |
| `notifications` | 通知（外部渠道已弃用，留壳） |
| `scheduler` | 调度任务管理 + 手动触发 |
| `data_management` | 数据同步 / Pipeline / 股票池 / 质量 / 清理 |
| `audit_log` | 结构化审计日志 |
| `observability` | Trace / Span / Event 查询 |

### 3.2 关键 Services（`app/services/`）

- **LLM 层 `app/services/llm/`（10）**：`client`（Anthropic/GLM 抽象 + @tracked + 缓存 + 重试 + watchdog 超时）、`zhipu_client`、`cost_tracker`（$150 硬熔断）、`conflict_validator`（PE/PB/dyr 5% 后验）、`red_line_checker`（8 红线）、`scoring`、`prompt_loader`/`prompts`、`deep_research_schema`、`theme_scan_schema`。
- **Pipeline 框架 `app/services/pipelines/`（11）**：`manager`（编排 + stale 恢复）、`base`/`checkpoint`/`dead_letter`/`metrics`/`throttler`（基础设施）、`{dividend,financial,kline,valuation,universe_bootstrap}_pipeline`（5 个数据 Pipeline）。
- **LLM Pipeline `app/services/pipelines/llm/`（6）**：`quality_screen`（价值复利筛选）、`deep_research`（4 大师并行 + Team Lead 综合，6 LLM 调用/家，JSON+Markdown 双输出）、`thesis_tracker`（持仓论点周跟踪 VALID/WARNING/INVALIDATED）、`news_pulse`（异动归因）、`earnings_review`（财报精读）、`theme_scan`（产业链主题）。
- **交易/持仓**：`position_service`（**唯一持仓真相源**：移动加权成本 / 已实现+浮动盈亏 / T+1 冻结）、`trade_service`（`record_trade` 唯一写入口）、`draft_generator`（BUY 草稿生成 + 触发条件 D + 仓位 10/30/20 + TTL 7 天）、`draft_service`（execute/supersede）、`fee_calculator_service`、`holding_service`（汇总查询）。
- **股票生命周期**：`lifecycle_service`（`StockLifecycle` 状态机 + 30 天 re-research 缓存）。
- **数据接入**：`lixinger_client`（唯一外部源）、`data_service`、`stocks_sync_service`、`deep_sync_service`、`kline_service`、各 `*_service`、`universe_service`、`trading_calendar_service`、`realtime_quote_service`、`corp_action_sync/processor_service`。
- **数据校验（边界待澄清，见审计报告）**：`data_quality_service` / `data_sanity_service` / `data_freshness_service` / `price_validator_service`。
- **告警/审计**：`system_alert_service`（in-app 告警，含 signal 类）、`alert_service`、`audit_log_service`、`scheduler_alerting`、`scheduler_config_service`、`notification_service`(no-op)。

### 3.3 Models（27，`app/models/`）

- **v2 新表**：`stock_lifecycle` / `research_report` / `theme_scan_report` / `decision_audit` / `llm_call_log` / `red_line_event`。
- **交易**：`trade` / `cash_balance` / `cash_adjustment` / `broker_fee_config` / `draft`（Phase 5 字段：`trigger_source`/`strategy_tier`/`sizing_logic`/`expires_at`/`status`）。
- **数据**：`stock` / `valuation` / `financial` / `historical_{financial,kline,valuation}` / `price_kline` / `dividend` / `corp_action` / `trading_calendar` / `data_freshness` / `pipeline`。
- **支撑**：`alert` / `system_alert` / `audit_log` / `scheduler_config`。
- **已删**：`Holding`（`v2_4`）/ `Plan` / `Candidate` / `Strategy` / `Theme` / `WatchlistItem` / `CashflowGoal` / `SchedulerJob`(旧名)。

## 4. 前端架构（feature-based）

`src/pages/*` 是 **1 行 re-export shim**，真实实现在 `src/features/`。路由见 `src/App.tsx`，导航分组见 `src/components/Layout.tsx`（入口/研究/数据/执行/自动化，品牌「Gojira 自动驾驶舱 v2」）。

| 路由 | 实现 | 状态 |
|---|---|---|
| `/` | `features/cockpit/CockpitPage` | ✅ 信号优先 dashboard |
| `/universe` | `features/universe/UniversePage` | ✅ 全市场筛选 |
| `/reports` | `features/reports/ReportsPage` | ✅ 研究报告 master-detail + markdown |
| `/stock/:code` | `features/stock-detail/StockDetailPage` | ✅ 研究触发 + K线 + 论点变量 |
| `/trades` | `features/trades/TradesPage` | ✅ 交易账本 + 出入金 |
| `/data-management` | `features/data-management/DataManagementPage` | ✅ 数据同步/清理/健康 |
| `/scheduler` | `features/scheduler/SchedulerPage` | ✅ Cron 配置 + 执行历史 |
| `/monitoring` | `features/monitoring/MonitoringPage` | ✅ 通知渠道 + 风控规则（内嵌 alerts tab） |
| `/drafts` | `features/drafts/DraftsPage` | ⚠️ **stub**（"v2 待重建"，Phase 3 占位） |
| `/__primitives__` | `pages/__primitives__` | dev-only |

- **API 客户端**：`src/api/client.ts`（122 函数，含 serenity research 块）+ `src/api/research.ts`（5 个 v2 research 函数）+ `src/api/types.ts`（177 类型）。两套 research 命名（serenity `client.ts` + v2 `research.ts`）并存——见审计报告。

## 5. 数据流与事件链

```
全市场 universe
  │ quality_screen / theme_scan（双引擎 sourcing）
  ▼
StockLifecycle: 观察池(30-50) → 候选(3-5)
  │ deep_research（4 大师并行 + 综合 + 8 红线 + 5% 冲突后验）
  ▼
research_report（BUY/HOLD/SELL + failure_scenarios）
  │ draft_generator（触发条件 D：价格入区间 + 论文健康 + 组合有空间）
  ▼
Draft（应买，TTL 7 天，仓位 10/30/20）
  │ 用户 execute → 回填实际价 → trade_service.record_trade
  ▼
Trade 账本 → position_service 派生持仓/盈亏
  │ thesis_tracker（周跑）→ INVALIDATED
  ▼
应卖 Draft（100% SELL + supersede pending BUY）
```

**EventBus（`app/core/events.py` + `event_handlers.py`，异步非阻塞）**：数据到达 / 论点告警 / 审计的自动响应链。新买卖 draft → `system_alert(category=signal)` 仅 in-app 提醒「应买入/应卖出…回填成交」。

**卖出 4 信号**（不做止损）：① 论点证伪（优先）② 估值 1.3x 止盈 ③ 仓位 15% 超限 ④ 基本面恶化（news_pulse）。建议卖价 = 风控类用现价 / 止盈类用公允 × 1.3。

## 6. 调度任务（`app/scheduler.py`，APScheduler @ Asia/Shanghai，默认 `SCHEDULER_ENABLED=false`）

**live JOB_REGISTRY（scheduler.py:932-952）**：数据同步（`daily_universe_bootstrap`/`daily_base_sync`/`daily_deep_sync`/`daily_snapshot`/`daily_kline_sync`/`daily_prev_close_sync`/`monthly_dividend_sync`/`quarterly_financials_refresh`/`quarterly_shareholders_refresh`/`weekly_dividend_sync`/`daily_corp_action_apply`）+ `alert_evaluation` + `intraday_price_poll` + `pipeline_stale_sweep` + `daily_draft_generation` + **v2 LLM**：`v2_quality_screen_weekly` / `v2_deep_research_weekly` / `v2_thesis_tracker_weekly`。

> ⚠️ **已知隐患（见审计报告）**：scheduler.py 仍残留大量 v1 孤儿 job 函数（`daily_plan_evaluation_job`/`thesis_evaluation_job`/`research_stale_sweep_job` 等），其中多个引用**已删除模块**（`watchlist_service`/`plan_runner`/`ResearchRun`）。部分**在 registry 内**的 job（如 `daily_kline_sync` → `_watched_and_held_codes` → 未导入的 `watchlist_service`）存在 **latent NameError**。因 scheduler 默认关闭未暴露，列为 P3 待修。

## 7. 实施进度矩阵（对照 v2-implementation-plan 8 Phase）

| Phase | 内容 | 状态 |
|---|---|---|
| 0 | Foundation：删 v1 + v2 骨架 + DB 重写 | ✅ |
| 1 | LLM 基础设施（client/cost_tracker/conflict/red_line + 5 ORM） | ✅ |
| 2 | 首 Pipeline 闭环（deep_research 端到端 + research API/CLI） | ✅ |
| 3 | Dashboard MVP（Cockpit 信号优先 + Reports + StockDetail 触发） | ✅ |
| 4 | 完整 Pipeline 套件（5 LLM pipeline + 事件 + 调度） | ✅ 实现（接线度量待 P2） |
| 5 | Draft 生成 + 卖出触发（draft_generator + sell 4 信号） | ✅ 后端闭环（P0-1~P0-4） |
| 6 | 度量系统（Tier 1/2/3 + 熔断 + 监控页） | ⏳ 待办 |
| 7 | 测试与 Eval Set（20-30 家评估集 + snapshot + E2E） | 🟡 部分（单元/集成有，Eval Set 待建） |
| 8 | 部署上线（docker dev/prod + 备份 cron） | 🟡 部分（compose 存在，未 cutover） |

**纸面交易评估闭环（2026-06-26 grill 锁定，6 决策）**：P0 后端闭环全部完成（position_service 真相源 + execute 回填 Trade + thesis INVALIDATED→SELL draft + 新买卖 draft→signal alert）。**待办**：P0 前端 UI（drafts 页 + 确认成交弹窗 + cockpit 信号区）；P1 评价系统四层指标（组合 / vs 沪深300 / 夏普·交易·双引擎归因[只算 source_ref 非空] / 信号质量滑点）；P2 估值止盈·仓位超限·news/earnings 接线；P3 删 scheduler v1 孤儿 job。

## 8. 仍生效的关键约束 / 坑（从 MEMORY 经验教训提炼）

- **GLM SDK httpx timeout 失效**：SSL「连接开但无数据」会永久阻塞，须 ThreadPoolExecutor + `future.result(timeout=N)` 在 Python 层强制超时（v2 `LLMClient` 已遵循）。
- **APScheduler `day_of_week` 是 0=Mon 不是 0=Sun**：`CronTrigger.from_crontab()` 不翻译，crontab `1-5` 会错位一天。
- **Lixinger 不提供 stock_code → 申万行业映射**（F20）：需 AkShare 才能彻底修；draft 行业闸门因此有意跳过。
- **测试隔离要看 `SessionLocal` 不只 `get_db`**：scheduler jobs / event_handlers / pipeline manager 直接用 `SessionLocal()`。
- **持仓权重基数统一用市值**（current_value），不用成本基数。
- **时区**：DB 存 naive 北京时间；手动 raw SQL 用 `datetime('now','+8 hours')`（见 `datetime_utils.beijing_now_sql`），勿用裸 `datetime('now')`（差 8h）。
- **Alembic 已 squash 为单一基线** `v2_baseline_squash`（down_revision=None，从 `Base.metadata` 建全量）。现有 DB 须 `alembic stamp v2_baseline_squash --purge` 一次。
- **测试通过 ≠ 真实链路跑通**：ship 必须真实 DB 端到端验证。
- **大重写后必须跑全套测试 + 逐 live 服务 grep 已删模块引用**（v1-leftover 靠惰性 import/try-except 掩盖崩溃）。

## 9. 给下一个迭代者的入口指引

- 想**改交易思想/评分** → `docs/standards/trading-philosophy.md` + `app/core/scoring_config.py` + `app/services/llm/scoring.py`。
- 想**改某条 LLM Pipeline** → `app/services/pipelines/llm/{name}_pipeline.py` + `app/prompts/{name}/`。
- 想**追任何代码的设计依据** → `docs/active/redesign-decisions-v2.md`（26 决策）；追不到说明是 over-engineering。
- 想**做下一步** → `docs/active/roadmap.md`（近期优先级）+ 本文 §7 矩阵。
