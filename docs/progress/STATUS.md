# Gojira 项目状态 (Snapshot)

> **此文档是项目当前状态的高频快照。AI 代理应首先阅读此文件,再按需展开。**
> 完整架构与进展见 `docs/progress/2026-06-26-v2-architecture-and-progress.md`。

| 字段 | 值 |
|---|---|
| 项目状态 | **v2（双引擎 + LLM Pipeline 重写）** — 全链路闭环完成 |
| 最后更新 | 2026-06-27（本轮前端补全 + 测试扩充） |
| 分支 | `master`（v2 已并入）；远程仓库：暂无 |
| 测试 | **686 passed**（2026-06-27 记录值） |
| 测试文件 | 69（root 52 + routers 3 + v2 13 + eval 1） |
| Alembic head | `v2_4_drop_holdings_table`（仅 3 个迁移文件，基线 `v2_baseline_squash` down_revision=None） |
| 后端模块 | 25 routers · 40 services + llm(11) + pipelines(11 + pipelines/llm 6) · 29 models · 22 schemas · core(14) |
| 前端 | feature-based（`src/features/` + `src/pages/` shim），17 路由页 |
| 数据源 | Lixinger（理杏仁，唯一 A 股数据源）+ Zhipu GLM web_search |
| 下次 milestone | 真实券商接入 / 评价系统 Tier 2/3 / Eval Set |

---

## 1. 项目定位

Gojira 是一台 **「个人股票自动驾驶舱」**：规则筛选 + LLM 深度研究 + 规则/人工审批的混合架构,把「选股 → 深研 → 买卖草稿 → 持仓审计 → 论点跟踪」全流程自动化,**唯一不自动的是券商真实下单**。

技术栈: FastAPI (Python 3.14) + React 19 (TypeScript) + SQLite (WAL) + Ant Design 6 + ECharts 6。

> **v1→v2 提示**：2026-06-24 起进行了大重写,删除了 v1 规则策略引擎(Strategy/Plan/Candidate/Watchlist/Holding/builtin_seeder)。遇到 `plan_runner`/`strategy_engine`/`builtin_seeder`/`docs/reference/specs/`/`invest{1,2,3}.md` 等名字一律视为已删除的历史。详见 v2 进展文档 §1。

## 2. 双引擎交易体系

- **两条独立选股来源,不互相裁决**：价值复利(ai-berkshire 四大师 段/巴/芒/李)→ `quality_screen`；产业链卡点(serenity)→ `theme_scan`。
- **hybrid 汇合**：serenity 选 WHICH + ai-berkshire 定 PRICE+RISK(估值 + 8 红线)→ 一张草稿。
- **评分 hybrid**：LLM 算分=advisory,Python 按 source profile 复核为权威分(`app/core/scoring_config.py`)。
- **防御**：Prompt + 代码后验(单股 ≤5%) + Pipeline 熔断(冲突率 >20%) + 8 红线否决。预算 $150/月硬熔断。
- 完整思想见 `docs/standards/trading-philosophy.md`(权威),工程决策见 `docs/active/redesign-decisions-v2.md`(26 决策)。

## 3. 核心数据流

```
universe ─ quality_screen/theme_scan ─▶ StockLifecycle(观察池/候选)
  ─ deep_research(4 大师 + 8 红线 + 5% 冲突后验) ─▶ research_report
  ─ draft_generator(价格入区间 + 论文健康 + 组合有空间) ─▶ 应买 Draft(TTL 7d)
  ─ execute 回填实际价 ─▶ trade_service.record_trade ─▶ Trade 账本
  ─ position_service 派生持仓/盈亏 ─ thesis_tracker(周跑) INVALIDATED ─▶ 应卖 Draft
```

- **持仓/盈亏 = Trade 账本派生**(`position_service` 唯一真相源,`holdings` 表已删 migration `v2_4`)。写交易走 `trade_service.record_trade`。
- **卖出 4 信号**(不止损)：论点证伪 / 估值 1.3x / 仓位 15% / 基本面恶化。
- **EventBus**(异步非阻塞)：新买卖 draft → `system_alert(category=signal)` 仅 in-app 提醒。

## 4. 模块清单（实测 2026-06-26）

详细一行职责见 `docs/progress/2026-06-26-v2-architecture-and-progress.md` §3-§4。计数与代表模块：

- **Routers(22)**：health/stocks/valuation/financial/dividend/portfolio/market/trades/cash/fee_configs/corp_actions/drafts/cockpit/**research_v2**/**theme_scan**/alerts/system_alerts/notifications/scheduler/data_management/audit_log/observability。
- **Services**：顶层 40 + `llm/`(11：client/cost_tracker/conflict_validator/red_line_checker/scoring/prompt_loader/deep_research_schema/theme_scan_schema/prompts/zhipu_client) + `pipelines/`(12) + `pipelines/llm/`(7)。交易核心：`position_service`/`trade_service`/`draft_generator`/`draft_service`/`lifecycle_service`/`sell_trigger`/`decision_audit_service`。
- **Models(29)**：v2 新表 stock_lifecycle/research_report/theme_scan_report/decision_audit/llm_call_log/red_line_event/eval_run/eval_result；交易 trade/cash_balance/cash_adjustment/broker_fee_config/draft；数据 stock/valuation/financial/historical_financial/historical_valuation/price_kline/dividend/corp_action/historical_kline 等。
- **前端 17 页**：Cockpit(信号 dashboard+待办Drafts+signal告警) / Portfolio(持仓组合+评价) / Dividend(股息红利汇总) / FeeConfigs(CRUD) / AuditLog(过滤查询) / Market(指数行情+K线) / CorpActions(批量处理) / Valuation(估值仪表盘) / Universe / Reports / StockDetail / Trades / DataManagement / Scheduler / Monitoring / Drafts(确认成交弹窗+T+1可卖股数) / Eval。

## 5. 实施进度

| Phase | 状态 | | Phase | 状态 |
|---|---|---|---|---|
| 0 Foundation | ✅ | | 5 Draft/卖出触发 | ✅ 全链路闭环 |
| 1 LLM 基础设施 | ✅ | | 6 度量系统 | 🟡 Tier 1 + 部分 Tier 2 |
| 2 首 Pipeline 闭环 | ✅ | | 7 测试/Eval Set | ✅ **686 tests** |
| 3 Dashboard MVP | ✅ | | 8 部署上线 | 🟡 docker-compose base+dev |
| 4 完整 Pipeline 套件 | ✅ | | | |

**全链路闭环完成**(2026-06-26)：position_service 真相源 + execute 回填 Trade + thesis INVALIDATED→SELL draft + sell_trigger 信号2/3/5 + decision_audit + Pipeline熔断 + quality_screen prompt外化 + docker-compose dev。

**已完成待办项**：
- ✅ 前端 7 个新页面：Portfolio / Dividend / FeeConfigs / AuditLog / Market / CorpActions / Valuation
- ✅ 前端 emoji 清理 → 统一 Ant Design Icons 风格
- ✅ CLAUDE.md 过时标注更新（Drafts stub → 完整, scheduler 孤儿 job 已清, 计数修正）
- ✅ 导航图标去重（Drafts: FileTextOutlined → EditOutlined）
- ✅ 代码质量修复：DatePicker Dayjs 类型, 股息率 100× 差异, market_cap 非空断言, QueryBoundary 缺失, onError 缺失
- ✅ 后端测试扩充 +47（audit_log 10, dividend 15, market 10, index 12）
- ✅ scheduler.py 孤儿 job 引用验证（JOB_REGISTRY 19 条均指向有效函数）
- ✅ Drafts 页（确认成交弹窗 + T+1 可卖股数 + 三种状态Tab）
- ✅ Cockpit 信号区（待审批Drafts表格 + signal_alerts）
- ✅ sell_trigger（估值止盈 信号2 + 仓位超限 信号3 + 基本面恶化 信号5）
- ✅ decision_audit 表填充（Draft 执行时写入）
- ✅ Pipeline 熔断（conflict率 >20% 阻断新运行）
- ✅ quality_screen prompt 外化
- ✅ event_handlers v1 残留清除
- ✅ docker-compose.dev.yml + Dockerfile.dev
- ✅ Research API 命名合并（已统一到 research.ts）
- ✅ scheduler v1 孤儿 job 清理（已使用 StockLifecycle 状态机）

**下一步**(详见 `docs/active/roadmap.md`)：评价系统 Tier 2/3 / Eval Set / 真实券商接入

## 6. 已知问题 / 技术债

- **`data_quality`/`data_sanity`/`price_validator` 服务边界需澄清**：四个数据校验服务职责有重叠，待重构。
- **前端 bundle 分块**：echarts 按需加载未做，首屏体积偏大。
- **评价系统 Tier 3 未实现**：四大师评分与后续股价相关分析未做。
- **Eval Set 基线未构建**：`tests/eval/companies/` 已有 20 个 JSON 数据文件，但基线运行记录尚未创建。
- 完整审计(冗余/过期/失效项 + 已执行清理)见 `docs/reports/2026-06-26-codebase-cleanup-audit.md`。

## 7. 文档导航（v2）

| 路径 | 语义 |
|---|---|
| `docs/progress/STATUS.md` | **本文件**,高频快照,AI 首读 |
| `docs/progress/2026-06-26-v2-architecture-and-progress.md` | **v2 完整架构与进展**(LLM 友好,迭代必读) |
| `docs/progress/2026-06-26-paper-trading-loop-design.md` | 纸面交易评估闭环设计(进行中) |
| `docs/standards/trading-philosophy.md` | **交易思想权威**(双引擎/评分/去重×3/弃用清单) |
| `docs/active/redesign-decisions-v2.md` | **工程决策锚点**(26 决策,AI 首读) |
| `docs/active/v2-implementation-plan.md` | 8-Phase 完整蓝图 |
| `docs/active/roadmap.md` | 近期优先级(P0/P1/P2/P3) |
| `docs/standards/serialization.md` | 序列化标准(持续生效) |
| `docs/reports/2026-06-26-codebase-cleanup-audit.md` | 代码库清理审计 |
| `docs/reports/completed/2026-06-25-legacy-cleanup-test-and-migration.md` | v1-leftover 清理记录 |
| `docs/templates/*` | 文档骨架模板 |
| `docs/reference/ai-berkshire/` · `serenity-skill/` | 双引擎方法论参考(gitignored) |
| `docs/archive/v1/` | v1 废弃文档(redesign-decisions-v1 / ADRs / 审计) |
| `memory/MEMORY.md` · `memory/daily/` | 项目记忆(沉积层 + 流层) |
