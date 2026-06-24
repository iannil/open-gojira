# ADR-0002: 分阶段执行模型(Phase 1 manual → Phase 2 auto,per-plan toggle)

2026-06-24 决定:Gojira 的交易执行链路分两阶段。Phase 1(当前)BUY/SELL 都 manual execute,`DisciplineChecklistModal` 5 条心法强制勾选保留。Phase 2(未来)BUY/SELL 都 auto-execute,modal 砍掉。**迁移单位是 per-plan,不是全局**——每个 plan 独立评估、独立翻 `Plan.auto_execute_enabled` 开关。

## Context

主痛点是「时间」(决策 2),直觉答案是把 `DisciplineChecklistModal` 砍掉、改 auto-execute。但 grill-me 第 5 题澄清:「**在手动确认可靠性之前,BUY/SELL 都手动**」。这意味着系统当前还没赚够信任,不能立刻 auto。所以采用分阶段:Phase 1 用 manual 攒信任(8 周 reliability gate,决策 5),Phase 2 翻 auto。

per-plan 而非全局,因为 6 plan 风险特征不同(`core_value` 防御 vs `contrarian` 高波动),不能用同一可靠性标准;且一个 plan 的 bug 不应污染其他 plan 的自动执行;分阶段让信任**逐步**建立(先信 core_value 跑 2 个月没事,再开 bank_anchor)。

## Considered Options

- **全局 binary 开关(一次性翻)**:被拒。一次大盘崩盘 + 一个 thesis_monitor 误判 = 全仓连环 auto-BUY 抄底,违反 invest3 §5
- **永远 manual**:被拒。违反决策 2「时间优先」——autopilot 名不副实
- **BUY auto / SELL manual**:被拒。SELL 是更大时间杀手(决定何时卖比何时买累),保留 SELL manual = 半自动,与决策 2 不一致
- **per-tier 开关(core auto / satellite manual)**:被拒。颗粒度太粗,同 tier 内 plan 风险仍不同(`bank_anchor` vs `core_value` 都是 core 但波动差很大)

## Consequences

- 新增字段:`Plan.auto_execute_enabled: bool`,默认全部 false(Phase 1)+ alembic migration
- 代码路径同时支持 manual / auto 两种模式:`draft_service.execute(draft_id, force)` 保留 manual 语义;新增 `draft_service.try_auto_execute(plan_id)` 在 worker scheduler 里被调用,根据 plan 开关决定走 manual 还是 auto 路径
- **不允许**「Phase 2 大重写」:开关切换 = config 改动,代码已经两条路径都跑通
- `DisciplineChecklistModal` 在 Phase 1 保留(每个 manual execute 强制勾 5 条心法),Phase 2 砍——但何时砍由 per-plan 决定(某 plan 翻 auto 后,该 plan 的 drafts 不再走 modal)
- 事故定义(决策 10)里「thesis breach 触发」要重新审视:Phase 1 thesis breach 只生成 draft + 通知,不 auto-execute;Phase 2(该 plan 翻 auto 后)thesis breach 直接 auto-SELL

## 关联

- 决策来源:`docs/active/redesign-decisions.md` 决策 3
- 可靠性闸门:ADR-0003
- 事故定义:决策 10
