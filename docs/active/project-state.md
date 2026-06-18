# Gojira 项目当前状态 (LLM Onboarding Guide)

> **目的**: 让下一个接手的 LLM 在 5 分钟内建立完整画面。CLAUDE.md 是项目规范,STATUS.md 是实测快照,本文档是**综合导航**。
>
> **项目状态**: **v0.1-paper-verified** ✅ (2026-06-18 grill-me completion verification 通过)
>
> **更新约定**: 每次完成 finding 修复 / ship 新功能 / 实测发现差异时更新本文件。STATUS.md 是"现在这一刻的快照",本文件是"现在为止的完整状态"。

---

## 0. AI 接手必读顺序

1. **本文件** — 建立完整画面 (5 分钟)
2. `docs/progress/STATUS.md` — 最新实测快照 (测试数 / commit / DB 状态)
3. `CLAUDE.md` — 项目规范 + 编码约定 + 双层 memory 架构
4. `memory/MEMORY.md` (项目内) — 高频访问的浓缩版记忆索引
5. `~/.claude/projects/-Users-rong-zhu-Code-gojira/memory/MEMORY.md` (Claude auto-memory) — 跨会话记忆

**优先级**: STATUS.md (实测快照) > 本文件 (综合) > memory (浓缩) > docs/progress/*.md (历史细节)。

---

## 1. 项目定位

Gojira 是一台**「个人股票自动驾驶舱」**:面向中国 A 股市场,基于 `docs/reference/invest{1,2,3}.md` 的投资体系,实现「策略组合 → 自动扫描 → 候选池 → 交易信号 → 持仓审计」全流程自动化。**除了在券商真实下单外**,筛选 / 监控 / 告警 / 订单草稿 / 再平衡建议 / 逻辑证伪全部自动。

**技术栈**: FastAPI (Python 3.14) + React 19 (TypeScript) + SQLite (WAL) + Ant Design 6 + ECharts 6。Lixinger (理杏仁) 是唯一外部 A 股数据源。

**用户三原则 (2026-06-13 锁定)**:
1. 除真实券商下单外全自动化
2. 架构尽可能简化
3. 交易系统对齐 `docs/reference/invest{1,2,3}.md`

详见 [[feedback-defer-infra-until-core-flow]]。

---

## 2. 当前可用功能矩阵 (2026-06-18 实测)

### 2.1 数据同步 (Lixinger API)

| 功能 | 状态 | 实测证据 | 已知限制 |
|---|---|---|---|
| 全市场 stocks 同步 (5626) | ✓ | `stocks=5626` | Lixinger API 不提供 industry 字段 (F20) |
| 估值 Pipeline (valuations=14928) | ✓ | F4 throttler wire + F5 429 retry | 单次同步 ~60s |
| K线同步 (price_klines=702950) | ✓ | 5 stocks × 3.5y 历史 | kline_service 有 lazy fetch path |
| 财报同步 (financial_statements=26799) | ✓ | F3 data_freshness 同步 | financial_pipeline 单股调用,全市场 90 min |
| 分红同步 (dividends=48989) | ✓ | F5 429 retry 后 5354/5354 成功 | 同上 |
| Lixinger circuit breaker | ✓ | api.critical alert 2026-06-17 16:13 | 5 次连续失败触发熔断 |

### 2.2 核心业务流程

| 功能 | 状态 | 实测证据 | 已知限制 |
|---|---|---|---|
| Plan runner (扫描→候选→draft) | ✓ | plan 1: 4 candidates + 6 drafts | 6 plan 中 4 可用 (plan 2/6 受数据缺失限制) |
| 候选池自动进出 | ✓ | 12 active candidates | source 字段区分 rule_based / serenity |
| Draft 生成 + supersede | ✓ | 10 pending drafts | F25 测试稳定性修复 |
| 周期评估 (cycle_assessment) | ✓ | cycle_position="low" | 依赖 Lixinger CSI300 PE 历史,fallback 到 CashflowGoal.current_index_pe_pct |
| Position advisor (集中度 cap) | 🟡 部分 | 15% industry cap | F20: industry 字段实际是 fsTableType,cap 在非金融股上几乎失效 |
| 论点证伪 → auto SELL draft (M4) | ✓ 代码层 | EventBus handler wired | DB 中 0 thesis_alerts (用户未填 thesis_variables) |

### 2.3 Scheduler (23 个 job)

| 类别 | 状态 | 实测证据 | 已知限制 |
|---|---|---|---|
| Cron 配置正确性 | ✓ F14 修复 | 周一 17:45 不再静默跳过 | 等下周一真触发验证 |
| Stuck pipeline 防御 | ✓ F15 修复 | recover_stale_runs wire + pipeline_stale_sweep job (15 min) | - |
| Stuck research 防御 | ✓ F23 修复 | research_stale_sweep job (10 min) | - |
| LLM hang 防御 | ✓ F26 修复 | watchdog wrap LLM + web_search | Python 不能强 kill thread,zombie 由 GC 回收 |
| Plan evaluation 触发 | 🟡 | job_executions 显示跑过 2 次 (6/10, 6/13) | 6/14-6/18 未触发 (服务未持续运行) |

### 2.4 高级功能 (从未真实跑过)

| 功能 | 状态 | 实测证据 | 已知限制 |
|---|---|---|---|
| Backtest engine | ✓ F21+F27+F28 | 5 股 × strategy 2,60 trades, sharpe 1.65 | sizing 限制: target_pct=0.10 对高价股不够 1 lot |
| Serenity research (LLM) | 🟡 部分 | Q14 Path B 跑过 1 次 (run_id=8) | GLM SSL hang 复现,F26 watchdog 已防 |
| Thesis monitor 双 check | ✓ 代码层 | check_held_stocks + check_claim_variables | 0 thesis_variables,需用户填数据 |
| 月度复盘 | 🟡 代码层 | periodic_review_service 存在 | 0 review 记录 |
| 银行盲盒分析 | ✓ F8 修复 | bank_analyzer_service 双语 industry | forward_dyr F17 v2 后银行股可选 |
| 再平衡建议 | 🟡 代码层 | rebalance_service 存在 | 0 holdings,无法真测 |

---

## 3. Finding 累计清单 (F1-F28)

> 历轮 audit 共发现 28 个 finding,F1-F13 (2026-06-18 早 audit) + F14-F28 (本次 grill-me + P1)。

### 3.1 已彻底修复 (P0)

| ID | 严重度 | 描述 | 修复 commit |
|---|---|---|---|
| F4 | P0 | AdaptiveThrottler 死代码 wire | 788a4f5 |
| F5 | P0 | Lixinger 429 不 retry → 15276 dead_letter | 788a4f5 |
| F7 | P0 | avoid_overvalued_tech 用 invalid op `<` | 788a4f5 |
| F8 | P0 | bank_select industry 双语 (`"银行"` vs `"bank"`) | 788a4f5 |
| F12 | CRITICAL | in_circle filter 默认翻转 (Batch 5 M2 break production) | 788a4f5 |
| F14 | P0 | APScheduler cron day_of_week 错位一天 | 9ebb86a |
| F15 | P0 | recover_stale_runs 死代码 + pipeline_stale_sweep job | 9ebb86a |
| F16 | P0 | SessionLocal 没 mock,测试污染生产 DB | 9ebb86a |
| F17 v2 | P0 | forward_dyr 算法 (Lixinger dyr × stability) | de0bd81 |
| F21 | P0 | BacktestSubmit schema vs engine 字段对齐 | 1b701f6 |
| F23 | P0 | research_stale_sweep job (GLM SSL hang 防御) | 6484ee6 |
| F26 | P0 | serenity worker watchdog (proactive 防 hang) | e69c3fc |
| F28 | P0 | _compute_percentile_at Feb 29 闰年 ValueError | 7fd2ce5 |

### 3.2 已修复 (P1) — 务实方案

| ID | 严重度 | 描述 | 修复 commit | 残留 |
|---|---|---|---|---|
| F17 v1 | P0 | WHERE amount_per_share > 0 (F17 v2 之前的过渡) | 9ebb86a | 被 v2 取代 |
| F20 | P0 | stocks.industry 字段语义错位 (fsTableType 而非申万行业) | 9ebb86a | 真实现需 AkShare (留 P1) |
| F24 | 杂项 | logs/ 加入 .gitignore | 9165cf1 | - |
| F25 | P1 | flaky test 隔离 (_price_cache + lixinger cache 清理) | 9165cf1 | 全套跑慢 60s→180s |
| F27 | 验证 | backtest 扩展历史数据 (5 stocks × 3.5y) | 7fd2ce5 | - |

### 3.3 文档化决策 (非 bug)

| ID | 描述 | 处理 |
|---|---|---|
| F1/F2/F3/F9/F10/F11/F13 | STATUS.md 文档漂移 (测试数 / migration count / drafts 数) | 988c3d5 修 |
| F6 | financial_pipeline 不批量 (90 min 同步) | 留作下次 |
| F10 | qiu_score 全 0 → plan 6 永远 0 候选 | builtin_seeder ⚠️ 标记 |
| F11 | dividend_payout_commitment_pct 只 1 stock 有数据 | builtin_seeder ⚠️ 标记 |

### 3.4 已知限制 (跟外部数据源 / 用户操作相关)

| 限制 | 描述 | 解锁条件 |
|---|---|---|
| F20 真实现 | midstream filter / business_pattern_inference / holding industry cap 失效 | 引入 AkShare (用户已决策不引入) |
| thesis_monitor 真触发 | thesis_evaluation 跑 41 次但 0 thesis_alerts | 用户填 thesis_variables_json |
| scheduler 真触发验证 | F14 修复后等下周一 17:45 验证 | 时间等待 |
| forward_dyr 真算法 | F17 v2 用 Lixinger dyr × stability,不是真 forward projection | 需要分红 guidance 数据 |

---

## 4. 6 内置 Plan 真实可用性 (2026-06-18 实测)

| Plan ID | slug | 状态 | 实测产出 | 根因 |
|---|---|---|---|---|
| 1 | core_value | ✓ 可用 | 4 candidates + 6 drafts | 唯一一直可用 |
| 2 | resource_macro (高息低估值) | ✗ 0 候选 | 0 | strategy 3 (resource_hard_asset) 要求 has_mine=1,只 7/5626 股 |
| 3 | bank_anchor (银行底仓) | ✓ F17 v2 后可用 | 7 candidates + 3 drafts | F17 v2 修了 forward_dyr 系统性低估 |
| 4 | contrarian_scan (超跌逆向) | ✓ 筛选可用 | 6 candidates, 0 drafts | 设计选择: trading_rules_json 为空 (纯筛选,STATUS §4 一致) |
| 5 | pure_cash_machine | ✓ F17 v2 后可用 | 1 candidate + 1 draft (芭田 002170) | F17 v2 修复后 forward_dyr 1.5% → 6.6% |
| 6 | moat_leader (选择权龙头) | ✗ 0 候选 | 0 | qiu_score 全 0 (F10),optionality_leader 永远 fail |

**总结**: 6 个内置 plan **4 个真实可用** (plan 1/3/4/5),2 个因数据缺失不可用 (plan 2/6,需用户手动填字段)。

---

## 5. Scheduler 任务现状 (23 个 job)

### 5.1 JOB_REGISTRY (按 cron 类型分组)

**Daily (周一到周五)**:
- `daily_universe_bootstrap` (15:00) — 全 A 股列表增量同步
- `daily_base_sync` (15:15) — 全量估值同步
- `daily_industry_sync` (15:10) — 申万行业同步 (⚠️ 死代码已删,scheduler_jobs 表已清)
- `daily_snapshot` (17:00) — watchlist 估值快照
- `daily_cycle_assessment` (17:05) — 沪深300 周期评估
- `daily_kline_sync` (17:15) — watchlist+held K线增量
- `daily_prev_close_sync` (17:20) — 涨跌停校验 prev_close
- `alert_evaluation` (17:30) — AlertRule 评估
- `thesis_evaluation` (17:32) — 论点变量监控
- `daily_plan_evaluation` (17:45) — 预案自动评估 (核心)
- `daily_deep_sync` (18:00) — 候选股深度同步
- `daily_corp_action_apply` (09:00) — 公司行为应用

**Intraday**:
- `intraday_monitor` (*/5 9-14,默认关) — 盘中价格监控
- `intraday_price_poll` (*/5 9-14,默认关) — 实时价格轮询

**Weekly/Monthly/Quarterly**:
- `weekly_research_refresh` (周一 08:00) — serenity 研究
- `weekly_dividend_sync` (周一 09:00) — 周度分红同步
- `weekly_rebalancing_review` (周日 10:00) — 再平衡检查
- `weekly_business_pattern_inference` (周日 04:30) — 商业模式推断 (⚠️ F20 联动,updated=0)
- `monthly_dividend_sync` (1 日 03:00) — 月度分红
- `monthly_thesis_variable_sync` (1 日 04:30) — 月度论点变量
- `quarterly_financials_refresh` (季报窗口) — 财报刷新
- `quarterly_shareholders_refresh` (季度初) — 股东信息

**Sweep / Watchdog (新增)**:
- `pipeline_stale_sweep` (*/15) — F15: stuck pipeline runs
- `research_stale_sweep` (*/10) — F23: stuck research runs

### 5.2 真实触发情况 (job_executions 表)

| Job | 真实跑过次数 | 最后一次 |
|---|---|---|
| intraday_monitor | 102 | 2026-06-18 02:45 (5min freq) |
| thesis_evaluation | 41 | 2026-06-18 02:31 |
| daily_universe_bootstrap | 3 | 2026-06-13 |
| daily_base_sync / kline_sync / cycle_assessment / plan_evaluation | 2 each | 2026-06-13 |
| 其他 daily jobs | 1 或 0 | 2026-06-10/13 |

**结论**: scheduler 真实跑过 14 个不同 job,但 6/14-6/18 主要靠 intraday_monitor + thesis_evaluation。daily_plan_evaluation 6/14-6/18 未触发 (服务未持续运行 + F14 cron 错位双重原因)。F14 修了 cron,但需等下周一才能真触发验证。

---

## 6. 测试矩阵

### 6.1 测试规模

- **总数**: 1181 passed (2026-06-18,本会话累计 +24)
- **耗时**: 全套 ~3 分钟 (F25 后清 cache 开销,此前 60-100s)
- **覆盖率**: backend ~33000 行代码 + ~20000 行测试

### 6.2 本会话新增测试

| Finding | 测试 | 数量 |
|---|---|---|
| F14 | cron_to_trigger + _translate_dow_field | +4 |
| F15 | recover_stale_runs + pipeline_stale_sweep_job | +3 |
| F17 v1 | _historical_avg_per_share WHERE > 0 | +3 |
| F17 v2 | compute_forward_dyr v2 stability + fallback | +5 |
| F21 | BacktestSubmit schema + API passthrough | +3 |
| F23 | research_stale_sweep | +2 |
| F26 | watchdog hang scenarios | +2 |
| F28 | Feb 29 leap year + normal date | +2 |

**累计本会话 +24 测试**。

### 6.3 测试稳定性

- F25 后: 全套 5/5 通过 (此前 2/3 通过率)
- 已知 flaky: 无 (F25 修复)
- 跨 test pollution: 已清 (conftest.py setup_db fixture 清 _price_cache + lixinger_client._cache)

---

## 7. 已知限制详细 (LLM 接手要看)

### 7.1 数据源限制

- **F20**: `stocks.industry` 字段实际存的是 Lixinger `fsTableType` (5 值: non_financial/bank/security/insurance/other_financial),不是申万行业。影响:
  - business_pattern_inference 永远 0 匹配 (spike 证实 Lixinger API 无 industry 字段)
  - midstream filter 98.3% bypass (stocks 无 business_pattern_id)
  - holding_service industry cap 在非金融股上失效
  - **真实现需 AkShare** (用户已决策不引入)
- **F17 v2 部分**: forward_dyr 用 Lixinger dyr × stability,不是真 forward projection。真算法需要分红 guidance 数据。
- **F10**: 0/5626 stocks 有 qiu_score → plan 6 (optionality_leader) 永远 0 候选
- **F11**: 1/5626 stocks 有 dividend_payout_commitment_pct → dividend_commitment_leader 近乎非功能

### 7.2 调度限制

- **scheduler 真触发未验证**: F14 修复 cron 错位,但 6/14-6/18 服务未持续运行,需等下周一 17:45 验证
- **thesis_monitor 真触发未验证**: thesis_evaluation 跑 41 次但 thesis_variables=0,需用户填数据

### 7.3 业务限制

- **6 内置 plan 仅 4 可用**: plan 2 (has_mine 缺) + plan 6 (qiu_score 缺)
- **backtest sizing**: target_pct=0.10 对高价股 (e.g. 茅台 1775 元) 不够买 1 lot,需要大 initial_capital
- **F26 watchdog 不强 kill**: Python 不能强 kill thread,LLM hang 时 watchdog 让 main 流程脱困,但 zombie thread 继续。F23 sweep job 后续清 DB 状态。

---

## 8. 推荐下一步 (P2)

按优先级排序:

### 8.1 高价值 (核心闭环增强)

1. **scheduler 真触发验证** — 等下周一 17:45 看 daily_plan_evaluation 是否真触发,产出 candidates/drafts。F14 已修,需时间验证。
2. **thesis_monitor 真触发** — 用户填一个 thesis_variables_json (e.g. 工商银行 NIM < 1.3%),验证 breach → EventBus → SystemAlert → M4 SELL draft 全链路。
3. **F20 真实现** (如改变决策引入 AkShare) — 实现申万行业 daily sync,激活 midstream filter / business_pattern_inference / holding industry cap。

### 8.2 中价值 (架构改进)

4. **multiprocessing 隔离 LLM 调用** — 替代 F26 watchdog (Python 不能强 kill thread)。子进程跑 LLM,父进程超时强 kill。需要重构 _execute_run_in_worker 不依赖 thread-local DB session。
5. **前端 TanStack Query 重构** — 2026-06-13 定,未实施。12 页统一改 TanStack Query + feature-folder。详见 [[project-frontend-page-interface]]。
6. **F17 v2 → v3** — forward_dyr 换真算法 (按年 sum DPS / 用 dividend guidance),彻底对齐 invest3 §8。

### 8.3 低价值 (杂项)

7. **F6 financial_pipeline 批量化** — 全市场 90 min → 5 min。Lixinger client 已支持 batch,重构 ~30-60 min。
8. **datetime.utcnow() → datetime.now(UTC)** — Python 3.14 deprecation warning。涉及 ~10 处。
9. **STATUS.md 自动化生成** — 从 git log + pytest 输出自动生成,减少人工同步成本。

---

## 9. 文档导航 (完整版)

| 路径 | 语义 | 何时读 |
|---|---|---|
| **本文件** (`docs/active/project-state.md`) | 综合导航 | AI 接手必读 |
| `docs/progress/STATUS.md` | 实测快照 | 每次会话开始 |
| `docs/active/roadmap.md` | P1/P2/P3 优先级 | 决定下一步 |
| `docs/standards/serialization.md` | 序列化标准 | 写新 router/service |
| `docs/templates/*.md` | 文档骨架 | 写新 progress/completed |
| `docs/reports/completed/*.md` | 已完成修改 + 历轮审计 | 想了解某次 ship 细节 |
| `docs/reference/invest{1,2,3}.md` | 投资理论 (gitignored) | 理解业务背景 |
| `docs/reference/investment-theory-source.md` | 投资理论原文合集 | 同上 |
| `docs/reference/specs/*.md` | 已确认的设计规格 | 修改对应模块 |
| `docs/archive/*.md` | 早期归档 | 了解演进历史 |

### 文档规范 (CLAUDE.md)

- 未完成修改 → `docs/progress/`
- 已完成修改 → `docs/reports/completed/`
- 对修改进行验收 → `docs/reports/` (根目录,综合审计)
- 持续生效的标准 → `docs/standards/`
- 文档骨架模板 → `docs/templates/`
- 综合状态导航 → `docs/active/` (本文件)

---

## 10. 历史里程碑 (倒序)

| 日期 | 事件 | Commit |
|---|---|---|
| 2026-06-18 | F27+F28 backtest 扩展 + Feb 29 fix | 7fd2ce5 |
| 2026-06-18 | F26 serenity worker watchdog | e69c3fc |
| 2026-06-18 | F24+F25 gitignore logs + flaky test | 9165cf1 |
| 2026-06-18 | F23 research stale sweep | 6484ee6 |
| 2026-06-18 | F21 backtest schema 对齐 | 1b701f6 |
| 2026-06-18 | F17 v2 forward_dyr Lixinger dyr × stability | de0bd81 |
| 2026-06-18 | docs: grill-me audit 报告 + F20 spike | fb2337f |
| 2026-06-18 | fix(audit): 5 P0 修复 F14/F15/F16/F17/F20 | 9ebb86a |
| 2026-06-18 | docs: STATUS.md 同步 | e95b80b |
| 2026-06-18 | 5 P0/CRITICAL F4/F5/F7/F8/F12 | 788a4f5 |
| 2026-06-17 | invest1/2/3 Batch 1-5 全 ship | d3d19c6 等 |
| 2026-06-15 | 三层完成度审计 + Phase 2 commit | e0a915f |
| 2026-06-11 | 第 6 轮全面深度审计 (32 项修复) | (历史快照,402 测试为当时值) |
| 2026-06-09 | 数据管理模块精细化升级 (5 Tab) | - |
| 2026-06-05 | 业务闭环打通 (分析→决策→持仓) | - |
| 2026-06-04 | 项目初稿 | - |

---

## 11. LLM 接手 Checklist

接手前 5 分钟读完上面,然后:

1. **跑测试确认基线**: `cd backend && .venv/bin/python -m pytest tests/ --tb=no -q` → 应 1184 passed
2. **看 git log**: `git log --oneline -20` → 应看到 v0.1 verification commits (F29 `c4d105c` 是最新)
3. **看 DB 状态**: `sqlite3 backend/data/gojira.db "SELECT 'holdings', COUNT(*) FROM holdings WHERE sell_date IS NULL UNION ALL SELECT 'drafts_pending', COUNT(*) FROM drafts WHERE status='pending' UNION ALL SELECT 'candidates', COUNT(*) FROM candidates WHERE status='active'"` → 应 2 holdings / 83 drafts / 179 candidates (v0.1 paper-verified artifact)
4. **看 scheduler 状态**: `sqlite3 backend/data/gojira.db "SELECT job_id, status, started_at FROM job_executions ORDER BY started_at DESC LIMIT 10"`
5. **跟用户确认任务**: 不要假设下一步,问用户优先级

**重要原则** (来自 CLAUDE.md + memory):
- 不要做"假设性未来需求"的预防性设计 (YAGNI)
- 测试通过 ≠ 真实链路跑通 (F1/F13/F29 教训) — 修了功能要真跑验证 (paper execute 端到端)
- 用 Lixinger API spike 时必须 artifact 化 ([[feedback-artifact-or-didnt-happen]])
- ship 必须真实 DB 端到端,不只 fixture+unit test ([[project-audit-2026-06-18]])
- 死代码模式重复出现 (F4/F15/daily_industry_sync/F29-auto_create_holding 死字段) — 加新公共方法必须 ≥1 调用方,schema 字段必须被 router 读

## 12. v0.1-paper-verified 通过证据 (2026-06-18 grill-me completion verification)

10 项 design 决策锁定 (B/A/A/B/D/A/B/B/A/A)。Stage 1+2 全部通过。详见 `docs/reports/2026-06-18-grill-me-completion-verification.md`。

### autopilot 链路 paper 真跑通
- scheduler 真触发 (daily_plan_evaluation today 17:45 Asia/Shanghai,72s success)
- plan_runner 真产出 (drafts 10→86, candidates 12→179)
- paper execute 真生效 (2 holdings created: 000651 + 000001)
- audit 真挂上 (holding.created × 2 + draft.executed × 4)
- 下游 evaluation 真跑 (alert_evaluation + thesis_evaluation 都 success)

### 三防护 production 验证 (F30 finding)
- 价格 band 校验 ✓ (¥100 for 002572 实际 ¥8.51 → 400 rejected)
- Cash balance 校验 ✓ (0 cash BUY ¥3905 → 400 rejected)
- Industry 集中度 cap ✓ (bank 60% > 15% → 409 rejected, force=true 可 bypass)

### v0.1 → v0.2 → v1.0 → v2.0 路径
- **v0.2**: scheduler 跑 1 个月 + 月度复盘真触发
- **v1.0**: 真实 broker 下单 + thesis_variables 用户填 + thesis_monitor M4 真触发
- **v2.0**: 6/6 plan 可用 (AkShare / 数据源扩展)
