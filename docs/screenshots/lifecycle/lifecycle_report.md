# Gojira 用户全生命周期验证报告

- **日期**: 2026-06-07 19:57:15
- **测试标的**: 601398 工商银行
- **总计**: 35 步 | ✅ 27 | ❌ 3 | ⚠️ 5

## 选股发现

| 步骤 | 状态 | 详情 |
|------|------|------|
| 股票池加载 | ❌ FAIL | 表格未渲染 |

## 深度研究

| 步骤 | 状态 | 详情 |
|------|------|------|
| 基本信息 | ✅ PASS | 卡片: ['代码601,398', '行业银行', '持仓数量1', '预案状态armed'] |
| K线图 | ✅ PASS | 图表已渲染 |
| 十大股东 | ⚠️ WARN | 无股东数据 |
| 北向资金 | ⚠️ WARN | 非互联互通标的 |
| 融资融券 | ✅ PASS | 20 条记录 |
| 营收构成 | ⚠️ WARN | 无数据 |
| Qiu评分向导 | ✅ PASS | 模态框已打开 |
| 论点变量编辑 | ✅ PASS | 编辑器已打开 |
| 加入自选 | ⚠️ WARN | 无反馈提示 |

## 制定预案

| 步骤 | 状态 | 详情 |
|------|------|------|
| 跳转预案编辑器 | ✅ PASS | 直接导航 |
| 表单加载 | ✅ PASS | 表单已渲染 |
| 填写论点 | ✅ PASS |  |
| Gates 区域 | ⚠️ WARN | 未找到 gates 文字说明 |
| Position 区域 | ✅ PASS | 仓位配置区域可见 |
| JSON阶梯区域 | ✅ PASS | 阶梯配置区域可见 |
| JSON阶梯内容 | ✅ PASS | buy_ladder=1, sell_ladder=1 |
| 失效规则 | ✅ PASS | 包含在 JSON textarea 的 invalidation 字段中 |
| 模板下拉 | ✅ PASS | 模板选择器存在 |
| 保存预案 | ✅ PASS | 已跳转到: http://localhost:3000/plans |

## 评估草稿

| 步骤 | 状态 | 详情 |
|------|------|------|
| 预案列表 | ✅ PASS | 1 条预案, 状态: ['armed'] |
| 预案评估 | ✅ PASS | 已评估：{"plan_id":3,"code":"601398","new_status":"armed","drafts_emitted":0,"gate_passed":false,"notes":["gates not satisfied — plan sleeps"]} |
| 阶段异常 | ❌ FAIL | Locator.count: Unexpected token "=" while parsing css selector ".ant-card-head-title:has-text('今日订单草稿'), text='今日订单草稿', text='今日无草稿'". Did you mean to CSS.escape it? |

## 执行交易

| 步骤 | 状态 | 详情 |
|------|------|------|
| Cockpit加载 | ✅ PASS |  |
| 现金流目标 | ✅ PASS | 进度条存在 |
| 阶段异常 | ❌ FAIL | Locator.count: Unexpected token "=" while parsing css selector ".ant-card-head-title:has-text('今日订单草稿'), text='今日订单草稿', text='今日无草稿'". Did you mean to CSS.escape it? |

## 持仓管理

| 步骤 | 状态 | 详情 |
|------|------|------|
| 组合概览 | ✅ PASS | 总值=73400.0, 持仓数=N/A |
| 分红预测 | ✅ PASS | 12月预期=0.0 |
| 估值快照 | ✅ PASS | PE%=N/A, PB%=N/A |
| 论点警报 | ✅ PASS | 0 个警报 |

## 复盘

| 步骤 | 状态 | 详情 |
|------|------|------|
| 复盘页面 | ✅ PASS |  |
| 草稿命中率 | ✅ PASS | 统计卡片存在 |
| 审计时间线 | ✅ PASS | 6 条记录 |
| 季度视图 | ✅ PASS | Tab 已切换 |
| 年度视图 | ✅ PASS | Tab 已切换 |

## 截图证据

- [01-universe.png](./01-universe.png)
- [02-kline.png](./02-kline.png)
- [02-margin.png](./02-margin.png)
- [02-north-flow.png](./02-north-flow.png)
- [02-qiu-score.png](./02-qiu-score.png)
- [02-revenue.png](./02-revenue.png)
- [02-shareholders.png](./02-shareholders.png)
- [02-stock-basic.png](./02-stock-basic.png)
- [02-thesis-vars.png](./02-thesis-vars.png)
- [02-watchlist-add.png](./02-watchlist-add.png)
- [03-plan-editor.png](./03-plan-editor.png)
- [03-plan-form.png](./03-plan-form.png)
- [03-plan-gates.png](./03-plan-gates.png)
- [03-plan-invalidation.png](./03-plan-invalidation.png)
- [03-plan-ladders.png](./03-plan-ladders.png)
- [03-plan-position.png](./03-plan-position.png)
- [03-plan-save.png](./03-plan-save.png)
- [03-plan-template.png](./03-plan-template.png)
- [04-plan-evaluate.png](./04-plan-evaluate.png)
- [04-plans-list.png](./04-plans-list.png)
- [05-cashflow-goal.png](./05-cashflow-goal.png)
- [05-cockpit.png](./05-cockpit.png)
- [05-market-cycle.png](./05-market-cycle.png)
- [06-dividend-projection.png](./06-dividend-projection.png)
- [06-portfolio-summary.png](./06-portfolio-summary.png)
- [06-thesis-alerts.png](./06-thesis-alerts.png)
- [06-valuation.png](./06-valuation.png)
- [07-audit-timeline.png](./07-audit-timeline.png)
- [07-hit-rate.png](./07-hit-rate.png)
- [07-review-annual.png](./07-review-annual.png)
- [07-review-monthly.png](./07-review-monthly.png)
- [07-review-quarterly.png](./07-review-quarterly.png)
- [99-final-cockpit.png](./99-final-cockpit.png)
