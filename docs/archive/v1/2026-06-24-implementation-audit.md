# Gojira 实现审计报告(2026-06-24)

> **日期**: 2026-06-24
> **状态**: 进行中(审计完成,待用户决策执行优先级)
> **评判锚点**: `docs/active/redesign-decisions.md`(14 条决策)+ ADR-0002 ~ 0006
> **范围**: backend(31 routers / 79 services / 42 models / 24 crons)+ frontend(17 pages / 141 tsx)+ infra(50 migrations / 4 主文档 / 3066 行)

## TL;DR

对照 14 条决策审计现有实现,发现:

- **可删除约 5,000 LOC**(后端 serenity + intraday + business_pattern + risk_rule + fee_config)
- **3 个 Phase 1 P0 缺口**(决策 3/4/11 明令的 UI/字段完全没实现)
- **24 cron 可瘦到 18**(删 3、简化 3)
- **4 主文档 3066 行大部分失效**(STATUS / roadmap / production-readiness / project-state)
- **50 alembic migrations 维持现状**(生产 DB,squash 风险 > 收益)
- **models 可从 42 瘦到 ~30,services 从 79 瘦到 ~65**

砍伐优先级按 ROI 排序(下一节)。

---

## 一、删除清单(remove,高置信度)

这些功能**不服务任何决策**或与决策**直接冲突**,删除收益明确。

### 后端

| # | 模块 | 规模 | 违反决策 | 证据 |
|---|---|---|---|---|
| R1 | **serenity research 全模块** | 10 表 + ~2,900 LOC + GLM SDK + 2 cron | 决策 2(时间痛点) | LLM 研究**消耗**时间(还要人审 claim_variable approve/reject)。invest{1,2,3} 是*人*的研究体系,LLM 代跑产生代理风险。决策 6 maximal 数据已覆盖筛选 |
| R2 | **intraday_monitor + intraday_price_poll** | 2 cron + intraday_monitor_service + stop_loss_service | 决策 4(daily+weekly) | 盘中 5min 轮询与 weekly review 节奏直接冲突。决策 8 已声明无组合熔断,stop_loss 是「纪律官」延伸 |
| R3 | **broker_fee_config + fee_configs router + fee_calculator_service** | 1 表 + 1 router + 1 service | 决策 1/11 + 不真实下单 | 单用户 + 全手动 + paper draft,fee 算给谁看?trade 写入时算 fee 没消费者。trade_service 内保留 1 个 hardcoded 默认费率常量即可 |
| R4 | **holding_risk_rule + risk_rules router + stop_loss_service**(同 R2) | 1 表 + 1 router + 1 service | 决策 8 | per-position trailing stop 同属组合熔断范畴,Phase 1 无组合熔断。删后 thesis_monitor 仍保留(论点越界检测) |
| R5 | **business_pattern 推断** | 1 表 + 349 LOC service + 1 router + 1 cron(`weekly_business_pattern_inference`) | 无决策锚点 | grill 已点名「invest 映射里没看到强映射」。plan_runner / strategy_engine 都不消费它。删后 thesis_variable_sync / stocks_sync 同步逻辑顺手清理 |
| R6 | **thesis_variable_proposal_service** | 347 LOC | 决策 2 | EventBus handler 调 LLM 生成论点变量提议,与研究模块同理——LLM 介入投资判断 |

**删除合计**:约 5,000 LOC + 6 表 + 3 cron

### 前端

| # | 页面/组件 | 规模 | 违反决策 | 证据 |
|---|---|---|---|---|
| F1 | **BusinessPatternsPage + features/business-patterns/** | ~543 LoC | 无决策锚点 | 后端 R5 删除后前端配套失去意义;与 serenity 公司宇宙功能重叠 |
| F2 | **SerenitySummaryCard(in CockpitPage)** | ~70 LoC(1385 行卡片块) | 决策 2 时间痛点 | LLM 摘要塞进首屏 HUD,违反「时间 > 纪律」;随 R1 删除 |

### 基础设施

| # | 项目 | 违反决策 | 证据 |
|---|---|---|---|
| I1 | cron `intraday_monitor` `*/5 9-14 * * 1-5` | 决策 4 | 默认已关,删影响为 0 |
| I2 | cron `intraday_price_poll` `*/5 9-14 * * 1-5` | 决策 4 + 10 | 与 intraday_monitor 职责重叠;决策 10 事故不含盘中止盈 |
| I3 | cron `weekly_business_pattern_inference` | 无决策 | 对应 R5 |

---

## 二、简化清单(simplify,服务决策但实现过重)

### 后端

| # | 模块 | 规模 | 服务决策 | 简化建议 |
|---|---|---|---|---|
| S1 | **historical_klines / historical_valuations / historical_financials** 3 表 | 3 表 + 800 LOC + pipeline + point_in_time_context_service | 决策 9(backtest) | 与 price_klines/valuations/financial_statements 重复存历史。**Phase 1 只保留 historical_klines**(backtest 必需),valuation/financial PIT 用快照表 publish_date 过滤临时拼。Phase 2 视情况恢复 |
| S2 | **backtest_engine + simulator + metrics + router** | ~1,000 LOC | 决策 9 | 现状是「独立运行」引擎,决策 9 要求**强制 gate**(plan→paper 前置)。删 router ad-hoc 入口,改为 plan_service 内部 API |
| S3 | **notification_channels + notifications router + 4 通道实现** | 1 表 + 1 router + service(server_chan/email/dingtalk/telegram) | 决策 10(只 macOS) | 决策 10 明令「macOS + webhook 扩展口」。**保留**: macOS + in_app(SystemAlert)。**移除**: 4 通道实现 + severity_filter 字段(改硬编码 6 类事故) |
| S4 | **alert_rules 用户自定义告警 + sync_stop_profit_rules_from_holdings** | model + alert_service 386 LOC + holding_service 同步逻辑 | 决策 4/10 | 决策 10 重定义事故为窄义 6 类,用户自定义 AlertRule(止损/止盈/价格)是「纪律官」遗留。**保留**: system_alert 自动检测。**移除**: 用户手动配 AlertRule 入口 + sync_stop_profit |

### 前端

| # | 页面/组件 | 规模 | 服务决策 | 简化建议 |
|---|---|---|---|---|
| S5 | **CockpitPage** | 1,385 LoC + 10+ 卡片 | 决策 4(HUD) | 当前塞了 serenity 摘要 / corp_actions / 4 种风险指标 / 象限 pie / 主题偏离 / 论点告警。**精简到核心**: GoalNav + Cycle + Drafts(WeeklyBatch) + Holdings + WorkerHeartbeat + Alerts。砍 SerenitySummaryCard / ThemeExposure / QuadrantPie / PendingCorpActionsCard(defer) |
| S6 | **MonitoringPage** | ~784 LoC(ChannelsTab 220 + RiskRulesTab 209 + AlertsTab 145 + 主页 76 + 子组件 134) | 决策 10(部分) | ChannelsTab(webhook/邮件配置)+ RiskRulesTab(止损止盈规则编辑)在「macOS only + 决策 8 无组合熔断」下大量功能 dead。**瘦身到 alerts-only**,保留 AlertsTab |
| S7 | **DisciplineChecklistModal** | 183 LoC + 11 个 manual checks(M1A/M1B/M3D 等) | 决策 2/3 | 决策 2 时间痛点下,11 个 checkbox 是典型纪律税。**精简到 4 个 auto + 3 个核心 manual**;决策 3 要求 per-plan 翻 auto 时砍,需先补 toggle(S8) |

### 基础设施

| # | 项目 | 服务决策 | 简化建议 |
|---|---|---|---|
| S8 | cron `pipeline_stale_sweep` `*/15 min` | 决策 7 | 拆 worker 后 L9 根因(reload 杀线程)消失,sweep 仅防 worker 进程内 OOM。**从 15min 放宽到 1h** |
| S9 | cron `weekly_rebalancing_review` `0 10 * * 0` | 决策 4 | weekly review 是用户操作**不是 cron**。降为 on-demand 或合并到 WeeklyBatchReview 视图 |
| S10 | cron `monthly_thesis_variable_sync` `0 4 1 * *` | — | 仅服务 thesis_variables_json(已被 thesis_evaluation 覆盖)。**降到季度或合并** |

---

## 三、Defer 清单(服务决策但非 Phase 1 必须)

### 后端

| # | 模块 | 规模 | 服务决策 | Defer 理由 |
|---|---|---|---|---|
| D1 | **cash_adjustment** model + 路径 | 1 表 | 决策 1/11 | 单用户全手动下「手动调现金余额」可有可无,Phase 1 走 CashBalance 直接读 trade_service |
| D2 | **draft_matcher_service**(backfill-suggestion) | 1 service + 1 endpoint | 决策 3 | Phase 1 manual 下合理,Phase 2 auto-execute 后 trade 直接从 draft 生成,**不需回填**。Phase 1 保留 Phase 2 砍 |

### 前端

| # | 页面/组件 | 规模 | Defer 理由 |
|---|---|---|---|
| D3 | **ResearchThemesPage + ResearchThemeDetailPage + RunDiffDrawer** | ~1,334 LoC | serenity 模块(R1)删除则整套消失;若 R1 改为 defer 则前端一并 defer。**等 R1 决策** |
| D4 | **QiuScorerWizard** | 126 LoC | invest1 §Qiu 三维评分,无决策直接引用;若 serenity defer 一并 defer |
| D5 | **PendingCorpActionsCard** | 200 LoC | 依赖 `corp_actions` 表(README L2 标 0 行)。Phase 1 数据未到位前移除 |
| D6 | **stock-detail/components/**(ClaimVariablesCard / ThesisVariablesModal / EditClaimVariableModal) | ~500 LoC | 耦合 serenity 研究表。R1 决策后同步处理 |

---

## 四、Phase 1 P0 必做缺口(决策明令但零实现)

审计发现 3 个**决策明令 Phase 1 必做**的功能,当前前端**零实现**(grep 全部 0 命中)。这是**必须立刻补**的,否则决策 3/4/11 落不了地。

| # | 缺口 | 决策来源 | 现状 | 必须做 |
|---|---|---|---|---|
| **P0-1** | **`Plan.auto_execute_enabled` toggle UI** | 决策 3(ADR-0002) | 前端零引用,PlansPage/CockpitPage 都没给 per-plan auto 开关 | ① 后端加字段 + alembic migration;② PlansPage 加 toggle;③ draft_service 代码路径分 manual/auto;④ DisciplineChecklistModal per-plan 绕过逻辑 |
| **P0-2** | **Cockpit `WeeklyBatchReview` 视图** | 决策 4 | Cockpit 现状是「日内 HUD」,没有 weekly batch 操作流 | 新增视图:聚合 5 天 drafts,按 qiu_score/紧急度排序,支持批量 execute/cancel/force |
| **P0-3** | **Cockpit `WorkerHeartbeatCard`** | 决策 11(ADR-0006) | 完全缺失。manual 运维下唯一的 worker 存活可视化 | ① worker 每 60s 写心跳到 DB;② Cockpit 卡片显示「最后心跳/存活」;③ 决策 10 事故 #6 检测逻辑 |

**这 3 个缺口是审计最重要的产出**——不是砍什么,而是「决策要求的关键功能根本没做」。如果不补,Phase 1 跑不起来(无法观测 worker、无法 batch review、Phase 2 无法 per-plan 翻 auto)。

---

## 五、Keep 清单(高价值,不动)

直接服务某决策,**不**列入简化:

### 后端
- `pipelines/` 全套(manager/base/checkpoint/dead_letter/metrics/throttler + 5 个 data pipeline)→ 决策 6 maximal 数据
- `AdaptiveThrottler` — **非死代码**(`lixinger_client.py:214` + `pipelines/base.py:130` 实际调用;更正 memory 旧记录)
- `recover_stale_runs` + `pipeline_stale_sweep` cron → 决策 12 松解 8 周 uptime
- `plan_runner` + `strategy_engine` + `builtin_seeder`(6 策略 6 预案)→ 决策 3 plan DSL
- `draft_service` + 三层防护 → 决策 8 明令保留
- `thesis_monitor` + `cashflow_goal_service` + `review_service` → 决策 4 weekly review
- `core/observability` + `core/events` EventBus → 决策「保留骨架」

### 前端
- `BacktestPage`(571 LoC)→ 决策 9,但需 S2 强化 gate
- `TradeEntryModal` + `CashAdjustmentModal`(358 LoC)→ 决策 3 manual 链路
- `primitives/`(349 LoC)→ 决策 1「易于改写」,合理
- `SystemAlertBanner` / `ErrorBoundary` / `QueryBoundary` / `Layout` → 通用骨架

### 基础设施
- 14 个 cron job 保留(见 S8/S9/S10 简化的 3 个之外)
- alembic 50 个 migration **维持现状**(生产 DB,squash 风险 > 收益;**v1.0 broker 上线前不动**)
- `s11_1_bj_timezone_migration` **禁止 squash**(不可逆时区改造)

---

## 六、文档处理(3066 行需 rewrite)

| 文件 | 行数 | 状态 | 行动 |
|---|---|---|---|
| `docs/active/redesign-decisions.md` | 224 | 新建 | **keep**(本轮锚点) |
| `docs/progress/STATUS.md` | 457 | 2026-06-19,**大部分失效** | **rewrite 最急**(AI 首读,§5.3 L1-L10 在 D7/D12 下大部分失效,§7 引用悬空 spec) |
| `docs/active/roadmap.md` | 128 | 2026-06-13,引用悬空 spec | **rewrite**(短小,配合 redesign-decisions) |
| `docs/active/production-readiness-plan.md` | 2,113 | 2026-06-12,Stage 6 Docker/DR 违反 D11 | **大段移到 docs/reports/completed/**,只留「仍在生效」摘要(S1-S4 已 ship 部分) |
| `docs/active/project-state.md` | 368 | 2026-06-18,§2.3「23 job」与实际 24 不符 | **合并入 STATUS.md**(两者重叠) |
| `docs/reports/completed/*.md` | 41 文件 | 历史档案 | **keep 不删**,含 21 处悬空 spec 引用,rewrite 时顺手标记 `[已归档]` |
| `docs/reference/specs/` | 0 | 已 git rm | 28 处悬空引用需清理(rewrite 时顺手) |
| `CLAUDE.md` §文档索引 | — | 提及 specs/ 目录已空 | **simplify**(同步重写后状态) |
| `README.md` §5.2 | — | 24 cron 列表 | **simplify**(cron 瘦身后同步,且 STATUS 冲突 23 vs 24) |

---

## 七、执行优先级建议

按 ROI(收益/成本)排序,分 4 批:

### Batch 1 — Phase 1 P0 必做(不补无法启动 Phase 1)
1. **P0-1** `auto_execute_enabled` 字段 + UI toggle + dual code path
2. **P0-2** Cockpit `WeeklyBatchReview` 视图
3. **P0-3** worker heartbeat + Cockpit `WorkerHeartbeatCard`
4. **决策 7** 拆 worker(API + worker_main + job_queue IPC)

### Batch 2 — 高 ROI 删除(快速减重,~5000 LOC)
5. **R1** serenity research 全模块(等用户最终确认)
6. **R2 + I1 + I2** intraday_monitor + intraday_price_poll + stop_loss
7. **R3** broker_fee_config
8. **R4** holding_risk_rule
9. **R5 + F1 + I3** business_pattern 全栈
10. **R6** thesis_variable_proposal_service
11. **F2** SerenitySummaryCard

### Batch 3 — 中 ROI 简化(提升一致性)
12. **S3** notification 收敛到 macOS+in_app
13. **S4** alert_rules 移除用户入口
14. **S5** CockpitPage 精简
15. **S6** MonitoringPage 瘦身
16. **S7** DisciplineChecklistModal 精简(11→7 checks)
17. **S8/S9/S10** cron 频率调整

### Batch 4 — 低 ROI defer/rewrite(不阻塞 Phase 1)
18. **S1** historical_* 表瘦身(Phase 2 前做)
19. **S2** backtest_engine gate 强化(Phase 2 前做)
20. **D1-D6** defer 项
21. 文档 rewrite(STATUS → roadmap → production-readiness → project-state)
22. 28 处悬空 spec 引用清理

---

## 八、需要用户决策的开放问题

审计中发现以下需要你拍板的问题:

### Q-A:serenity research 全模块(R1,~2900 LOC)是 remove 还是 defer?

- **remove 理由**:决策 2 时间痛点 + invest 是人的研究体系 + 代理风险
- **defer 理由**:可能 Phase 2 翻 auto 后,LLM 研究作为「候选池补充」有价值
- **我的推荐**:**remove**。Phase 1 焦点是「证明 plan_runner 可靠」,LLM 研究不在这个链路上。真需要时 Phase 2 重建(数据还在,只是代码删了)

### Q-B:`historical_valuations` / `historical_financials`(S1)是删还是留?

- **删的理由**:与 valuations/financial_statements 重复,backtest 可用 publish_date 过滤拼出
- **留的理由**:PIT 数据是 backtest 正确性的关键,临时拼可能出错
- **我的推荐**:**Phase 1 留**,Phase 2 验证 backtest 正确性后再决定

### Q-C:Cockpit 精简(S5)砍哪些卡片?

当前 10+ 卡片:GoalNav / Cycle / ThemeExposure / SerenitySummary / PendingClaims / Rebalance / DividendProj / ThesisAlerts / PortfolioRisk / QuadrantPie / Alerts / Holdings / Plans / PendingCorpActions

- 决策 4 核心需求:GoalNav + Cycle + Drafts(WeeklyBatch) + Holdings + WorkerHeartbeat + Alerts
- 砍候选:SerenitySummary(R1 删)/ ThemeExposure(不在决策)/ QuadrantPie(不在决策)/ PendingCorpActions(D5 defer)/ PortfolioRisk(决策 8 无组合熔断,风险指标意义降级)
- 留候选:PendingClaims(论点变量监控,服务 thesis_monitor)/ Rebalance / DividendProj
- **我的推荐**:砍 5 个,留 9 个

### Q-D:DisciplineChecklistModal(S7)11 → 几个 check 合适?

- 决策 2 时间痛点下,越少越好
- 决策 3 Phase 1 仍需「最低限度的纪律闸门」(invest2 §23 心法)
- **我的推荐**:**4 个核心**(反复交易 / 损失厌恶 / 锚定 / 追高),砍 7 个细碎的

---

## 九、下一步

1. **你拍板 Q-A / Q-B / Q-C / Q-D 四个开放问题**
2. 我按 Batch 1 → 2 → 3 → 4 顺序,每个 Batch 单独 progress 文档 + 验收
3. Batch 1 完成后 Phase 1 才能真正启动(autopilot 真正 daily 跑 + 你 weekly review)
4. 文档 rewrite 放 Batch 4,避免改动中频繁改文档

---

## 参考

- 决策锚点:`docs/active/redesign-decisions.md`
- ADR:`docs/adr/0002-phased-execution-manual-to-auto.md` ~ `0006-manual-operation-no-supervisor.md`
- 审计过程:3 个并行 agent(backend / frontend / infra)对照 14 决策逐项评估
