# ADR-0005: 无组合级熔断(Phase 1,Phase 2 复审)

2026-06-24 决定:Phase 1 **不实现**任何组合级风险熔断(drawdown breaker / cash floor / monthly loss limit / daily trade count limit)。系统性风险防线只有一条——weekly review 的人工判断。per-draft 三层防护(价格 band / cash / industry cap)+ cycle gate 保留。

## Context

per-draft 防护只防「单笔蠢操作」,不防系统性风险(大盘崩盘全仓跌 15%、策略集体失效月亏 20%、数据异常导致连环错误 draft)。理论上应该有组合级 breaker。但 grill-me 第 10 题用户明确选 A「无组合熔断」,理由:

1. Phase 1 是 manual execute,系统性风险发生时你 weekly review 能砍,不需要机器自动介入
2. 加 breaker 是给 Phase 1 增加「可能错的机器逻辑」——breaker 误触发会误拦合法操作,得不偿失
3. YAGNI:Phase 2 翻 auto 时再评估也来得及,不是不可逆决策

风险接受:Phase 2 翻 auto 后,大盘崩盘时系统可能连环 auto-BUY 抄底(违反 invest3 §5「极端 cycle 才布局」)。届时**必须**重新评估是否加 drawdown breaker。

## Considered Options

- **drawdown breaker + cash floor(推荐项)**:被拒。用户选 A,接受 Phase 1 无组合熔断的风险
- **全套 breaker(drawdown + cash floor + monthly loss + daily count)**:被拒。参数多、易互相冲突,且 weekly review 模式下 daily count limit 无意义
- **per-plan breaker(core_value drawdown 20% / contrarian 30%)**:被拒。颗粒度细但配置复杂,且 6 plan 各设阈值难以横向比较

## Consequences

### Phase 1 保留

- per-draft 三层防护:`price_band ±15%` / `cash_balance 检查` / `industry_cap 15%`
- cycle gate:`extreme_high` blocker 新开仓 / `extreme_low` 非阻塞 banner
- weekly review 作为系统性风险防线

### Phase 1 不实现

- drawdown breaker(组合级 `(peak - current) / peak ≥ X%` 触发暂停)
- cash floor(`cash / total_assets ≤ X%` 禁新 BUY)
- monthly loss limit
- daily trade count limit

### Phase 2 复审触发条件

翻任何 plan 的 `auto_execute_enabled = true` 之前,**必须**重新评估本 ADR:

- 如果 Phase 1 paper 期间未经历大盘剧烈波动(单日 DD ≥ 5%),且策略表现稳定,可继续无熔断
- 如果 Phase 1 期间经历过波动或 paper 出现过连环错误 draft,**强烈建议**先加 drawdown breaker(阈值 15-20%)再翻 auto
- 复审结论写入新的 ADR(0005 的修订版或 0005-phase2-amendment)

### 事故定义兜底

决策 10 的「单日 drawdown ≥ 5%」事故会触发桌面通知——这是 Phase 1 无组合熔断的**最低限度的预警机制**。系统不拦,但你知道。

## 关联

- 决策来源:`docs/active/redesign-decisions.md` 决策 8
- 事故定义(单日 DD≥5% 推送):决策 10
- Phase 2 复审触发:ADR-0002(分阶段执行)
