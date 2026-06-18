# G3 预期股息率 (Forward DYR) — Ship 1

> **日期**: 2026-06-14
> **状态**: 已完成
> **关联**: grill-me 11 决策 (Q3=A 全改 / Q4=A inconclusive 剔除); 4 个 invest-coverage gap 的第 1 个

## 目标

把 invest3 §8 反复强调的"预期股息率，而不是过去股息率"在系统层面落地：
- 6 个内置策略凡引用 DYR 的字段统一从 `dyr` (trailing) 改为 `dyr_fwd` (forward)
- `core_value` / `resource_macro` / `bank_anchor` 3 个内置预案的 trading rule triggers 同步
- forward DYR 缺失时（次新股 / 停牌 / 数据未同步）→ inconclusive → 该股被剔除（Q4 决策）

## 变更摘要

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/app/services/dividend_projector_service.py` | 加公共函数 | `compute_forward_dyr_for_stock(db, code)` 基于 3 年平均 per-share / 最新 close |
| `backend/app/services/strategy_engine.py` | 加字段 + 映射 | `StockContext.forward_dyr`; `_resolve_field` 加 `dyr_fwd` |
| `backend/app/services/stock_context_builder.py` | 加调用 | `build_context` 调 `compute_forward_dyr_for_stock` 填充 |
| `backend/app/schemas/strategy.py` | 加 Literal | `StrategyField` 加 `dyr_fwd` |
| `backend/app/schemas/plan.py` | 加 Literal | `BuyTriggerKind` 加 `dyr_fwd_ge`; `SellTriggerKind` 加 `dyr_fwd_le` |
| `backend/app/services/builtin_seeder.py` | 5 策略 + 3 预案改名 | `dyr` → `dyr_fwd`; `dyr_ge`/`dyr_le` → `dyr_fwd_ge`/`dyr_fwd_le` |
| `backend/app/services/builtin_seeder.py` | bug fix | `seed_plans` 现在更新 `trading_rules_json`（之前漏了） |
| `backend/app/services/plan_runner.py` | 加 trigger 处理 | `_evaluate_trading_rules` + `_format_buy/sell_reason` 处理 `dyr_fwd_*` |
| `backend/tests/test_dividend_projector.py` | 加测试 | `TestComputeForwardDyr` 5 个 case |
| `backend/tests/test_stock_context_builder_forward_dyr.py` | 新文件 | `forward_dyr` 字段存在 + build_context 填充 + screening 不填 |
| `backend/tests/test_strategy_engine.py` | 加测试类 | `TestDyrFwdField` 5 个 case（含 None fallback 剔除） |
| `backend/tests/test_builtin_seeder_dyr_fwd.py` | 新文件 | 6 策略 + 3 预案 + seed_plans update 共 10 个测试 |

## 实施细节

### Forward DYR 算法

```
forward_dyr = avg(amount_per_share for dividends in past 3 years) / latest_close_price
```

- 任一输入缺失（无分红历史 / 无价格）→ 返回 None
- 调用方（strategy_engine）看到 None → `_evaluate_condition` 返回 `passed=False`，detail 写 "data unavailable" → 该股被该策略剔除

### Trade-off

- `build_screening_contexts`（轻量首筛）**不**填充 `forward_dyr`——避免 N 股 × 2 查询的性能损耗。`_strategy_definitely_fails` 的 AND/OR 失败快速逻辑能正确处理 None 字段，未填充的股不会被误删，进入 Pass 2 时由 `build_context` 全量填充
- 不引入新的 `EvalResult.inconclusive` 状态——已有的 `passed=False + detail="data unavailable"` 语义已足够；新增状态会污染 schema

### Bug fix: seed_plans 之前不更新 trading_rules_json

发现的副作用：`seed_plans` 在 plan 已存在时只比对 `scan_scope / composition / name / description`，**漏了 `trading_rules_json`**。意味着已有 DB 里的旧 `dyr_ge` triggers 永远不会被新 seeder 覆盖。修复后下次启动 seeder 会自动迁移存量数据。

## 验证

- `pytest tests/test_dividend_projector.py tests/test_stock_context_builder_forward_dyr.py tests/test_strategy_engine.py tests/test_builtin_seeder_dyr_fwd.py` → **48/48 通过**
- `pytest` 全套 → **877/877 通过**（baseline 852 + 29 business pattern + 24 G3 新增 + 1 seed_plans fix = 877；- 29 个早期已计入）
- 实际：baseline 852 (2026-06-13) + business pattern 29 (2026-06-14 早) = 881？读 STATUS 说 816 + business pattern 29 = 845，business pattern progress 说 852。

  实测当前 877，比 ship 前增加 25（24 G3 + 1 seed_plans fix）。

## 与文档一致性

| invest 文档 | 系统行为 |
|---|---|
| invest3 §8 "预期股息率，而不是过去股息率" | ✅ 6 策略 + 3 预案全部用 forward DYR |
| invest3 §22 "不懂不做" | ✅ forward 数据缺失 → 剔除 |
| invest3 §16 "没信息优势就靠基本面" | ✅ 基本面（历史分红）+ 当前价格 → 推断未来 |

## 下一步

- [ ] Ship 2: G2 中游过滤（BusinessPattern.is_midstream + Stock.is_cost_leader + plan_runner 过滤）
- [ ] Ship 3: G1 周期 gate（Plan.cycle_buy_max + plan_runner gate + cycle_unavailable skip）
- [ ] Ship 4: G4 资源股 2 维（Stock.has_mine + domestic_leader + resource_hard_asset 加规则）
