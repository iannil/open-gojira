# 投资体系对齐审计 (2026-06-17)

> 日期: 2026-06-17
> 状态: 已确认 + 已验证 + Batch 4 已 ship (二次 grill 复核 + 4 项新决策实施完毕)
> 关联: `docs/progress/STATUS.md` | `docs/reference/invest{1,2,3}.md` | `docs/reference/specs/2026-06-14-comprehensive-audit.md`

## 背景

用户指令: 梳理 `docs/reference/*` (invest1/2/3) 的内容,并审计当前项目是否已经对照实现。

`docs/reference/invest{1,2,3}.md` 三份文档构成完整投资体系:
- **invest1**: 核心方法论 (第一性原理 / 求字理论→选择权理论 / 现金流为王 / 盲盒可视化 / 估值锚 / 仓位管理"人之道" / 破除妄念 / 30% 止盈)
- **invest2**: MR Dang 5 层金字塔 (哲学 / 选股 / 战术 / 风控 / 配置) — 29 条原则 + 10 条核心诫命
- **invest3**: 祝融说映射 + 案例 (天阶 / 玄阶 / 地阶) + 价值投资三大误区

审计发现: 整体骨架已良好对齐 invest1/2/3,但存在若干"基础设施已建,策略层未接"的明显断层。本次 grill-me 产出 11 项决策。

---

## 审计结果 (已实现 vs 缺口)

### 已良好对齐 invest1/2/3 (✓)

| invest 要点 | Gojira 实现 |
|---|---|
| 第一性原理 (每行业抓核心变量) | `BusinessPattern.first_principle_variable` + 19 业务模式 |
| 资源股 7 维 (禀赋/成本/估值/股息/管理/地缘/扩产) | `resource_hard_asset` 策略 6 维 + `BUILTIN_RESOURCE_LEADERS` 7 只 |
| 银行 3 维 (股息/地域/现金流) | `bank_analyzer_service` 完整 3 维 (盲盒可视化) |
| 现金流为王 (OCF/NI ≥ 1) | `cashflow_asset` 策略 + `bank_analyzer` OCF/NI 维 |
| 估值锚 (PE/PB 10y 分位) | `undervalued_entry` 策略 ≤30% |
| 股息率兜底 (5%) | `bank_select` 5% + `core_value` plan |
| 周期评估 (5 档 + 仓位建议) | `cycle_assessment_service` (extreme_low→extreme_high) |
| 仓位纪律 (3-4 只 / 单只 10-50% / 行业 15%) | `position_advisor_service` 硬约束 |
| 加权 DYR 4-5% 组合目标 | `holding_service.target_weighted_dyr=0.045` + 低目标 warning |
| 论点证伪 (渣男思维) | `thesis_monitor` v2 双源 + breach_when 机械字段 |
| DisciplineChecklistModal (双层闸门) | UI 强制闸门 |
| 平方差魔咒 (回测维度) | `backtest_metrics.compute_max_drawdown` + sharpe |
| 业务模式 (生产资料视角) | 19 个 `BUILTIN_BUSINESS_PATTERNS` + theme_id |
| 4 主线 (能源/资源/金融/粮食安全) | 4 个 theme + 对应业务模式 |
| Lixinger 唯一数据源 | `lixinger_client` + 5 个 Pipeline |

### 已识别的差距与决策 (本次 grill 产出)

详见下文 11 项决策。

---

## 决策清单 (11 项 + 1 项命名重构)

### D1: `bank_select` 策略接入 bank_analyzer 三维

**问题**: `bank_analyzer_service.analyze()` 已实现 invest2 §11 完整 3 维 (股息 + 地域 + OCF/NI),输出 `blind_box_verdict`。但 `bank_select` 策略 rule_json 只用 1 维 (industry=bank + dyr_fwd≥5%)。候选池可能纳入"高股息但人口流出地+现金流差"的银行,违反 invest2 §11。

**决策**: 加 1 个 condition 到 `bank_select`:
```python
{"field": "bank_blind_box", "op": "==", "value": "可见"}
```
严格对齐 invest2 §11"挑能看见东西的"。`blind_box_verdict` 字段已在 StockContext (`stock_context_builder.py:226`) 和 `_resolve_field` (`strategy_engine.py:69`) 就绪。

**实施**: 改 `builtin_seeder.py:73-79` 的 bank_select rule_json + alembic migration 若 rule_json 是 immutable。

### D2: 新增 `optionality_leader` 策略 (power_tier 激活)

**问题**: invest1 §二核心方法论"求字理论"在代码层全部建模完毕 (`BusinessPattern.power_tier_baseline` / `Stock.qiu_score` / StockContext.power_tier / strategy_engine 支持),但 **0 处** 策略使用。基础设施空转。

**决策**: 新增独立策略 `optionality_leader`:
```python
{
    "slug": "optionality_leader",
    "name": "选择权龙头",
    "description": "选择权位阶≥2 (上游+政府求你) 且 预期股息率≥4%",
    "rule": {
        "logic": "AND",
        "conditions": [
            {"field": "power_tier", "op": ">=", "value": 2},
            {"field": "dyr_fwd", "op": ">=", "value": 0.04},
        ],
    },
}
```
不修改现有 6 策略。可加入 `core_value` plan 或独立"选择权" plan。

### D2-命名: "求字理论" → "选择权理论"

**用户指令 (2026-06-17)**: 求字理论改为选择权理论,本质一样 (谁决定选择谁),文案不同。

**映射**:
| 旧 | 新 |
|---|---|
| 求字理论 | 选择权理论 |
| 3 求 (上游/下游/政府都求你) | 3 层选择权 (对三方完全选择权 / 定价权垄断) |
| 2 求 (上游+政府求) | 2 层选择权 (稀缺资源/核心技术) |
| 1 求 (平等对话) | 1 层选择权 (双向选择) |
| 0 求 (两头受气) | 0 层选择权 (被单向选择) |

**实施影响**:
- **字段名保留**: `power_tier` / `power_tier_baseline` (字段名内部稳定,改字段需 alembic migration,不值)
- **文档/UI 改文案**: model docstring (`business_pattern.py:5`) / builtin_seeder 注释 / STATUS.md / MEMORY.md / CandidatesPage 显示用"选择权位阶"
- **策略命名**: `power_player` (D2 原名) → `optionality_leader`

### D3: 财报红旗 (完整拓 schema + Lixinger)

**问题**: invest1 §三 + invest2 §10 明确"财报避坑",但当前 0 红旗检测,4 个内置 plan 的 `invalidation:[]` 字段全空。

**决策**: **完整版** — 拓 schema + Lixinger endpoint + 6-8 个机械红旗检测器。

**新增 schema 字段** (`FinancialStatement`):
- `accounts_receivable` (应收账款)
- `accounts_receivable_pct_change` (应收同比)
- `inventory` (存货)
- `inventory_turnover_ratio` (存货周转率)
- `non_recurring_profit` (非经常性损益)
- `audit_opinion` (审计意见: "standard_unqualified" / "qualified" / "adverse" / "disclaimer")

**新增 service**: `red_flag_detector_service` 输出 `red_flag_count: int` + `red_flags: list[str]`。

**6-8 个机械红旗**:
1. `goodwill / net_assets > 0.5` (商誉雷)
2. `ocf_to_ni < 0.5 持续 2 年` (利润虚高)
3. `accounts_receivable_growth >> revenue_growth` (伪造销售)
4. `inventory_turnover 同比下降 > 30%` (存货积压)
5. `non_recurring_profit / net_profit > 0.5` (非经常损益依赖)
6. `audit_opinion != "standard_unqualified"` (非标审计)
7. `dividend_sustainability < 30` (分红不可持续,已有分数可直接复用)

**接入方式**: 填入 4 个内置 plan 的 `invalidation:[]` 字段作为 hard invalidation (从候选池剔除),不是反向策略。理由: invest2 §10"避坑"是 plan 层级 hard invalidation。

**Lixinger API 扩展**: 需调研 `accounts_receivable` / `inventory` / `non_recurring` 是否在 Lixinger 财务端点提供。若提供则自动同步,否则 manual 输入。

### D4: 新增 `portfolio_risk_service` (平方差魔咒实时指标)

**问题**: invest2 §7"平方差魔咒"是选择高股息/低估值/硬资产的理论根据,但当前 max_drawdown 仅在 backtest 路径,实时组合波动率缺失。

**决策**: 新增 `portfolio_risk_service.compute_current_metrics()`:
- 输入: 当前持仓 + historical_klines
- 输出: `{annual_volatility, max_drawdown_30d, max_drawdown_90d, sharpe_proxy}`
- 接入: Cockpit "组合风险" 卡片

**不做硬约束**: 不触发 SystemAlert,不阻塞 plan_runner。理由:
1. invest2 §7 是"为什么买这类资产"的理由,不是机械交易规则
2. 波动率超阈触发减仓 → 与 cycle_assessment 高位 warning 重复
3. 展示给用户用 invest2 §7 视角自我评估

### D5: `extreme_high` Cycle 升级 blocker (invest2 §5 硬纪律)

**问题**: invest2 §5"极高高位尽量空仓"是硬纪律,但 `position_advisor_service:198-202` 仅发 warning,`can_open_new` 仍为 True。

**决策**: 升级规则:
```python
if cycle_position == "extreme_high" and not already_held:
    blockers.append("市场极度高估 (PE 分位≥90%),不开新仓 (invest2 §5)")
```
**保留"加仓赢家"通道**: `already_held` 时不 blocker (invest1 §二"去弱留强"在任何位置都应保留强者)。

`high` (PE 分位 70-90%) 仍是 warning,留给用户判断。

### D6: 认知边界 (反向策略 + plan invalidation)

**问题**: invest2 §13 明确三类禁投 (高估值科技 / 无优势中游 / 热点末端),当前 0 实现。但 BFNY/NSLY 是中游且 cost_leader (天阶),关键区分是"是否 cost_leader"。

**决策 (双管齐下)**:

**A. 新增反向策略 `avoid_overvalued_tech`**:
```python
{
    "slug": "avoid_overvalued_tech",
    "name": "回避高估值题材",
    "description": "PE 历史高位 + 低股息 = 高估值科技/题材股",
    "rule": {
        "logic": "OR",
        "conditions": [
            {"field": "pe_pct_10y", "op": ">=", "value": 0.90},
            {"field": "pe_pct_10y", "op": ">=", "value": 0.70},
            {"field": "dyr_fwd", "op": "<", "value": 0.02},
        ],
    },
}
```
注: 第 2 个 condition 是简化的"PE 高位",第 3 个是"低股息";OR 内层是 AND 语义 (需 D3 schema 后改 nested logic)。

**B. 4 个内置 plan `invalidation:[]` 加中游非 cost_leader 排除**:
```python
"invalidation": [
    {
        "description": "中游非成本龙头排除 (invest2 §13)",
        "rule": {
            "logic": "AND",
            "conditions": [
                {"field": "is_midstream", "op": "==", "value": True},
                {"field": "is_cost_leader", "op": "==", "value": False},
            ],
        },
    },
]
```
需 strategy_engine 支持 `is_midstream` + `is_cost_leader` 字段 (后者已建,前者需加 StockContext 字段)。

**热点末端跳过**: 拥挤度需换手率数据,Lixinger 不直接提供,延后。

### D7: 30% 止盈保持现状 + 文档化理由

**问题**: invest1 §13"新手 30% 止盈"仅 `core_value` 符合 (`resource_macro` 50%, `bank_anchor` 用 DYR≤3%, `contrarian_scan` 无)。

**决策**: 保持现状,在 `builtin_seeder.py` 注释 + STATUS.md + seeder 源文档解释各 plan 止盈选择的理由:
- `core_value` 30%: 严格贴 invest1 §13 新手
- `resource_macro` 50%: 资源股周期弹性大 (铜/铝/磷肥常超 50%)
- `bank_anchor` DYR≤3%: invest2 §8 更高级 ("用股息率做买卖决策")
- `contrarian_scan` 无交易规则: 纯筛选,留给用户判断

invest1 §13 原文是"**新手**可以设 30%" — 言下之意: 老手可按标的性质调整。强行统一反而偏离分类施策思想。

### D8: 资产配置维持股票范围 + 文档边界

**问题**: invest2 §23 资产配置层 (房产降权 + 黄金实物 + 货基替代 + 4 块权益) 超出 Gojira "股票自动驾驶舱" 范围。

**决策**: 维持股票范围。在 CLAUDE.md + STATUS.md "项目范围" 明确写: "房产/黄金实物/货币基金不在 Gojira 范围,加权 DYR 4-5% 已是 invest2 §23 的可量化部分。"

理由:
1. CLAUDE.md 项目定位明确是"个人**股票**自动驾驶舱"
2. 房产/黄金实物无公开 API 可自动化
3. 加权 DYR 4.5% 已实现 (`holding_service.target_weighted_dyr=0.045`)
4. 扩展会违反原则 (2) "架构尽可能简化"

### D9: 跳过 100 万门槛机械实现

**问题**: invest2 §24"100 万门槛"是元层面建议 (劳动收入 vs 投资收入权重)。

**决策**: 跳过机械实现。invest2 §24 是叙述性建议,不是交易规则。个人用户自行判断本金状态。

### D10: 跳过 EPS 真相 + 文档化限制

**问题**: invest1 §3"剔除永续债/优先股"需 Lixinger 不提供的数据 (永续债利息仅在年报附注披露)。

**决策**: 跳过 + 文档化已知限制。在 STATUS.md "已知限制" 记: "Lixinger 不提供永续债/优先股利息,adjusted_eps 未实现。用户需手动查年报附注。"

invest1 §3 是"现金流为王"章节的辅助点 (1 个子弹点),优先级 P3。

---

## Ship 计划 (两批)

### Batch 1: 低风险高价值 (~2-3 天)

**特点**: 不拓 schema,只动策略/plan rule_json + 文案。无 alembic migration。

| 任务 | 估时 | 涉及文件 |
|---|---|---|
| D1 bank_select 加 bank_blind_box==可见 | 0.5 天 | `builtin_seeder.py` |
| D5 position_advisor extreme_high blocker | 0.5 天 | `position_advisor_service.py` |
| D6 avoid_overvalued_tech 策略 + 4 plan 中游 invalidation | 1 天 | `builtin_seeder.py` + strategy_engine 加 `is_midstream`/`is_cost_leader` resolve |
| D7 止盈文档化 | 0.2 天 | `builtin_seeder.py` 注释 + STATUS.md |
| D8 资产配置文档边界 | 0.2 天 | CLAUDE.md + STATUS.md |
| D9 + D10 文档化已知限制 | 0.2 天 | STATUS.md |
| 求字→选择权 命名重构 | 0.3 天 | model docstring + builtin_seeder 注释 + STATUS.md + MEMORY.md |

**验收**: 跑现有 1075 测试 + 验证 bank_select 新规则在工商银行等真实案例上行为正确 + 验证 extreme_high blocker 在测试 fixture 下生效。

### Batch 2: 拓 schema + 新 service (~5 天)

**特点**: 拓 schema,需 alembic migration + Lixinger endpoint 调研。

| 任务 | 估时 | 涉及文件 |
|---|---|---|
| D3 财报红旗完整版 (schema + Lixinger + 6-8 检测器 + plan invalidation) | 2-3 天 | `financial.py` + alembic + `lixinger_client.py` + `red_flag_detector_service.py` (新) + `builtin_seeder.py` |
| D2 optionality_leader 策略 | 0.5 天 | `builtin_seeder.py` |
| D4 portfolio_risk_service + Cockpit 卡片 | 1-1.5 天 | `portfolio_risk_service.py` (新) + `cockpit_service.py` + 前端 Cockpit 组件 |

**前置**: D3 需先调研 Lixinger 是否提供 `accounts_receivable` / `inventory` / `non_recurring` / `audit_opinion`。若不提供,降级为 manual 输入或缩小红旗集合。

**验收**: 新 schema migration 跑通 + 红旗检测器对 6-8 个边界 case 输出正确 + portfolio_risk 在 historical_klines 空时不 crash + Cockpit 卡片在持仓 0 时显示"无持仓"。

---

## 与之前决策的关系

| 之前决策 | 当前审计关系 |
|---|---|
| 2026-06-13 重审 (production-readiness) | 7 项已 ship,本轮聚焦 invest1/2/3 对齐 |
| 2026-06-14 全面审计 (backtest) | backtest 路径已通 (max_drawdown 已有),本轮补实时组合风险 |
| 2026-06-15 三层完成度审计 | 已识别 thesis monitor v2 完成,本轮无新增架构发现 |
| 2026-06-17 thesis monitor v2 ship | 完美对应 invest1 "渣男思维" 自动化,本轮无新增论点证伪相关决策 |

---

## 投资体系对齐度评估 (Batch 3 验证后实际)

| invest 维度 | 当前对齐度 (Batch 3 后) | 说明 |
|---|---|---|
| invest1 第一性原理 | 80% | D6 加深禁投 |
| invest1 求字→选择权理论 | 85% | D2 激活 + 命名重构 |
| invest1 现金流为王 | 95% | 已对齐 |
| invest1 银行盲盒 | 95% | D1 接入 |
| invest1 估值锚 | 95% | 已对齐 |
| invest1 仓位管理 | 100% | D5 blocker |
| invest1 30% 止盈 | 75% | D7 文档化 |
| invest2 §10 财报避坑 | 85% | D3 6/7 红旗生效 (spike 验证后); 扣非净利率红旗死代码 |
| invest2 §13 三类禁投 | 80% | D6 双管齐下, midstream filter 在 plan_runner 而非 invalidation |
| invest2 §7 平方差魔咒 | 85% | D4 实时 portfolio_risk_service |
| invest2 §23 资产配置 | 60% | D8 文档边界 + Batch 3 决定 4 块分类不引入 Plan.cyclicality |
| invest2 §24 100 万门槛 | 10% | D9 跳过 |
| invest1 §3 EPS 真相 | 10% | D10 跳过 |
| 进度条战法 (invest1 §一) | 0% | Batch 3 文档化为已知限制 (Lixinger 不提供矿权进度数据) |
| 治理瑕疵逆向 (invest2 §十) | 0% | Batch 3 文档化为已知限制 (Lixinger 不提供减持公告) |
| 60% 分红承诺 (invest2 §八) | 0% | Batch 3 文档化为已知限制 (Lixinger 不提供分红承诺数据) |
| 数人头/数店面 (invest1 §一) | 30% | Batch 3 文档化:仅作 BusinessPattern.first_principle_variable 描述字符串 |
| 个股周期拐点 (invest2 §五) | 0% | Batch 3 文档化为已知限制 (需商品价格 API) |

**整体对齐度修正**: 原审计声称 58% → 78% 是过度乐观。Batch 3 grill 复核实际 ~75% (D3 红旗激活 + audit_opinion 新增 +5 missed 文档化)。剩余的 ~25% 是 Lixinger 不支持的数据维度,文档化为已知限制,符合 CLAUDE.md "架构尽可能简化" 原则。

---

## Batch 3 验证决策 (2026-06-17 grill-me 复核)

Batch 1/2 ship 后用户再次 grill-me,对照实际代码核对 11 项决策的真实状态,产出 5 项新决策:

1. **D3 Lixinger field keys 立即 spike**: 写 `spikes/probe_redflag_metrics.py` 调真实 API 验证 bs.ar.t / m.i_tor.t / ps.np_wd_s_r.t / auditOpinionType 4 候选。**结果**: bs.ar.t (4/4 股票有数据) + m.i_tor.t (4/4) + auditOpinionType (4/4 = unqualified_opinion) 全部生效; ps.np_wd_s_r.t + bs.inv.t 确认 400 ValidationError 不支持。spike artifact: `backend/spikes/output/probe_redflag_metrics_2026-06-17T08-27-18Z.json`。

2. **D3+D6 invalidation 架构接受现状**: audit 原始决策说红旗 + 中游过滤走 `plan.invalidation:[]` schema,实际实施在 plan_runner 代码路径 (red_flag_count 检查 + `_should_filter_as_midstream_non_leader`)。决策: 不重构,改审计 spec 文字对齐代码 (invalidation 字段保留但不启用)。理由: 代码已 ship + 测试覆盖,重构 1-1.5 天且无功能增量。

3. **5 missed 概念全部文档化为已知限制**: 进度条战法 / 治理瑕疵 / 60% 分红承诺 / 数人头量化 / 个股周期拐点。除"个股周期拐点"可能复用 PriceKline 推导外,其他 4 个需要新数据源 (公告/商品价格/业务运营)。按 CLAUDE.md "架构尽可能简化" 原则不扩数据源。

4. **invest2 §23 4 块分类不引入 Plan.cyclicality**: 4 块 (顺周期/逆周期/困境反转/金融) 与现有 4 theme_id (能源/资源/金融/粮食安全) 维度正交但不冲突。文档化 `theme_id` 已足够,避免引入新字段 + alembic migration。

5. **3 阶段执行顺序**: Phase 1 spike → Phase 2 接入 (条件性) → Phase 3 4 份文档同步 + 测试。Batch 3 commit。

---

## Batch 4 grill 复核 (2026-06-17 二次 grill-me)

> 用户在 Batch 3 ship 后再次 /grill-me,要求**综合 (复核 + 漏检 + 下一批)**。本节是二次 grill 产物。

### B4-0 复核 15 项 ✓ 声明 (系统性全检)

逐项核对 `已良好对齐 ✓` 表 15 项,代码 spot-check:

| # | 审计声明 | 代码实测 | 判定 |
|---|---|---|---|
| 1 | 第一性原理 + 19 业务模式 | `business_pattern.py:51` first_principle_variable + `builtin_seeder.py:151` BUILTIN_BUSINESS_PATTERNS 19 个 | ✓ 真实 |
| 2 | invest3 天阶 7 → RESOURCE_LEADERS 7 | 4 重叠 (BFNY/NSLY/BTGF/CHGF); 3 天阶不在 LEADERS (DSL/HXYH/菜百); 3 LEADERS 不在天阶 (紫金/山东/中金) | **口径松散** (B4-5 修文档) |
| 3 | 银行 3 维 (股息+地域+OCF) | `bank_analyzer_service.py:30-32` dividend_yield + hq_region + region_score + ocf_ni_verdict | ✓ 真实 |
| 4 | 现金流为王 | `builtin_seeder.py:104` cashflow_asset ocf_to_ni≥1.0 | ✓ 真实 |
| 5 | 估值锚 ≤30% | `builtin_seeder.py:33` undervalued_entry pe_pct_10y≤30% | ✓ 真实 |
| 6 | 股息率 5% 兜底 | `builtin_seeder.py:79` bank_select dyr≥5% + `:421` core_value plan | ✓ 真实 |
| 7 | 周期评估 5 档 | `cycle_assessment_service.py:30-43` extreme_low→extreme_high + position advice | ✓ 真实 (D5 才补 extreme_high blocker) |
| 8 | 仓位纪律 3-4 / 10-50% / 15% | `position_advisor_service.py:25-28` TARGET_HOLDINGS_RANGE=(3,4) + MAX/MIN_SINGLE + MAX_INDUSTRY_WEIGHT=0.15 | ✓ 真实 |
| 9 | 加权 DYR 4-5% | `holding_service.py:299,411` target_weighted_dyr=0.045 + 低 warning | ✓ 真实 |
| 10 | 论点证伪 | `thesis_monitor_service.py:142,243-261` 双源 + breach_when 机械字段 | ✓ 真实 |
| 11 | DisciplineChecklistModal | 3 处使用 (DraftsPage / CockpitPage / ResearchThemeDetailPage) | ✓ 真实 |
| 12 | 平方差魔咒 | `backtest_metrics.py:59,79` compute_sharpe + compute_max_drawdown + `portfolio_risk_service.py:45-48` 实时指标 | ✓ 真实 |
| 13 | 业务模式 19 + theme_id | `builtin_seeder.py:151` 19 patterns + theme_name 解析 | ✓ 真实 |
| 14 | 4 主线 themes | `alembic/versions/m3h4i5j6k7l8_add_themes_table.py:67-86` 4 themes seed | ✓ 真实 |
| 15 | Lixinger 唯一数据源 | `pipelines/{universe,valuation,financial,dividend,kline}_pipeline` 5 个 | ✓ 真实 |

**结论**: 14/15 真实, 1 项 (#2) 口径松散 — invest3 天阶 7 标的与 BUILTIN_RESOURCE_LEADERS 7 只**不是同一集合**,仅 4 重叠。审计表口径误导。

### B4-1 漏检维度 (4 项决策)

二次 grill 发现原审计表完全没出现过的 invest1/2/3 概念,共 5 个潜在漏检,4 个确认要补 (E 默认 P3 doc):

#### A+B 合并: invest3 天阶 + 玄阶 标记 (Stock.tier 枚举)

**问题**:
- A: invest3 玄阶 (GGGF/YTKG/九华旅游) + invest2 §13 "邪修可小仓位玩预期差" — 当前 0 字段 / 0 策略 / 0 标记
- B: invest3 天阶 7 标的 (BFNY/NSLY/BTGF/DSL/HXYH/菜百/CHGF) 中 3 只 (DSL/HXYH/菜百) 不在任何 BUILTIN_*_LEADERS

**决策** (单字段方案,与 A 共享 schema):
- `Stock.tier: Literal['heaven','mystic',None]` (一字段表达天阶/玄阶/未分类)
- `is_speculative` 派生自 `tier == 'mystic'` (不另设 bool)
- seed 10 stocks: 7 天阶 + 3 玄阶
- 4 页面 UI badge (CandidatesPage 表格 / StockDetailPage 顶部 / DraftsPage 草稿 / CockpitPage 持仓区)
- **玄阶不进 plan**: invest2 §13 "可小仓位玩" 是人决策,系统只标记。理由: (a) 仓位控制是用户 territory (b) 玄阶本质"瑕疵股",系统不应自动 promote (c) 符合 CLAUDE.md "架构尽可能简化"

**实施影响**:
- alembic migration 加 tier 列 (nullable, 默认 None)
- `stock.py` model + schema + lixinger 解析不动
- `builtin_seeder.py` 加 BUILTIN_HEAVEN_TIER_CODES + BUILTIN_MYSTIC_TIER_CODES (10 codes)
- 前端 4 页面 tier badge 组件

#### C: invest2 "事后一刀两断" 止损 → 取消 (误读)

**问题**: 原 grill 候选 C 建议加 `trade_rule.stop_loss_pct` 机械止损。

**重新阅读 invest1/2 原文结论**: **C 是误读**。
- invest2 闭环交易预案标题"事后一刀两断"但正文无机械止损规则
- invest1 §13 §3 "拒绝回本强迫症" = 不摊平 (加仓纪律,不是止损)
- invest2 §13 "接受卖飞,拒绝深套" = 心理建设,非机械规则
- 作者哲学: **真正的止损 = 论点证伪** (thesis breach),不是机械百分比
- 当前 `thesis_monitor` 已实现论点证伪,`DisciplineChecklistModal` 已实现心法闸门

**决策**: C 取消,不加 stop_loss_pct 字段。

#### D: invest2 §4 反杠杆 (UI 加闸)

**问题**: invest2 §4 "本金观" 明确"不能借来的钱 / 不能有刚性成本 / 不能加杠杆"。当前 0 杠杆检测。但系统不接券商 API,无法机械识别。

**决策**: DisciplineChecklistModal 在 execute Draft 时加一条 "**本仓是否使用自有资金 (非融资融券/信用卡/亲友借款)?**" 用户手动勾选。
- 与 invest2 §4 "坚守能力圈 + 心法" 一致
- 不拓 cash_balance schema (拒绝过度工程)
- 系统不阻塞,只提醒

### B4-2 5 项"已知限制"复核

二次 grill 重新审视 Batch 3 文档化的 5 项"已知限制":

| # | 已知限制 | 二次复核结论 |
|---|---|---|
| 1 | 进度条战法 (矿权进度) | **已半自动** — `thesis_variables_json` 支持 `source="manual"` 任意变量,仅缺 BusinessPattern 模板条目 |
| 2 | 治理瑕疵 (减持公告) | 真·限制 — Lixinger 不提供公告数据,doc 维持 |
| 3 | 60% 分红承诺 | **需新字段** — `FinancialStatement.dividend_payout_ratio` 是 actual per-period,与 commitment (forward 承诺) 不同概念 |
| 4 | 数人头/数店面 | **已部分实现** — `first_principle_variable` 字符串描述已覆盖 (如 "加盟店增速"),定量靠 manual thesis variable |
| 5 | 个股周期拐点 | **已半自动** — 同 #1,`thesis_variables` 可输入商品价格,仅缺模板 |

### B4-3 Batch 4 ship 范围 (一个 commit, ~2 天)

| 编号 | 任务 | 涉及 | 估时 |
|---|---|---|---|
| **Spike** | `spikes/probe_stock_codes.py` Lixinger 验证 6 待验代码 (DSL/HXYH/菜百/GGGF/YTKG/九华) + artifact JSON | spike 脚本 + output | 0.3 天 |
| **N1** | Stock.tier 字段 + alembic migration + seed 10 stocks + 4 页面 badge | `stock.py` + `stock.py schema` + alembic + `builtin_seeder.py` + 前端 4 组件 | 1 天 |
| **N2** | DisciplineChecklistModal 加自有资金闸门 | `DisciplineChecklistModal.tsx` | 0.2 天 |
| **N3** | BusinessPattern.thesis_variables 模板 aggressive 拓 (3-4 个/pattern) | `builtin_seeder.py` BUILTIN_BUSINESS_PATTERNS (~21-28 变量) | 0.5 天 |
| **N4** | Stock.dividend_payout_commitment_pct + 新策略 `dividend_commitment_leader` (commitment ≥ 60%) + UI filter + plan 接入 (core_value 可选 condition) | `stock.py` + alembic + `builtin_seeder.py` + `strategy_engine.py` resolve + 前端 filter | 0.7 天 |
| **N5** | audit #2 口径修正 + STATUS.md/MEMORY.md/audit spec 同步 | 多文档 | 0.3 天 |

**验收**:
- 跑现有 1126 测试 + 新增 tier/commitment 测试 ~30 个
- spike artifact: `backend/spikes/output/probe_stock_codes_<ts>.json`
- tier badge 在 4 页面渲染正确 (3 状态: heaven/mystic/None)
- DisciplineChecklistModal 新闸门在 buy Draft 时显示
- 7 资源 BusinessPattern 各加 3-4 个 thesis 变量 (覆盖进度+现价+价差+产能)
- `dividend_commitment_leader` 策略 + 1 plan 接入 (`core_value` 加 optional condition)
- 文档同步: STATUS.md / MEMORY.md / 本 audit spec

### B4-4 投资体系对齐度评估 (Batch 4 实际)

| invest 维度 | Batch 3 后 | Batch 4 实际 | 说明 |
|---|---|---|---|
| invest1 第一性原理 | 80% | 85% | N3 拓 thesis 变量 |
| invest1 选择权理论 | 85% | 85% | 无变化 |
| invest1 现金流为王 | 95% | 95% | 无变化 |
| invest1 银行盲盒 | 95% | 95% | 无变化 |
| invest1 估值锚 | 95% | 95% | 无变化 |
| invest1 仓位管理 | 100% | 100% | 无变化 |
| invest1 30% 止盈 | 75% | 75% | 无变化 |
| invest2 §4 本金观 (反杠杆) | 10% | 70% | N2 心法加医 |
| invest2 §8 闭环交易预案 (事后一刀两断) | 75% | 75% | C 取消 (误读) |
| invest2 §10 财报避坑 | 85% | 85% | 无变化 |
| invest2 §13 三类禁投 | 80% | 80% | 无变化 |
| invest2 §7 平方差魔咒 | 85% | 85% | 无变化 |
| invest2 §23 资产配置 | 60% | 60% | 无变化 |
| invest2 §24 100 万门槛 | 10% | 10% | 无变化 |
| invest1 §3 EPS 真相 | 10% | 10% | 无变化 |
| **invest3 天阶/玄阶分类** | **0%** | **80%** | **N1 tier 字段激活** |
| **invest3 §八 分红承诺** | **0%** | **80%** | **N4 dividend_commitment_leader** |
| **invest3 §九 进度条战法** | **0% (doc)** | **60% (manual)** | **N3 thesis 变量激活** |
| **invest3 §五 个股周期拐点** | **0% (doc)** | **60% (manual)** | **N3 thesis 变量激活** |
| 数人头/数店面 | 30% | 35% | N3 间接加分 |
| 治理瑕疵逆向 | 0% (doc) | 0% (doc) | 维持 (真·限制) |

**整体对齐度修正**: Batch 3 后 ~75% → **Batch 4 预期 ~80-82%**。剩余的 ~18% 是真·限制 (Lixinger 不提供公告/公告/商品历史价格 series)。

---

## Batch 4 实际产出 (2026-06-17 ship)

二次 grill 决策落地实际状态:

| 任务 | 计划 | 实际 | 偏差 |
|---|---|---|---|
| Spike 验证 6 股票代码 | Lixinger /company 查询 6 待验 + 4 controls | 全部 10/10 通过,artifact `probe_stock_codes_2026-06-17T12-11-27Z.json` | YTKG 锁定云天化 (600096) ✓ |
| N1 tier 字段 | 新字段 `Stock.tier: Literal['heaven','mystic',None]` + alembic + seed 10 + 4 页面 badge | **简化**: `Stock.tier` 字段已存在,只更新 docstring. 用 `core`/`watch` 复用替代 `heaven`/`mystic` (用户 2026-06-17 指示 "保留核心、关注,替代天阶玄阶") | 0 alembic migration, 0 frontend 改动, 6 新 tests |
| N2 DisciplineChecklist | 加自有资金闸门 | **简化**: `no_borrow` checkbox 已存在,只更新 label 对齐 invest2 §4 措辞 ("本仓使用自有资金 (非融资融券 / 信用卡 / 亲友借款) — invest2 §4") | 1 行 label 改动 |
| N3 thesis 变量 | 21-28 新变量 (3-4 个/pattern) | 20 新变量 (10 patterns × 2 vars: 进度 + 商品现价),实际覆盖资源/能源相关 10 个 BusinessPattern | 范围 21-28 → 20,符合"aggressive"标准 |
| N4 commitment | Stock.dividend_payout_commitment_pct + 策略 + plan + UI filter | alembic `s8_1` + model + schema + strategy_engine resolve + 新策略 `dividend_commitment_leader` + 新 plan `pure_cash_machine` + seed BTGF 0.60 + CandidateResponse expose 字段 | **filter UI 未实施** (字段已 expose,filter widget 推到 P3) |
| N5 文档同步 | audit #2 口径修正 + STATUS.md/MEMORY.md/audit spec 同步 | STATUS.md 测试数 1126→1141,Alembic head s7_1→s8_1;本 spec 加 Batch 4 实际产出节 | 完成 |

**Batch 4 实际测试数**: 1141 passed (+15 new tests for tier/commitment/thesis 变量结构)

**alembic head**: `s8_1_dividend_payout_commitment`

**对齐度评估 (Batch 4 实际)**: 75% → ~80% (符合 B4-4 预期, N4 UI filter 推到 P3 略减 1-2%)

### Batch 4 用户决策变更 (2026-06-17 实施过程中)

1. **N1 命名简化 (用户 2026-06-17 指示)**: 原决策 `heaven`/`mystic` 改为复用 `core`/`watch`. 理由: 避免冗余 tier 值,与现有 UI tier maps 兼容. invest3 修仙映射保留在 model docstring (`core≈天阶, watch≈玄阶`)
2. **N4 UI filter 范围调整**: 完整 filter widget 推到 P3 (字段已 expose 到 CandidateResponse + GroupedCandidate),用户可手动用 API 查询,等高优先级工作完成后补 UI

---

## Batch 5 (2026-06-17 invest-alignment 3rd grill) — 漏检深挖

> 用户在 Batch 4 ship 后第 5 次跑同一 prompt "梳理 docs/reference/* 内容,审计是否对照实现"。前 4 批覆盖 invest3 五层 + 核心十诫部分 + invest2 §1-13。本轮聚焦"4 批都没碰过的漏检维度"。

### 漏检清单 (7 项识别)

| # | 漏检项 | 来源 | Batch 1-4 状态 |
|---|---|---|---|
| M1 | "人之道" 加减仓纪律 (加仓盈利/砍亏损/补仓拉开梯度) | invest1 第13章 + invest2 §3 + invest3 第三层 | **0 实现** |
| M2 | 能力圈边界 (Stock 字段表达"在我的能力圈内") | invest3 第四层 + 核心十诫 #9 | **0 实现** |
| M3 | "破除三大妄念" 心法闸门 (损失厌恶/从众/锚定) | invest1 第12章 + invest2 §2 | 仅自有资金闸门 |
| M4 | "渣男理论" 组合换股机制 (不谈恋爱只谈逻辑) | invest1 第13章 + invest2 §3 | thesis_monitor 部分对应 |
| M5 | 投机与投资界限 (玄阶/satellite 仓位上限) | invest1 第9章 + invest2 §1.3 + invest3 第四层 | **0 实现** |
| M6 | "煤油比价" 行业第一性原理公式化 | invest1 第5章 | 字符串描述 |
| M7 | 避坑指南的"伪逻辑识破" | invest1 附录 | 元层面 |

### Batch 5 决策清单 (8 项: 6 实质 + 1 命名重构 + 1 ship 计划)

#### Q2: tier 命名重构 (专业金融名词)

Batch 4 用 `core/watch`,但 `watch` 是"自选股"语义,与 invest2 §13/invest3 玄阶"卫星/投机小仓位"语义不匹配。

**决策**: 改用 Core-Satellite Model 行业标准术语:
- `core` = 核心仓位 (≈ invest3 天阶,高确定性核心持仓)
- `satellite` = 卫星仓位 (≈ invest3 玄阶,可小仓位玩预期差)

`focus` / `None` 不变。alembic s9_1 UPDATE 已 seed 的 3 元组 (`watch` → `satellite`)。

#### M1: "人之道" 加减仓纪律 + psychology_alerts

invest1 第13章 + invest3 第三层 反复强调:
- 反直觉加减仓: 加仓盈利股,砍掉亏损股 (违反"补亏损"天道)
- 补仓纪律: 跌幅未到 10% 不考虑补仓,拒绝"回本强迫症"

**决策**:
- DisciplineChecklistModal 加 3 条心法闸门 (a/b/c)
- cockpit_service.psychology_alerts 字段: 持仓现价 < cost × 0.9 且最近 30 天有 BUY trade → "回本强迫症嫌疑"

#### M2: 能力圈边界 (Stock.in_circle)

invest3 第四层 + 核心十诫 #9 "坚守边界: 不懂不做"。

**决策**:
- 新增 `Stock.in_circle: bool` (默认 False)
- UI toggle (UniversePage / StockDetailPage)
- plan_runner filter stage 过滤 (`_filter_out_of_circle`)
- `Plan.disable_in_circle_filter` 逃生口 (默认 False)
- CandidatesPage filter "仅能力圈内"

#### M3: "破除三大妄念" 心法扩到 5 条 + extreme_low banner

invest1 第12章三大妄念: 损失厌恶 / 从众 / 锚定。

**决策**:
- DisciplineChecklist 从 M1 的 3 条扩到 5 条 (加 d 反损失厌恶 / e 反锚定)
- cockpit_service.cycle_banner 字段: extreme_low → "建议布局" / extreme_high → "建议空仓" 非阻塞 banner

#### M4: thesis breach 自动 SELL draft (渣男理论)

invest1 "论点没了就换,不恋战" 是 CLAUDE.md 三原则 1 (全自动化) 的核心承诺。

**决策**:
- thesis breach → EventBus → `draft_service.create_thesis_breach_sell_draft`
- 自动生成 SELL draft (plan_id=NULL, step_kind='thesis_breach', source='system')
- 同时 supersede 该 stock 的所有 pending BUY drafts
- 半自动平衡点: 自动 draft,不自动 execute (用户仍是最后闸门)

#### M5: tier-aware 仓位上限 (Core-Satellite 单只+总仓位)

invest2 §1.3 "可小仓位玩" 是硬约束,但 position_advisor MAX_SINGLE_POSITION=0.5 一视同仁。

**决策**:
- `MAX_SINGLE_BY_TIER = {'core':0.5, 'satellite':0.1, 'focus':0.5, None:0.5}`
- `TOTAL_SATELLITE_MAX = 0.20` (组合总卫星仓位上限)
- `check_before_draft` 加 satellite 分支 (blocker / warning)
- `_compute_suggested_buy_quantity` 加 tier-aware clamp

#### M6+M7: 跳过 + 文档化

- M6 (行业公式化): Lixinger 不提供商品价格 series,Batch 4 N3 thesis_variables 已部分覆盖
- M7 (避坑指南伪逻辑): 元层面心法,无机械规则,D3 + D6 部分覆盖

#### Q9: ship 计划

单 Batch 5 一个 commit,7 步实施,~3-4 天。

### Batch 5 实际产出 (2026-06-17 ship)

| 任务 | 计划 | 实际 |
|---|---|---|
| Q2 tier rename | alembic UPDATE + model docstring + 4 处 frontend | ✓ alembic s9_1 + model + builtin_seeder + 4 frontend (CandidatesPage/UniversePage/DisciplineChecklistModal) |
| M1 心法闸门 + psychology_alerts | DisciplineChecklist 3 条 + cockpit_service 字段 | ✓ 3 条 + cockpit_service `_compute_psychology_alerts` 回本强迫症检测 |
| M2 in_circle | Stock 字段 + UI + plan_runner filter + CandidatesPage filter | ✓ Stock.in_circle + UniversePage toggle + plan_runner `_filter_out_of_circle` + Plan.disable_in_circle_filter 逃生口 |
| M3 心法扩到 5 条 + extreme_low banner | DisciplineChecklist 加 d/e + cycle_assessment banner | ✓ 5 条 + cockpit_service.cycle_banner (extreme_low/extreme_high) |
| M4 thesis breach → sell draft | EventBus handler + draft_service 新方法 + supersede | ✓ on_thesis_alert_triggered 扩展 + `create_thesis_breach_sell_draft` + `_supersede_pending_buys_for_stock` + alembic s9_2 (plan_id nullable) |
| M5 tier-aware 仓位上限 | position_advisor 加 caps + check 分支 | ✓ `MAX_SINGLE_BY_TIER` + `TOTAL_SATELLITE_MAX` + `_current_satellite_weight` + `_compute_suggested_buy_quantity` clamp |
| M6+M7 文档化 | STATUS.md 已知限制 | ✓ |
| 测试 | +9 新测试 | ✓ +14 (M2 filter 4 + M4 thesis breach 6 + M5 tier-aware 4) |
| alembic head | s9_2 | ✓ |

### Batch 5 对齐度评估

| invest 维度 | Batch 4 后 | Batch 5 实际 |
|---|---|---|
| invest1 第一性原理 | 85% | 88% (M2 能力圈) |
| invest1 仓位管理 | 100% | 100% (M5 补) |
| invest1 §三 心法 (三大妄念) | 50% | 80% (M3) |
| invest1 §三 仓位管理"人之道" | 30% | 80% (M1) |
| invest2 §5 极低布局提示 | 0% | 80% (M3 extreme_low banner) |
| invest2 §13 邪修投机小仓位 | 0% | 90% (M5) |
| invest1 第13章 渣男理论 | 50% | 90% (M4) |
| invest3 核心十诫 #9 坚守边界 | 0% | 90% (M2) |

**整体对齐度修正**: Batch 4 后 ~80% → **Batch 5 后 ~86-88%**。剩余的 ~12% 是真·限制 (Lixinger 不提供公告/商品价格 series) + 元层面心法 (M7)。

---

## 参考

- 项目快照: `docs/progress/STATUS.md`
- 路线图: `docs/active/roadmap.md`
- 投资体系原文: `docs/reference/invest{1,2,3}.md` + `docs/reference/investment-theory-source.md`
- 上次审计: `docs/reference/specs/2026-06-14-comprehensive-audit.md`
- CLAUDE.md 三原则: 除真实券商下单外全自动化 / 架构尽可能简化 / 交易系统对齐 invest{1,2,3}.md
