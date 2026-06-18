# G2 中游过滤 (Midstream Filter) — Ship 2

> **日期**: 2026-06-14
> **状态**: 已完成
> **关联**: grill-me 11 决策 (Q5=A Pattern 级 / Q6=B Seeder 预填 / Q7=B plan_runner 过滤); 4 个 invest-coverage gap 的第 2 个

## 目标

把 invest3 §13 反复强调的"中游企业一般不要投资，除非它是成本最低的那个...这是他筛掉大量公司的一把刀"在系统层面落地：
- BusinessPattern 标 `is_midstream` (17 patterns 中 2 true: 煤化工 / 电解铝)
- Stock 标 `is_cost_leader` (Seeder 预填 BFNY/NSLY; null = inconclusive → 剔除)
- plan_runner 扫描后过滤：midstream 非 cost_leader → 不进候选池
- Plan 加 `disable_midstream_filter` 逃生口 (默认 false = 启用)

## 变更摘要

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/app/models/business_pattern.py` | 加字段 | `is_midstream: bool` (默认 false) |
| `backend/app/models/stock.py` | 加字段 | `is_cost_leader: bool \| null` (nullable, indexed) |
| `backend/app/models/plan.py` | 加字段 | `disable_midstream_filter: bool` (默认 false) |
| `backend/alembic/versions/t7_1_g2_midstream_filter.py` | 新增 migration | 3 表加字段 + 1 index |
| `backend/app/services/builtin_seeder.py` | 标 patterns | 煤化工/电解铝 is_midstream=true; 其他默认 false |
| `backend/app/services/builtin_seeder.py` | 加 BUILTIN_COST_LEADERS + seed_cost_leaders() | 预填 600989 (宝丰) / 600219 (南山铝业) |
| `backend/app/services/builtin_seeder.py` | seed_business_patterns 同步 is_midstream | 已存在的 patterns 也会更新该字段 |
| `backend/app/services/builtin_seeder.py` | seed_all 调用 seed_cost_leaders | 启动时自动预填 |
| `backend/app/services/plan_runner.py` | 加 `_should_filter_as_midstream_non_leader` 函数 | 纯函数,6 个 unit test 覆盖 |
| `backend/app/services/plan_runner.py` | 接入扫描循环 | Pass 2 + small-scope 两处都接入 |
| `backend/app/services/plan_runner.py` | PlanRunResult 加 `filtered_midstream_non_leader` 计数 | 用于 audit_log / 前端可视化 |
| `backend/tests/test_plan_runner_midstream_filter.py` | 新文件 | 9 个测试 (6 unit + 1 seed patterns + 2 seed cost_leaders) |

## 实施细节

### 过滤规则（与 Q5/Q6/Q7 决策一致）

```
_should_filter_as_midstream_non_leader(db, stock, plan) -> bool:
  1. plan.disable_midstream_filter == True → return False (逃生口)
  2. stock.business_pattern_id is None → return False (未关联 pattern,无法判定)
  3. pattern = db.get(BusinessPattern, stock.business_pattern_id)
  4. pattern is None OR pattern.is_midstream == False → return False (上游/下游/金融/公用)
  5. return stock.is_cost_leader is not True  # null or False → filter
```

### 接入位置

在 plan_runner 的两处扫描循环中，strategy 评估通过后、`passed_codes.append` 之前：

```python
strategy_results, passed = _evaluate_strategies(strategies, ctx, comp)
if not passed:
    continue

# G2 midstream filter
stock = db.get(Stock, code)
if stock is not None and _should_filter_as_midstream_non_leader(db, stock, plan):
    result.filtered_midstream_non_leader += 1
    continue

passed_codes.append(code)
```

### Null 语义（与 G3 fallback 哲学一致）

`is_cost_leader = None`（用户未标）= inconclusive → 视为非 leader → 剔除。这是文档 §22 "不懂不做" 的直接体现 — 中游股没明确判定为 cost_leader 就不买。

只有 `is_cost_leader = True` 才通过。Seeder 预填的 BFNY/NSLY 是 True，其他中游股 null 状态下被自动剔除，等用户主动标记。

### 17 patterns 标记结果

| Pattern | is_midstream |
|---|---|
| 煤化工 | **true** |
| 电解铝 | **true** |
| 其他 15 个（纯煤/铝上游/磷化工/钾肥/铜矿/锡矿/黄金矿企/黄金零售/银行/保险/证券/电力/植物生长剂/药店零售/旅游景区） | false |

注：`磷化工` 虽然 industry 字符串里含"化工"，但 first_principle_variable 是"磷矿品位/储量"，本质是有矿的上游，不是无矿的中游加工 → `is_midstream=false`。

### Seeder 预填 cost_leaders

| Code | 公司 | Pattern | is_cost_leader |
|---|---|---|---|
| 600989 | 宝丰能源 (BFNY) | 煤化工 | true (煤自给 + 技术路线领先) |
| 600219 | 南山铝业 (NSLY) | 电解铝 | true (印尼电力套利) |

用户可在 UI/PATCH 上扩展（v1 暂未实现 UI，留 v2）。

## 验证

- `pytest tests/test_plan_runner_midstream_filter.py -v` → **9/9 通过**
  - 6 unit test 覆盖纯函数（filter / keep / disable / no-pattern 各分支）
  - 1 test 验证 seeder 标 patterns
  - 2 test 验证 seed_cost_leaders 行为
- `pytest` 全套 → **886/886 通过**（baseline 877 + 9 G2 新增）
- `alembic upgrade head` → ✅ migration 应用成功
- `alembic heads` → `t7_1_g2_midstream_filter (head)`

## 与文档一致性

| invest 文档 | 系统行为 |
|---|---|
| invest3 §13 "中游非成本最低一律不要投" | ✅ plan_runner 自动剔除 midstream non-cost-leader |
| invest3 §22 "不懂不做" | ✅ `is_cost_leader=null` → 剔除 |
| invest2 显式案例 BFNY/NSLY | ✅ seeder 预填为 True，开局即用 |

## 范围之外 (留 v2)

- **前端 UI**: StockDetail "成本领先" 勾选 + IndustryContextPanel 显示
- **PATCH /stocks/{code}/cost-leader endpoint**: 当前无 API 让用户改 is_cost_leader
- **Candidates 加 "中游过滤"列**: 显示哪些股被剔除 + 原因
- **plan 级 disable_midstream_filter UI 开关**: 当前需要直接改 DB

这些前端工作可批量在 Ship 4 (G4) 完成后一起做。

## 下一步

- [ ] Ship 3: G1 周期 gate (Plan.cycle_buy_max + plan_runner gate + cycle_unavailable skip)
- [ ] Ship 4: G4 资源股 2 维 (Stock.has_mine + domestic_leader + resource_hard_asset 加规则)
