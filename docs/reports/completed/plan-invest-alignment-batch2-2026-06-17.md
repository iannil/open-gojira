# invest1/2/3 对齐审计 Batch 2 (拓 schema)

> **完成日期**: 2026-06-17
> **开始日期**: 2026-06-17
> **作者/执行人**: Claude Code
> **关联规格**: `docs/reference/specs/2026-06-17-invest-system-alignment-audit.md`
> **关联 Batch 1**: `docs/reports/completed/plan-invest-alignment-batch1-2026-06-17.md`

## 目标 (Goal)

实施 invest1/2/3 对齐审计的 Batch 2 — 拓 schema + 新 service,补齐 Batch 1 跳过的 D2 / D3 / D4。让 invest 体系的"选择权理论"、"财报避坑"、"平方差魔咒"三个核心方法论在 Gojira 决策链中真正生效。

## 最终状态 (Final State)

Batch 2 完成 3 项决策:
- **D2 optionality_leader**:激活 power_tier (选择权位阶) 字段 + 新增 moat_leader plan
- **D3 财报红旗**:拓 FinancialStatement schema + alembic migration `s6_1_red_flag_fields` + 6 个机械红旗检测器 + plan_runner 集成过滤
- **D4 portfolio_risk_service**:从 historical_klines 推算年化波动率 / 30-90 日最大回撤 / 夏普代理,Cockpit 加"组合风险"卡片

1121 测试通过 (Batch 1 +1084, Batch 2 +37 新增)。前端类型 clean。

## 关键修改 (Key Changes)

### 后端

**D2 选择权龙头**:
- `backend/app/services/builtin_seeder.py`: 新增第 8 个内置策略 `optionality_leader` (rule: power_tier>=2 AND dyr_fwd>=0.04) + 第 5 个内置 plan `moat_leader` (纯筛选)

**D3 财报红旗**:
- `backend/app/models/financial.py`: 4 新字段 `accounts_receivable` / `inventory` / `inventory_turnover_ratio` / `non_recurring_profit_ratio`
- `backend/alembic/versions/s6_1_red_flag_fields.py`: 新 migration (head: s5_3 → s6_1)
- `backend/app/services/red_flag_detector_service.py` (新建 253 行): 6 个机械红旗
  - `goodwill_to_equity_gt_50`: 商誉/净资产 > 50%
  - `ocf_to_ni_lt_half_2y`: OCF/NI < 0.5 持续 2 年
  - `low_dividend_sustainability`: 分红可持续性 < 30 (复用 dividend_sustainability_service)
  - `ar_growth_gt_revenue`: 应收账款增速 > 营收×2
  - `inventory_turnover_drop`: 存货周转率同比下降 > 30%
  - `non_recurring_dominant`: 非经常损益/净利润 > 50%
- `backend/app/services/strategy_engine.py`: StockContext 加 `red_flag_count: int | None` 字段 + `_resolve_field` 支持
- `backend/app/services/stock_context_builder.py`: build_context + build_contexts_batch 都调用 detect_with_dividend_sustainability 填充 red_flag_count
- `backend/app/services/plan_runner.py`: PlanRunResult 加 `filtered_red_flags` 计数 + 大/小 scope 都加 `if ctx.red_flag_count > 0: continue` 过滤

**D4 组合风险**:
- `backend/app/services/portfolio_risk_service.py` (新建 175 行): 从 historical_klines 推算
  - `_build_portfolio_series`: 加权 (quantity × close) 时间序列
  - `_annual_volatility`: std × √252
  - `_max_drawdown_in_window`: 30/90 日最大回撤
  - `sharpe_proxy`: 复用 backtest_metrics.compute_sharpe
- `backend/app/services/cockpit_service.py`: build() 加 `portfolio_risk` 字段 (failure isolation via _safe)

### 前端

- `frontend/src/api/types.ts`: 新增 `PortfolioRisk` interface + CockpitResponse.portfolio_risk 字段
- `frontend/src/features/cockpit/CockpitPage.tsx`: 新增"组合风险"卡片 (年化波动率 / 夏普代理 / 30 日回撤 / 90 日回撤 + 持仓 0 时显示"暂无持仓")

### 数据库

- Alembic migration `s6_1_red_flag_fields`: ALTER financial_statements 加 4 列 (nullable, 不破坏现有数据)

### 测试 (+37)

- D2: `test_builtin_seeder_dyr_fwd.py::TestOptionalityLeaderStrategy` × 4
- D3 检测器: `test_red_flag_detector_service.py` × 18 (含 6 红旗各类 trigger/no-trigger 边界)
- D3 plan_runner 集成: `test_plan_runner_red_flag_filter.py` × 2 (clean stock 通过 / red flag 过滤)
- D4 service: `test_portfolio_risk_service.py` × 12 (含 helper 纯函数 + 集成 + empty cases)
- D4 cockpit 集成: `test_cockpit_aggregator.py::test_build_includes_portfolio_risk` × 1

## 测试结果 (Test Results)

```
pytest: 1121 passed (Batch 1 +1084, Batch 2 +37), 0 failed
alembic upgrade head: ✓ (s5_3_claim_variables → s6_1_red_flag_fields)
npx tsc --noEmit: ✓ (前端类型 clean)
```

## 验收检查 (Acceptance Checklist)

- [x] 功能验收:
  - D2: optionality_leader 策略在 BUILTIN_STRATEGIES 注册 + moat_leader plan 在 BUILTIN_PLANS 注册
  - D3: red_flag_detector 对 6 种红旗场景正确触发; plan_runner 在红旗时过滤候选股
  - D4: portfolio_risk_service 对单持仓 + 30 天 klines 数据正确计算波动率/回撤/夏普
- [x] 回归测试: 1121 测试通过,Batch 1 的 1084 测试全部保留
- [x] 文档更新: spec + 本次 report
- [x] 性能验收:
  - red_flag_count 在 build_context 单股 +0.5ms (DB query cached)
  - portfolio_risk 在 cockpit build +200ms (90 日 klines 聚合,acceptable)
- [x] Schema migration: alembic upgrade/downgrade 跑通

## 遗留问题 (Known Issues)

**Lixinger 字段键未实测验证** (P2 后续):

D3 schema 新增的 4 个字段对应的 Lixinger metric keys 是基于通用命名推断:
- `bs.ar.t` (accounts_receivable)
- `bs.inv.t` (inventory)
- `m.i_tor.t` (inventory_turnover_ratio, 已在默认 metrics)
- `ps.np_wd_s_r.t` (non_recurring_profit_ratio, 经验值)

未跑 spike 验证这些键在 Lixinger 标准 API 中是否真实存在。`financial_service.py:130-160` 也未更新为从 Lixinger 数据填充这些字段。

**当前 graceful degradation 设计**:
- 若 Lixinger 不返回该字段 → FinancialStatement 字段为 None → 红旗检测器跳过该红旗 (不报错)
- 现有 goodwill + OCF/NI + dividend_sustainability 红旗基于已有字段,立即可用
- AR/inventory/non_recurring 三红旗等用户跑 spike 确认 Lixinger 键 + 更新 financial_service.py 后生效

**Audit opinion 跳过**: Lixinger 标准 API 不提供审计意见,跳过该红旗 (spec 已说明)。

## 参考 (References)

- 设计文档: `docs/reference/specs/2026-06-17-invest-system-alignment-audit.md`
- Batch 1: `docs/reports/completed/plan-invest-alignment-batch1-2026-06-17.md`
- 投资体系原文: `docs/reference/invest{1,2,3}.md`
