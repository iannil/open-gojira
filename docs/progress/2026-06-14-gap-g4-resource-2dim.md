# G4 资源股 2 维 (Resource Flags) — Ship 4

> **日期**: 2026-06-14
> **状态**: 已完成
> **关联**: grill-me 11 决策 (Q11=B 核心 2 维 has_mine + domestic_leader); 4 个 invest-coverage gap 的最后一个

## 目标

把 invest3 §12 反复强调的"没矿的有色股他会很警惕"+"国内优先"在系统层面落地：
- Stock 加 `has_mine: bool | null` + `domestic_leader: bool | null` 字段
- resource_hard_asset 策略加 2 条 `==` 规则；null = inconclusive → 剔除（与 G3/G2 fallback 一致）
- Seeder 预填 7 个公开案例（BFNY/NSLY/BTGF/CHGF/紫金/山东黄金/中金黄金）

## 变更摘要

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/app/models/stock.py` | 加 2 字段 | `has_mine: bool \| null` + `domestic_leader: bool \| null` (均 indexed) |
| `backend/alembic/versions/t9_1_g4_resource_flags.py` | 新增 migration | stocks 加 2 字段 + 2 index |
| `backend/app/services/strategy_engine.py` | StockContext 加 2 字段 + mapping | `has_mine` / `domestic_leader` |
| `backend/app/schemas/strategy.py` | StrategyField 加 2 literal | `has_mine` / `domestic_leader` |
| `backend/app/schemas/strategy.py` | Condition.value Union 加 bool | `Union[bool, float, str, list[str]]` — bool 放最前避免被 float 强转 |
| `backend/app/services/stock_context_builder.py` | build_context 填充 2 字段 | 从 Stock ORM 读 |
| `backend/app/services/builtin_seeder.py` | resource_hard_asset 加 2 规则 | `has_mine == True` + `domestic_leader == True` |
| `backend/app/services/builtin_seeder.py` | 加 BUILTIN_RESOURCE_LEADERS + seed_resource_leaders | 7 个公开案例预填 |
| `backend/app/services/builtin_seeder.py` | seed_all 调用 seed_resource_leaders | 启动自动预填 |
| `backend/tests/test_strategy_engine.py` | 加 TestResourceFlagsFields | 7 个测试覆盖字段/==/None fallback |
| `backend/tests/test_builtin_seeder_dyr_fwd.py` | 加 TestResourceHardAssetG4Rules | 2 测试验证策略规则 |
| `backend/tests/test_plan_runner_midstream_filter.py` | 加 TestSeedResourceLeaders | 2 测试验证 seeder 预填 |

## 实施细节

### Bool 类型 Pydantic 陷阱（顺手修了一个 schema bug）

`Condition.value: Union[float, str, list[str]]` — Pydantic 2 按顺序尝试，`True` 被强转为 `1.0`。导致 `{"field": "has_mine", "op": "==", "value": True}` 实际比较 `"True" == "1.0"` → False。

修复：`Union[bool, float, str, list[str]]` — bool 放最前，`True` 保持 bool 类型。

### 7 个 BUILTIN_RESOURCE_LEADERS 预填

| Code | 公司 | Pattern | has_mine | domestic_leader |
|---|---|---|---|---|
| 600989 | 宝丰能源 (BFNY) | 煤化工 | true | true |
| 600219 | 南山铝业 (NSLY) | 电解铝 | true | true |
| 002170 | 芭田股份 (BTGF) | 磷化工 | true | true |
| 002895 | 川恒股份 (CHGF) | 磷化工 | true | true |
| 601899 | 紫金矿业 | 铜矿 | true | true |
| 600547 | 山东黄金 | 黄金矿企 | true | true |
| 600489 | 中金黄金 | 黄金矿企 | true | true |

注：与 G2 BUILTIN_COST_LEADERS 有 2 个 code 重叠（BFNY/NSLY）— 这是对的：它们既是中游加工的 cost_leader，也是有矿/国内优先的资源股。

### resource_hard_asset 策略最终规则

```python
{
    "slug": "resource_hard_asset",
    "rule": {
        "logic": "AND",
        "conditions": [
            {"field": "dyr_fwd", "op": ">=", "value": 0.04},      # G3 预期股息率
            {"field": "pb_pct_10y", "op": "<=", "value": 0.50},
            {"field": "has_mine", "op": "==", "value": True},      # G4 有矿优先
            {"field": "domestic_leader", "op": "==", "value": True}, # G4 国内优先
        ],
    },
}
```

4 维 AND — 全部满足才通过。任一为 null = inconclusive → 剔除（与 G3/G2 fallback 一致）。

### 范围之外 (留 v2)

Q11 决策明确：扩产预期 (`expansion_outlook`) + 地缘税收 (`geo_risk`) 不在 v1 范围。文档反复提及但没有具体可观察指标，且 Lixinger 无对应数据。v2 可基于同样模式扩展。

## 验证

- `pytest tests/test_strategy_engine.py::TestResourceFlagsFields -v` → **7/7 通过**
- `pytest tests/test_builtin_seeder_dyr_fwd.py::TestResourceHardAssetG4Rules -v` → **2/2 通过**
- `pytest tests/test_plan_runner_midstream_filter.py::TestSeedResourceLeaders -v` → **2/2 通过**
- `pytest` 全套 → **907/907 通过**（baseline 896 + 11 G4 新增）
- `alembic upgrade head` → ✅ `t9_1_g4_resource_flags` 应用成功

## 与文档一致性

| invest 文档 | 系统行为 |
|---|---|
| invest3 §12 "没矿的有色股他会很警惕" | ✅ resource_hard_asset 要求 `has_mine=True` |
| invest3 §12 "国内优先" | ✅ resource_hard_asset 要求 `domestic_leader=True` |
| invest3 §12 资源股体系 7 维 | ✅ 覆盖 5/7（资源禀赋=industry, 估值=pb_pct_10y, 股息=dyr_fwd, +有矿, +国内）；剩 2 维（管理/扩产/地缘）v2 |
| invest3 §22 "不懂不做" | ✅ has_mine=null / domestic_leader=null → 剔除 |

## 4 个 gap 全部 ship 完成

| Ship | Gap | 文档来源 | 核心改动 | 测试增量 |
|---|---|---|---|---|
| 1 | **G3** 预期股息率 | invest3 §8 | 6 策略 + 3 预案改 forward DYR | +25 |
| 2 | **G2** 中游过滤 | invest3 §13 | Pattern.is_midstream + Stock.is_cost_leader + plan_runner 过滤 | +9 |
| 3 | **G1** 周期 gate | invest3 §5 | Plan.cycle_buy_max + plan_runner gate + cycle_unavailable skip | +10 |
| 4 | **G4** 资源股 2 维 | invest3 §12 | Stock.has_mine + domestic_leader + resource_hard_asset 加规则 | +11 |
| **总计** | | | **4 migration + 9 模型字段 + 6 策略 + 3 预案 + 2 plan_runner 过滤** | **+55** |

最终测试: **852 → 907**（+55）。0 失败。Alembic head: `t9_1_g4_resource_flags`。

## 下一步

- [ ] 写 `docs/reference/specs/2026-06-14-invest-coverage-gaps-closure.md` — 4 gap 收口规格
- [ ] 写 `docs/active/roadmap.md` 更新（删 P1 G1-G4 相关项，加 v2 候选如前端 UI / 扩产预期 / 地缘税收）
- [ ] 更新 `docs/progress/STATUS.md` — 测试数、模块清单、新增字段
