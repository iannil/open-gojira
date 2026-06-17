# invest1/2/3 对齐审计 Batch 1 (低风险高价值)

> **完成日期**: 2026-06-17
> **开始日期**: 2026-06-17
> **作者/执行人**: Claude Code (grill-me + 实施)
> **关联规格**: `docs/reference/specs/2026-06-17-invest-system-alignment-audit.md`

## 目标 (Goal)

对照 `docs/reference/invest{1,2,3}.md` 投资体系审计 Gojira 项目对齐度,识别并修复"基础设施已建,策略层未接"的断层。Batch 1 聚焦低风险高价值项 (不动 schema,无 alembic migration),Batch 2 (拓 schema) 留待下一轮。

## 最终状态 (Final State)

Batch 1 完成 6 项决策 (D1 / D5 / D6 / D7-D10 文档化 / 求字→选择权 命名重构),新增 1 个内置策略 (`avoid_overvalued_tech`),修复 1 个潜伏 bug (`bank_select.industry_in` 永不匹配 Lixinger 实际返回的 `"银行"`),1084 测试通过 (+9 新增,无回归)。

实测发现的核心修复:
1. **D1 顺带修 bug**: `bank_select` 用 `["bank"]` 但 Lixinger 实际返回 `"银行"`,导致 bank_select 永不匹配。改为 `["银行", "bank"]` 兼容两种来源。
2. **D5 升级硬纪律**: `extreme_high` 新开仓由 warning → blocker,严格对齐 invest2 §5"极高高位尽量空仓"。保留"加仓赢家"通道 (invest1 §二"去弱留强")。
3. **D6-A 标记策略**: 新增 `avoid_overvalued_tech` 策略 (PE 分位≥90% 或 DYR<2%),用于 /strategies/test 单股检测 (plan DSL 是正向逻辑,不支持 NOT)。
4. **D6-B 已就绪**: 中游非 cost_leader 排除已由 `plan_runner._should_filter_as_midstream_non_leader` 实现,4 个内置 plan 默认 `disable_midstream_filter=False` 即 filter 启用。BFNY/NSLY 等成本龙头不受影响。
5. **命名重构**: `BusinessPattern.power_tier_baseline` 字段名保留 (内部 ID),但 UI/文档统一改"选择权理论 / 选择权位阶"文案。映射: 0 求 → 0 层选择权 (被选择); 3 求 → 3 层选择权 (垄断)。

## 关键修改 (Key Changes)

### 后端

- `backend/app/services/builtin_seeder.py`:
  - `bank_select` rule_json 加第 3 个 condition `{field: bank_blind_box, op: ==, value: 可见}` 严格对齐 invest2 §11 银行盲盒三维
  - `bank_select` + `bank_anchor.scan_scope` 的 industry 从 `["bank"]` → `["银行", "bank"]` 修复 Lixinger 实际返回值不匹配 bug
  - 新增第 7 个内置策略 `avoid_overvalued_tech` (logic: OR, conditions: PE分位≥0.90 / DYR<0.02)
  - BUILTIN_PLANS 上方加 D7 止盈规则说明 + D6-B 中游 filter 说明注释
- `backend/app/services/position_advisor_service.py:198-215`:
  - `cycle_position == "extreme_high"` + `not already_held` → blocker (原 warning)
  - `cycle_position == "extreme_high"` + `already_held` → warning ("加仓赢家通道")
  - `high` 仍 warning,留给用户判断
- `backend/app/models/business_pattern.py`:
  - model docstring "求字理论 (话语权 0-3)" → "选择权理论 (选择权位阶 0-3, 谁决定选择谁)"
  - `power_tier_baseline` 字段 docstring 重写,0/1/2/3 四档语义用"层选择权"措辞
  - 添加注释: 字段名内部保留,UI/文档用"选择权"文案

### 前端

- `frontend/src/features/stock-detail/StockDetailPage.tsx:203`: "求评分" → "选择权评分"
- `frontend/src/features/business-patterns/BusinessPatternsPage.tsx`:
  - purpose 字符串 "话语权位阶" → "选择权位阶"
  - TIER_LABELS 4 档: "0 求(地狱)" → "0 层选择权(被选择)" / "3 求(顶级)" → "3 层选择权(垄断)" 等
- `frontend/src/features/stock-detail/components/IndustryContextPanel.tsx`:
  - TIER_LABEL 4 档同步改"层选择权"措辞

### 数据库

无 alembic migration。所有改动通过 `seed_strategies` / `seed_plans` 的 idempotent upsert 机制在下次启动时自动应用。

### 文档

- `docs/reference/specs/2026-06-17-invest-system-alignment-audit.md` (新建): 11 项决策 + 两批 ship 计划
- `docs/progress/STATUS.md`: 加 "已知限制 (D8/D9/D10)" 小节
- `~/.claude/projects/-Users-rong-zhu-Code-gojira/memory/feedback-qiu-to-optionality-naming.md` (新建): 命名重构偏好
- `~/.claude/projects/-Users-rong-zhu-Code-gojira/memory/project-invest-alignment-audit-2026-06-17.md` (新建): 审计状态快照
- `MEMORY.md`: 加 2 个索引项

### 测试

- `backend/tests/test_builtin_seeder_dyr_fwd.py` 加 3 个测试类:
  - `TestBankSelectUsesBlindBoxVerdict` (3 tests): 验证 D1
  - `TestAvoidOvervaluedTechStrategy` (3 tests): 验证 D6-A
  - `TestMidstreamFilterIsActive` (1 test): 验证 D6-B
- `backend/tests/test_position_advisor.py` 加 2 个测试:
  - `test_buy_blocked_in_extreme_high_new_stock`: extreme_high + new stock → blocker
  - `test_buy_allowed_in_extreme_high_already_held`: extreme_high + already_held → 允许 + warning

## 测试结果 (Test Results)

```
pytest: 1084 passed, 0 failed (baseline 1075 + 9 new)
npx tsc --noEmit: ✓ (前端类型检查 clean)
```

新增 9 测试明细:
- D1 验证 × 3 (bank_select has blind_box / industry 中文化 / bank_anchor scan_scope 中文化)
- D5 验证 × 2 (extreme_high 新仓 blocked / 加仓赢家 allowed)
- D6-A 验证 × 3 (avoid_overvalued_tech exists / uses OR / has correct conditions)
- D6-B 验证 × 1 (4 个内置 plan 默认 filter 启用)

## 验收检查 (Acceptance Checklist)

- [x] 功能验收: bank_select 现在要求 blind_box=可见; extreme_high 新仓 blocker; avoid_overvalued_tech 策略可查
- [x] 回归测试: 1084 测试通过 (1075 baseline + 9 新增,无回归)
- [x] 文档更新: spec + STATUS.md + 2 memory + 命名重构注释全到位
- [x] 性能验收: 无性能敏感路径变更 (策略规则评估为常数时间)
- [x] Bug 修复: bank_select.industry_in 永不匹配 Lixinger 实际返回值的潜伏 bug 已修

## 遗留问题 (Known Issues)

Batch 2 (待下一轮 grill + ship):
- **D2 optionality_leader 策略**: 新增 `power_tier >= 2 AND dyr_fwd >= 0.04` 策略激活选择权位阶字段。0.5 天。
- **D3 财报红旗完整版**: 拓 `FinancialStatement` schema 加 `accounts_receivable` / `inventory` / `non_recurring_profit` / `audit_opinion` 字段 + Lixinger endpoint 调研 + 6-8 红旗检测器 + plan invalidation 接入。2-3 天。
- **D4 portfolio_risk_service**: 新增 service 从 `historical_klines` 推算组合波动率 / 30 日最大回撤 / sharpe proxy,Cockpit 加"组合风险"卡片。1-1.5 天。

其他已知限制 (D8/D9/D10 文档化,不实施):
- D8 房产/黄金实物/货币基金不在 Gojira 范围
- D9 100 万门槛跳过机械实现
- D10 EPS 真相 (永续债/优先股剔除) Lixinger 不支持

## 参考 (References)

- 设计文档: `docs/reference/specs/2026-06-17-invest-system-alignment-audit.md`
- 上次 ship: `docs/reports/completed/plan-thesis-monitor-v2-2026-06-17.md`
- 投资体系原文: `docs/reference/invest{1,2,3}.md`
