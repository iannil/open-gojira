# 投资体系对齐改造

> 日期：2026-06-06
> 分支：`feature/gojira-investment-system`
> 状态：全部完成

## 目标

对照 `docs/invest1/2/3.md` 描述的投资体系，删除违反投资理论的模块，补齐投资体系要求的自动化能力。

## 完成内容

### Phase 5：清理（删除违反投资体系的模块）
- 删除 screener 模块（5 个文件 + 7 个端点）— 违反"不迷信机械化低估值投资"
- 删除 market sectors 热力图端点 — 投资体系不做板块轮动
- 删除 stats 路由 — 与 cockpit 冗余
- Alembic 迁移：`DROP TABLE screener_templates`

### Phase 6：配置合并 + 四象限目标
- 合并 `portfolio_settings` 到 `cashflow_goals`（消除冗余配置）
- 新增 `quadrant_targets_json` 列（四象限目标配比）
- Alembic 迁移：合并表 + 数据迁移

### Phase 7：商业模式评分 Gate
- Plan DSL 新增 `min_qiu_score` gate（求字理论 0-3 分）
- EvalSnapshot 新增 `qiu_score` 字段
- plan_evaluator._check_gates() 添加 qiu_score 检查

### Phase 8：股息可持续性 + 市场温度计
- 新建 `dividend_sustainability_service.py`（OCF/NI + 分红连续性 + 派息率 + DYR → 0-100 评分）
- Plan DSL 新增 `min_dividend_sustainability` gate
- 新建 `market_temperature_service.py`（基于 PE 分位 → 0-100 温度）
- Plan DSL 新增 `max_market_temperature` gate
- Cockpit 集成市场温度显示

### Phase 9：主题系统 + 论点变量
- 新建 Theme 模型 + CRUD + 暴露分析
- 4 个默认主题：能源安全/资源安全/金融安全/粮食安全
- Plan 新增 `theme_id` 关联
- Stock 新增 `thesis_variables_json`（第一性原理变量）
- Cockpit 集成主题暴露分析

### Phase 10：组合再平衡
- 新建 `rebalance_service.py`（三级：持仓/象限/主题 → 再平衡建议）
- 新增 `weekly_rebalancing_review` 调度任务（周日 10:00）
- Cockpit 集成再平衡建议

### Phase 11：前端增强
- CockpitPage：市场温度指示器 + 主题暴露卡片 + 再平衡建议表格
- PlanEditorPage：新增 qiu_score/dividend_sustainability/market_temperature gate 字段
- StockDetailPage：论点变量编辑器（表格展示 + 模态框编辑）

## 验证结果

- 后端测试：297 passed（从 214 增长到 297）
- 前端构建：✓ built in 206ms
- 无已删除端点的残留引用

## 数据库变更

| 操作 | 表/列 |
|---|---|
| 删除表 | `screener_templates`, `portfolio_settings` |
| 新建表 | `themes` |
| 新增列 | `cashflow_goals`: cash_reserve, quadrant_targets_json, position_plan_json, current_index_pe_pct |
| 新增列 | `plans`: theme_id |
| 新增列 | `stocks`: thesis_variables_json |
| Plan DSL | Gates +min_qiu_score, +min_dividend_sustainability, +max_market_temperature |
