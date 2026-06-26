# Gojira 下一步计划 (Roadmap, v2)

> **最后更新**: 2026-06-26（v2 大重写后重订）
> **当前状态**: 纸面交易 P0 后端闭环完成（555 测试记录值）。Phase 0-5 ✅，Phase 6-8 进行中。
> **分工**: 本文 = 近期优先级；`docs/active/v2-implementation-plan.md` = 完整 8-Phase 蓝图；`docs/progress/2026-06-26-v2-architecture-and-progress.md` = 架构全景。

---

## P0：纸面交易前端 UI（最高优先级 — 闭合 paper 验证回路）

> 后端 4 信号 + 回填 + 信号告警已就绪（P0-1~P0-4），但用户还看不到/点不动。先把前端补齐才能真正开始 paper 跟踪。

| # | 项 | 说明 |
|---|---|---|
| 1 | **重建 `/drafts` 页** | 当前是 stub。展示应买/应卖 draft 列表（含 trigger_source / tier / sizing / TTL 倒计时），inline 1-click 审批入口 |
| 2 | **"确认成交"弹窗** | execute draft 时弹窗回填实际成交价/量/时间 → manual Trade（source_ref=draft.id）。实际可偏离建议价 |
| 3 | **Cockpit 信号区** | 待办 signals（应买/应卖）置顶，接 `system_alert(category=signal)` |
| 4 | **T+1 可用股数展示** | SELL draft 显示可卖股数（position_service 冻结逻辑） |

## P1：评价系统（四层指标 — 回答"系统选股能否稳定盈利"）

| # | 项 | 说明 |
|---|---|---|
| 1 | **组合层** | 总市值 / 已实现+浮动盈亏 / 持仓明细（position_service 派生） |
| 2 | **基准层** | vs 沪深300（同期收益对比，需引指数序列） |
| 3 | **质量层** | 夏普 / 交易次数 / **双引擎归因**（只算 source_ref 非空的 draft→trade）|
| 4 | **信号层** | 建议价 vs 实际价滑点 / 信号质量统计 |

## P2：触发接线补全（让更多自动信号真正产出 draft）

- **估值止盈触发**（信号 2）：每日扫候选/持仓估值 > 1.3x → TRIM draft
- **仓位超限触发**（信号 3）：> 15% → TRIM 回 10%
- **news_pulse / earnings_review 接线**（信号 4）：异动/财报事件 → 基本面恶化判断 → SELL draft
- `decision_audit` 表填充（Phase 6 Tier 2 前置）

## P3：技术债清理

- **删 scheduler.py v1 孤儿 job**：`daily_plan_evaluation_job` / `thesis_evaluation_job` / `weekly_rebalancing_review_job` / `daily_cycle_assessment_job` / `_monthly_thesis_variable_sync_job` / `_weekly_research_refresh_job` / `weekly_business_pattern_inference_job` / `research_stale_sweep_job` 及其 helper（引用已删的 `watchlist_service`/`plan_runner`/`ResearchRun`）。同时修 registry 内 job 触及未导入 `watchlist_service` 的 latent NameError（改用 lifecycle/position 派生 code 列表）。详见审计报告。
- **澄清/合并两套 research API 命名**（`client.ts` serenity vs `research.ts` v2）
- **澄清数据校验服务边界**（`data_quality`/`data_sanity`/`data_freshness`/`price_validator`）
- **确认 `historical_data_pipeline.py`** 是否被 `pipelines/` 取代
- 前端 bundle 分块（echarts 按需）

## Phase 6（度量系统，对应 v2-implementation-plan）

- Tier 1 运营健康：Pipeline 成功率 / 冲突率 / 红线分布 / 月度 LLM 成本 + 前端监控页
- Tier 2 决策质量：decision_audit 填充 / Draft 批准率 / 论文证伪率
- Tier 3 系统校准：四大师评分与后续股价相关（数据采集）
- Pipeline 熔断：conflict_rate_50 > 20% → throttler 暂停 + 告警

## Phase 7-8（测试与部署）

- Eval Set 20-30 家公司（`tests/eval/companies/*.json`）+ snapshot + 3-5 条 E2E
- docker-compose dev/prod cutover + 备份 cron（compose 已存在，未上线）

---

## 不在路线图上（明确不做）

- 用户认证 / 多用户（个人工具，单用户 by-design）
- PostgreSQL 迁移（SQLite WAL 已满足）
- 移动端 App（响应式 Web 够用）
- 第三方数据源（Lixinger 唯一源决策已确认；行业映射缺口为已知限制 F20）
- 止损（v2 决策不做止损，卖出走 4 信号）
- 范围蔓延加新 Pipeline（严格按 26 决策，新需求 → v3）
