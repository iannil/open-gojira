# G1 周期 gate (Cycle Gate) — Ship 3

> **日期**: 2026-06-14
> **状态**: 已完成
> **关联**: grill-me 11 决策 (Q8=A 仅买入 gate / Q9=A cycle_buy_max 默认 mid / Q10=C plan-level skip); 4 个 invest-coverage gap 的第 3 个

## 目标

把 invest3 §5 反复强调的"大盘整体高位时回撤会无差别打击"在系统层面落地：
- Plan 加 `cycle_buy_max: str`（默认 "mid"）— 允许产生 BUY drafts 的最高周期位置
- 5 档 cycle position: `extreme_low < low < mid < high < extreme_high`
- plan_runner 在 trading rules 评估前检查：`current_rank > plan_max_rank` → 抑制 BUY drafts（SELL 不影响）
- cycle 数据缺失（Lixinger 挂 / CashflowGoal 未配）→ 整个 plan run 跳过，写 plan-level audit_log

## 变更摘要

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/app/models/plan.py` | 加字段 | `cycle_buy_max: str` (默认 "mid") |
| `backend/alembic/versions/t8_1_g1_cycle_gate.py` | 新增 migration | plans 表加字段 |
| `backend/app/services/plan_runner.py` | 加纯函数 | `_cycle_position_rank(pos)` + `_check_cycle_gate(plan_max, current)` |
| `backend/app/services/plan_runner.py` | run_plan 开头加 cycle 可用性检查 | pe_pct_10y=None → 写 audit_log + 返回 |
| `backend/app/services/plan_runner.py` | trading rules 评估前加 cycle gate | block BUY drafts when cycle > max |
| `backend/app/services/plan_runner.py` | PlanRunResult 加 3 字段 | cycle_position / cycle_buy_blocked / cycle_unavailable_skipped |
| `backend/tests/test_plan_runner_cycle_gate.py` | 新文件 | 10 测试 (9 unit + 1 integration) |

## 实施细节

### Cycle rank 映射

```python
_CYCLE_POSITION_RANKS = {
    "extreme_low": 0,   # PE 历史分位 80-100% (最便宜)
    "low": 1,           # 60-80%
    "mid": 2,           # 40-60%
    "high": 3,          # 20-40%
    "extreme_high": 4,  # 0-20% (最贵)
}
```

注意：分位数 0.80 = 当前 PE 比历史 80% 时间低 = 极度低估 → rank 0（风险最低）。

### Gate 逻辑

```python
_check_cycle_gate(plan_max, current) -> bool:
    return _cycle_position_rank(current) > _cycle_position_rank(plan_max)
```

`current_rank > max_rank` → True → BUY drafts 被抑制。

例：
- plan.cycle_buy_max="mid" (rank 2), current="high" (rank 3) → 3>2 → block
- plan.cycle_buy_max="low" (rank 1), current="mid" (rank 2) → 2>1 → block
- plan.cycle_buy_max="extreme_high" (rank 4) → 任何 current 都不会 block（逃生口）

### 接入位置

在 trading rules 评估的 for 循环开头：

```python
# G1: cycle gate suppresses BUY side
if side == "BUY" and cycle_blocks_buy:
    result.cycle_buy_blocked += 1
    continue
```

SELL 不受影响（cycle=high 可能合法触发止盈卖出）。

### 数据缺失 fallback（Q10=C）

在 run_plan 开头：

```python
cycle = assess_cycle(db)
if cycle.pe_pct_10y is None:
    result.cycle_unavailable_skipped = True
    result.errors.append("cycle_assessment data unavailable — plan run skipped")
    return result
```

理由：invest3 §5 "大盘整体高位时回撤会无差别打击" — 如果不知道大盘位置就不该下决定。Fallback 到 mid 放行会产生基于过期数据的 draft（危险）。

### 现有测试影响

`test_plan_runner_constraints.py` 等已存在的 plan_runner 集成测试现在会调用 `assess_cycle`：
- Lixinger 在测试环境工作（实测 PE pct ~23.5，cycle="low"）
- cycle="low" (rank 1) < 默认 cycle_buy_max="mid" (rank 2) → 不 block
- 所有现有 31 个测试照常通过

**注意**：这给测试引入了网络依赖。如果 Lixinger token 失效（G10 P0-1），assess_cycle 会退到 CashflowGoal fallback；若 CashflowGoal.current_index_pe_pct 也未配，plan run 会跳过。`test_plan_skipped_when_cycle_unavailable` 测试明确覆盖了这条路径。

## 验证

- `pytest tests/test_plan_runner_cycle_gate.py -v` → **10/10 通过**
  - 6 test 覆盖 `_cycle_position_rank` 5 档 + 异常
  - 3 test 覆盖 `_check_cycle_gate` block / pass / disable 三种语义
  - 1 test 覆盖 `run_plan` 在 cycle unavailable 时早返回
- `pytest` 全套 → **896/896 通过**（baseline 886 + 10 G1 新增）
- `alembic upgrade head` → ✅ `t8_1_g1_cycle_gate` 应用成功

## 与文档一致性

| invest 文档 | 系统行为 |
|---|---|
| invest3 §5 "大盘整体高位时不要融资加杠杆" | ✅ cycle=high/extreme_high 时 plan_runner 抑制 BUY drafts |
| invest3 §5 "中位正常持有" | ✅ cycle_buy_max 默认 "mid"，允许 mid 时正常买入 |
| invest3 §5 "极高位尽量空仓" | ✅ cycle=extreme_high 强制 block BUY |
| invest3 §5 "低位敢重仓" | ✅ cycle_buy_max 可改 "low" / "extreme_low" 仅在低位买入 |

## 范围之外 (留 v2)

- **Plan UI 加 cycle_buy_max 下拉** (5 档 enum)
- **Cockpit 显示当前 cycle_position + 是否阻断 plan**
- **Cockpit "为什么今天没 draft" 提示** (cycle_unavailable / cycle_blocked)
- **G1 v2: cycle=high 时主动触发 SELL drafts** (rebalance_service 联动)

## 下一步

- [ ] Ship 4: G4 资源股 2 维 (Stock.has_mine + domestic_leader + resource_hard_asset 加规则)
- [ ] 全部 ship 后写 `docs/reference/specs/2026-06-14-invest-coverage-gaps-closure.md` 收口
