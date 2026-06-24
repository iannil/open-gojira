# Gojira v2 实施计划

> **基础**：`redesign-decisions-v2.md`（26 条决策）
> **代码库现状**：40 models、80+ services、30 routers、16 pages、114 test files、54 Alembic migrations
> **策略**：大重写 + 删除旧代码 + 保留 Lixinger 数据 + dev/prod 部署
> **预估总工期**：12 周（3 个月）

## 现有代码分类（保留 / 改造 / 删除）

### KEEP（基础设施，完全保留）

- **技术栈**：FastAPI + React 19 + SQLite(WAL) + Ant Design 6 + ECharts 6
- **分层架构**：Routers → Services → Models + Schemas
- **核心基础设施**：
  - `app/core/observability.py` + `observability_instrument.py` + `observability_report.py`（`@tracked` 装饰器）
  - `app/core/events.py` + `event_handlers.py`（EventBus）
  - `app/core/datetime_utils.py` / `constants.py` / `exceptions.py` / `industry_registry.py`
- **Pipeline 框架**：`app/services/pipelines/{base,manager,checkpoint,dead_letter,metrics,throttler}.py`
- **数据 Pipeline**：dividend / financial / kline / valuation / universe_bootstrap（5 个保留）
- **数据客户端**：`app/services/lixinger_client.py`
- **Alembic 迁移工具** + 现有 54 个迁移（作为参考）
- **测试基础设施**：pytest + in-memory SQLite + TestClient 模式

### KEEP（数据模型，保留表数据）

- `stocks` / `financial_statements` / `price_klines` / `dividend_records` / `valuation_snapshots`
- `audit_logs` / `trading_calendar` / `data_freshness`
- `historical_*` 系列（historical_financial / historical_kline / historical_valuation）
- `corp_actions`（公司行动）

### REVIEW & ADAPT（已有 LLM 基础设施，评估后改造）

- **`app/services/llm/zhipu_client.py`**：已有 Zhipu 客户端 → **改造为 v2 的 `LLMClient`**，加 `@tracked` / 缓存 / 重试 / 成本追踪 / 冲突后验
- **`app/services/llm/prompts.py`**：已有 prompt → **迁移到 `app/prompts/{pipeline}/{version}/*.md`** 外部文件结构
- **`app/core/research_config.py`**：已有 Serenity 配置 → 改造为 v2 Pipeline 配置
- **`app/core/events.py` 现有事件**：DataSyncCompleted / DraftCreated / AlertTriggered → 保留并新增 v2 事件类型

### DELETE（v1 思维，直接删除）

**Backend：**
- `app/services/builtin_seeder.py`（15+ 策略 + plans + business_patterns + cost_leaders + resource_leaders）
- `app/services/strategy_engine.py`（纯函数评估器）
- `app/services/plan_runner.py`（Plan DSL 执行器）
- `app/services/thesis_variable_sync_service.py`
- `app/services/thesis_monitor_service.py`（v1 论点监控）
- `app/services/thesis_variable_proposal_service.py`
- `app/services/strategy_service.py` / `plan_service.py`（CRUD 服务）
- `app/services/business_pattern_service.py`
- `app/services/research_*` 系列（v1 Serenity 交互式研究模块，被 v2 Pipeline 替代）
- `app/services/cycle_assessment_service.py` / `qiu_*` 系列
- `app/services/stop_loss_service.py` / `rebalance_service.py`（v2 不做止损/再平衡）
- `app/services/backtest_*`（v2 Tier 3 度量自实现）

**Models（删除表）：**
- `strategies` / `plans` / `themes` / `business_patterns`
- `candidates`（旧）/ `drafts`（旧）
- `thesis_variables` / `watchlist_groups` / `watchlist_items`（旧）
- `research_themes` / `research_runs` / `research_*`（v1 交互式研究）
- `backtest_runs` / `holding_risk_rules`
- `cashflow_goals` / `notification_channels`（v2 不做这些通知渠道）

**Routers（删除）：**
- `/strategies` / `/plans` / `/themes` / `/business-patterns`
- `/research/*`（v1 交互式）/ `/backtests`
- `/watchlist`（旧版）/ `/cashflow-goal`

**Frontend pages（删除）：**
- `StrategiesPage` / `PlansPage` / `BusinessPatternsPage`
- `ResearchThemesPage` / `ResearchThemeDetailPage`（v1）
- `BacktestPage`
- `DisciplineChecklistModal` 组件 / `QiuScorerWizard` 组件

### ADD NEW（v2 新建）

**Backend 新模块：**
- `app/services/llm/client.py`（v2 LLMClient，从 zhipu_client 改造）
- `app/services/llm/cost_tracker.py` / `cache.py` / `retry.py`
- `app/services/llm/conflict_validator.py`（post-validation 层）
- `app/services/llm/red_line_checker.py`（8 红线）
- `app/prompts/`（外部 prompt 目录）
- `app/services/pipelines/llm/`（5 个 LLM Pipeline）：
  - `quality_screen_pipeline.py`
  - `deep_research_pipeline.py`
  - `thesis_tracker_pipeline.py`
  - `news_pulse_pipeline.py`
  - `earnings_review_pipeline.py`
- `app/services/lifecycle_service.py`（股票状态机）
- `app/services/draft_generator.py`（Draft 生成 + 触发条件 D）
- `app/services/sell_trigger.py`（卖出触发 1+2+3+5）
- `app/services/metrics/`（Tier 1/2/3 度量）

**新数据表（5 张）：**
- `stock_lifecycle`
- `research_report`
- `decision_audit`
- `llm_call_log`
- `red_line_event`

**改造现有表：**
- `drafts`：加 `trigger_source` / `strategy_tier` / `sizing_logic` / `expires_at` / `status`
- `holdings`：加 `thesis_report_id` / `last_review_at`

**Frontend 新页面：**
- 改造 `CockpitPage` → 信号优先 dashboard
- 新增 `ReportsPage`（研究报告浏览）
- 新增 `PipelineMonitoringPage`（替代旧 MonitoringPage）
- 改造 `OnboardingPage`（持仓 CSV 导入）

---

## 实施阶段（12 周）

### Phase 0：Foundation（Week 1）✅ 已完成 2026-06-24

**目标**：清理 v1 代码，搭好 v2 骨架。

**任务：**
1. ✅ 创建 `v2-rewrite` 分支
2. ✅ 备份现有 DB 到 `backend/data/backups/pre-v2-2026-06-24.db` (1.2 GB)
3. ✅ 写 Alembic 迁移 `v2_1_initial_cleanup`：
   - ✅ drop 22 张 v1 表
   - ✅ 创建 5 张新表（stock_lifecycle / research_reports / decision_audits / llm_call_logs / red_line_events）
   - ✅ 保留 Lixinger 数据表（stocks=5629 / financial_statements=40611 / price_klines=6.2M）
4. ✅ 删除 v1 backend 模块（38 services / 20 models / 11 routers / 10 schemas）
5. ✅ 删除 v1 frontend 页面和组件（8 pages / 7 features dirs / 2 components）
6. ✅ 清理 `app/main.py` 路由注册（30 → 19 routers）
7. ✅ 清理 `frontend/src/App.tsx` 路由（16 → 9 pages）

**Commit**: `cdec6b2 v2 (2026-06-24): Phase 0 — big rewrite baseline` (150 files, -22K lines)

**Verification**:
- ✅ Backend `from app.main import app` OK
- ✅ `/api/health` returns 200
- ✅ `/api/cockpit` returns v2 stub
- ✅ `/api/stocks?limit=3` returns 5629 stocks
- ✅ Frontend `npm run build` OK

### Phase 1：LLM 基础设施（Week 2-3）✅ 已完成 2026-06-24

**目标**：建好 LLM 调用层，所有 Pipeline 都依赖它。

**任务：**
1. ✅ 实现 `app/services/llm/client.py`：LLMClient 类，GLMTier 枚举，@tracked trace_id 集成，prompt_hash 缓存 hook，指数退避重试 3 次，watchdog 超时，tool_use JSON 输出，web_search 支持，自动写 llm_call_logs
2. ✅ 建 prompt 文件结构：shared/{system_base, defense_methodology, evidence_grading}.md + 5 个 Pipeline 占位目录
3. ✅ 实现 `app/services/llm/cost_tracker.py`：月度累计 / $100 软告警 / $150 硬熔断 / check_budget_available
4. ✅ 实现 `app/services/llm/conflict_validator.py`：PE/PB/dyr/revenue 对比，5% 阈值
5. ✅ 实现 `app/services/llm/red_line_checker.py`：8 红线 + consecutive_losses 代码检查 + LLM 标注解析
6. ✅ 5 个 v2 ORM models（StockLifecycle / ResearchReport / DecisionAudit / LLMCallLog / RedLineEvent）
7. ✅ `@tracked` 通过 trace_id_var 集成（LLMClient 自动读 trace_id）

**Deliverable**：✅ 12/12 tests passing，cost math 正确，防御层工作，/api/health 仍 200。

**Commit**: 即将提交

### Phase 2：First Pipeline 闭环（Week 4-5）✅ 已完成 2026-06-24

**目标**：跑通 deep_research 端到端，验证架构。（quality_screen 推迟到 Phase 4）

**任务：**
1. ✅ 实现 `stock_lifecycle` 状态机：enter_state / mark_researched / needs_research (30天缓存) / count_by_state
2. ⏸ quality_screen_pipeline 推迟到 Phase 4
3. ✅ 写 deep_research 7 个 prompts（system + data_collection + 4 masters + synthesis）
4. ✅ 实现 `deep_research_pipeline`：6 步流（gather → data_collect → 4 masters 并行 → synthesis），集成 conflict_validator + red_line_checker
5. ✅ 集成防御层（5% conflict + 8 red lines）
6. ✅ API：`POST /api/research/{code}` + `/latest` + `/history` + `/reports` + `/health`
7. ✅ CLI：`python -m app.cli.research 600519 --model opus --force`

**Deliverable**：✅ 命令行触发单公司深度研究，产出 ai-berkshire 风格 markdown 报告。20/20 v2 tests passing。

**Commit**: 即将提交

### Phase 3：Dashboard MVP（Week 6）✅ 已完成 2026-06-24

**目标**：前端能看报告，能触发研究。（1-click 审批 + CSV 导入推迟到 Phase 5）

**任务：**
1. ⏸ OpenAPI codegen 推迟到 Phase 8（v2 已用 typed client.ts）
2. ✅ 改造 `CockpitPage` 为信号优先：4 stat cards + budget 告警 + 待办 signals 占位 + 最近报告表（60s 自动刷新）+ lifecycle 漏斗可视化
3. ✅ 实现 `ReportsPage`：master-detail 布局，左列筛选（pipeline 类型 + 股票代码搜索），右侧 markdown 渲染（react-markdown）+ 冲突/红线 alert
4. ✅ 改造 `StockDetailPage`：触发面板（模型层选择 + web_search 开关 + force 跳过缓存）+ 最新报告 markdown + 历史列表
5. ⏸ 1-click 审批推迟到 Phase 5（需要 Draft 生成）
6. ⏸ CSV 导入推迟到 Phase 5（需要后端 bulk endpoint）

**安全加固（per 自动安全审查）**：
- ✅ `rate_limit.py` 共享 limiter（避免 main↔routers 循环依赖）
- ✅ `POST /api/research/{code}` 加 `@limiter.limit("10/minute")` + 预算预检 + 异常细节不泄露
- ✅ 3 项其他发现（auth / data enum / cache bypass）按 decision 1 单用户设计声明 by-design

**Deliverable**：✅ 前端 build OK，触发研究 → markdown 报告全链路可视化。20/20 v2 tests passing。

**Commit**: `b83d2e3`

### Phase 4：完整 Pipeline 套件（Week 7-8）

**目标**：5 个核心 Pipeline 全部上线。

**任务：**
1. 实现 `thesis_tracker_pipeline`：
   - 每周对持仓复核
   - 输出 VALID / WARNING / INVALIDATED
   - 写入 thesis 报告
2. 实现 `news_pulse_pipeline`：
   - 监听 `PriceChange ±5%` 事件
   - 4 维并行侦察（公司事件 / 监管 / 行业对手 / 市场情绪）
   - 输出归因报告 + 性质判断
3. 实现 `earnings_review_pipeline`：
   - 监听 `EarningsPublished` 事件
   - LLM 财报精读
   - 论文影响评估
4. 集成 EventBus 新事件类型：
   - `StockEnteredWatchlist` / `DeepResearchCompleted`
   - `CandidateQualified` / `DraftGenerated`
   - `DraftApproved` / `ThesisInvalidated`
5. 实现 Scheduler 调度（APScheduler）：
   - quality_screen 每日 16:00
   - deep_research 每周日 + 状态触发
   - thesis_tracker 每周日
   - valuation_trigger 每日开盘前 + 收盘后

**Deliverable**：5 Pipeline 跑通，事件链工作，定时任务调度。

### Phase 5：Draft 生成 + 卖出触发（Week 9）

**目标**：完整的买卖信号生成。

**任务：**
1. 实现 `draft_generator.py`：
   - 触发条件 D（价格 + 论文 + 组合）
   - 仓位计算（10/30/20 阈值）
   - 策略层仓位（激进 100% / 稳健 50%）
   - Draft TTL 7 天 + 自动取消
2. 实现 `sell_trigger.py`：
   - 触发 1：thesis INVALIDATED → SELL 100%
   - 触发 2：估值 > 1.3x → TRIM 50%
   - 触发 3：仓位 > 15% → TRIM 回到 10%
   - 触发 5：news_pulse 基本面恶化 → SELL 100%
3. 实现 `valuation_trigger` 每日扫描：
   - 查候选池所有公司的当前估值
   - 触发 draft_generator
4. 改造 Draft 模型使用新字段
5. Draft 过期 cron（每日清理 7 天前的 pending drafts）

**Deliverable**：买入 + 卖出 Draft 自动生成。

### Phase 6：度量系统（Week 10）

**目标**：Tier 1/2/3 全部度量上线。

**任务：**
1. Tier 1（运营健康）：
   - Pipeline 成功率 / 冲突率 / 红线分布
   - 月度 LLM 成本
   - 前端 Pipeline 监控页
2. Tier 2（决策质量）：
   - `decision_audit` 表填充逻辑
   - Draft 批准率统计
   - 论文证伪率统计
3. Tier 3（系统校准）：
   - 四大师评分与后续股价相关（数据采集，分析延后）
   - 同公司多次 research 对比视图
4. Pipeline 熔断：
   - `metrics.conflict_rate_50` > 20% 触发 throttler 暂停
   - 告警通知

**Deliverable**：完整可观测的度量系统。

### Phase 7：测试与评估（Week 11）

**目标**：测试体系建立，Eval Set 跑通。

**任务：**
1. Unit tests（100+）：
   - LLMClient（mock Zhipu SDK）
   - 状态机
   - conflict_validator
   - red_line_checker
   - draft_generator / sell_trigger
2. Integration tests（30+）：
   - 各 Pipeline 编排（mock LLM）
   - EventBus 集成
   - Scheduler 集成
3. Eval Set 构建：
   - 20-30 家公司（覆盖各类型）
   - `tests/eval/companies/{stock_code}.json`
   - 自动跑 + 人工 review 流程
4. Snapshot tests：
   - 关键 Pipeline 的输出基线
5. E2E tests（3-5 路径）：
   - 完整买入流（research → candidate → draft → approve）
   - 完整卖出流（thesis invalidate → sell draft → approve）
   - 冷启动 bootstrap

**Deliverable**：CI 可跑，Eval Set 周跑，质量可量化。

### Phase 8：部署与上线（Week 12）

**目标**：生产环境部署。

**任务：**
1. `docker-compose.yml`（base）：
   - backend + frontend + db volume
   - `gojira-net` 独立网络
2. `docker-compose.dev.yml`（开发 override）：
   - backend: `--reload`
   - frontend: `npm run dev`
3. `docker-compose.prod.yml`（生产 override）：
   - backend: gunicorn
   - frontend: nginx serve
4. `.env` 模板更新（GLM API key 等）
5. 数据库备份 cron：
   - 每日备份到 `data/backups/`
   - 30 天轮转
6. 健康检查 endpoint `/api/health`
7. 文档：README 更新 + 部署 runbook
8. 生产 cutover：
   - 备份当前 prod DB
   - 跑 v2 migration
   - 部署 v2 容器
   - Smoke test

**Deliverable**：v2 上线，dev 环境长期运行。

---

## 关键依赖与风险

### 依赖关系

```
Phase 0 (清理) → Phase 1 (LLM 基础) → Phase 2 (首 Pipeline)
                                          ↓
                                       Phase 3 (Dashboard)
                                          ↓
                                       Phase 4 (全 Pipeline)
                                          ↓
                                       Phase 5 (Draft/Sell)
                                          ↓
                                       Phase 6 (Metrics)
                                          ↓
                                       Phase 7 (Testing) → Phase 8 (Deploy)
```

Phase 0-2 是硬依赖，必须顺序。Phase 3-6 可并行（如果有多人）。Phase 7-8 收尾。

### 主要风险

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| GLM 模型质量不达预期 | 中 | 高（核心 Pipeline 失效） | Phase 2 早期跑 Eval Set，迭代 prompt；保留切换 Claude 的能力（LLMClient 抽象） |
| 成本超 $250/月 | 低 | 中 | Phase 1 就上 cost_tracker；硬熔断保护 |
| 范围蔓延（加新 Pipeline） | 高 | 中 | 严格按 26 条决策；新需求 → v3 |
| 数据迁移丢数据 | 低 | 高 | Phase 0 备份；迁移在 DB copy 上测试 |
| 单人开发 12 周太久 | 高 | 中 | Phase 2 后即可用（最小闭环）；增量交付 |
| LLM 评估集难构建 | 中 | 中 | Phase 2 跑通后立即开始；用 ai-berkshire 已有报告作参考 |

### 关键里程碑

| 周次 | 里程碑 | 验证标准 |
|------|--------|---------|
| Week 3 | LLM 基础设施就位 | LLMClient 可调通，成本追踪工作 |
| Week 5 | 首个 Pipeline 闭环 | 命令行对单公司跑 deep_research，产出报告 |
| Week 6 | Dashboard 可用 | 能看报告，能审批 Drafts |
| Week 8 | 5 Pipeline 全跑 | 定时任务工作，事件链通 |
| Week 10 | 完整买卖信号 | 候选 → Draft 全自动 |
| Week 12 | 生产上线 | dev 环境稳定运行 1 周 |

---

## 下一步行动

立即可做（不需要等待）：
1. **创建 `v2-rewrite` 分支** 并备份 DB
2. **写 Phase 0 的 Alembic 迁移脚本**
3. **删除 v1 代码**（按 DELETE 清单）

建议从 Phase 0 开始执行。每个 Phase 完成后更新本文档的进度。
