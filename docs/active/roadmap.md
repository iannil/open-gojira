# Gojira 下一步计划 (Roadmap, v2)

> **最后更新**: 2026-06-26
> **当前状态**: 全链路闭环完成（587 测试记录值）。Phase 0-5 ✅，Phase 6 部分，Phase 7-8 部分。
> **分工**: 本文 = 近期优先级；`docs/active/v2-implementation-plan.md` = 完整 8-Phase 蓝图；`docs/progress/2026-06-26-v2-architecture-and-progress.md` = 架构全景。

---

## ✅ 已完成项（此前 P0-P3，已全部闭环）

- **Drafts 页** — 确认成交弹窗（回填实际价/量/时间）+ T+1 可卖股数 + 三种状态Tab
- **Cockpit 信号区** — 待审批Drafts表格 + signal_alerts 置顶
- **sell_trigger** — 卖出信号2/3/5 (估值止盈/仓位超限/基本面恶化)
- **decision_audit 表填充** — Draft 执行时自动写入
- **Pipeline 熔断** — conflict率 >20% 阻断新运行
- **quality_screen prompt 外化** — `prompts/quality_screen/v1/borderline_judgment.md`
- **event_handlers v1 残留清除** — 删除6个v1 handler
- **docker-compose.dev.yml** — + Dockerfile.dev（Vite HMR + hot reload）
- **Research API** — 已统一到 `research.ts`

## P1（下一次）：评价系统 — 回答"系统选股能否稳定盈利"

| # | 项 | 说明 |
|---|---|---|
| 1 | **组合层** | 总市值 / 已实现+浮动盈亏 / 持仓明细（position_service 派生）— ✅ 已有 |
| 2 | **基准层** | vs 沪深300（同期收益对比，需引指数序列）|
| 3 | **质量层** | 夏普 / 交易次数 / **双引擎归因**（只算 source_ref 非空的 draft→trade）|
| 4 | **信号层** | 建议价 vs 实际价滑点 / 信号质量统计 |

## P2（评估集）：Eval Set + 质量基线

- 构建 Eval Set 20-30 家公司（`tests/eval/companies/*.json`）
- snapshot 测试 + 3-5 条 E2E 测试路径
- 完整买入流 + 卖出流 + 冷启动 bootstrap

## Phase 6：度量系统补全

- Tier 1 运营健康：Pipeline 成功率 / 冲突率 / 红线分布 / 月度 LLM 成本 + 前端监控页 — ✅ 已有
- Tier 2 决策质量：Draft 批准率 / 论文证伪率 — ⏳ decision_audit 已填充，统计视图待做
- Tier 3 系统校准：四大师评分与后续股价相关（数据采集）— ⏳ 待做
- Pipeline 熔断：conflict_rate_50 > 20% → throttler 暂停 + 告警 — ✅ 已有

## Phase 8：部署上线

- docker-compose base + dev — ✅ 已有
- 生产 cutover + 长期运行 — ⏳ 待做

## 清理/技术债

- 澄清数据校验服务边界（`data_quality`/`data_sanity`/`data_freshness`/`price_validator`）
- 确认 `historical_data_pipeline.py` 是否被 `pipelines/` 取代
- 前端 bundle 分块（echarts 按需）

---

## 不在路线图上（明确不做）

- 用户认证 / 多用户（个人工具，单用户 by-design）
- PostgreSQL 迁移（SQLite WAL 已满足）
- 移动端 App（响应式 Web 够用）
- 第三方数据源（Lixinger 唯一源决策已确认；行业映射缺口为已知限制 F20）
- 止损（v2 决策不做止损，卖出走 4 信号）
- 范围蔓延加新 Pipeline（严格按 26 决策，新需求 → v3）
