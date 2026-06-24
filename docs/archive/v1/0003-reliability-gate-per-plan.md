# ADR-0003: 可靠性闸门(per-plan 5 条件同时满足才翻 auto)

2026-06-24 决定:每个 plan 翻 `auto_execute_enabled = true` 前,必须**同时**满足 5 个条件。5 条件是「最小理性信任基线」,缺一不可。

## Context

决策 3 要求 Phase 2 才翻 auto,但「什么时候可以翻」不定义,就永远卡在 manual。直觉答案「跑 8 周看看」太模糊——8 周里如果大盘顺风,paper 不爆雷不代表策略有效;如果 worker 间歇挂掉,40 run 攒不齐也不代表系统不可靠。必须把闸门钉死成可观测、可验证的条件。

5 条件覆盖三个维度:**时间**(8 周足够覆盖各种市场环境)、**volume**(40 run 足够产出统计意义的 drafts)、**质量**(零事故 + 不爆雷 + 你签字)。前 4 条是客观可查的,第 5 条「你签字」是主观的——因为信任最终是个人判断,系统只能提供数据,不能替你决定。

per-plan(不是全局)的依据见 ADR-0002。

## 5 Conditions

1. **时间**: 连续 ≥ 8 周 elapsed(不要求 uptime,见决策 12 松解)
2. **volume**: ≥ 40 个 plan run(工作日 daily,8 周 ≈ 40 个工作日)
3. **零事故**: 6 类事故(决策 10)零触发——plan_runner 拒跑 / 三层防护连触 / thesis breach / pipeline 大面积失败 / 单日 DD≥5% / worker 崩溃
4. **paper 不爆雷**: 期间 paper portfolio 不出现离谱亏损(单 plan 亏 30%+ 算爆雷,需复盘策略是否本身是垃圾)
5. **你签字**: 月度 review 时看着记录,手动翻开关

## Considered Options

- **全局 binary(所有 plan 一起过闸门)**:被拒。6 plan 风险特征不同,一刀切要么过松(contrarian 没准备好就翻)要么过紧(core_value 准备好了还被拖)
- **准确率驱动(paper P&L / 命中率超阈值)**:被拒。paper 表现受大盘影响大,牛市垃圾策略也赚钱,熊市好策略也亏——不是系统可靠性的直接指标
- **纯主观签字(不预设指标)**:被拒。没有客观支撑,「感觉差不多了」容易过早翻 auto

## Consequences

- `backtest_engine` 是前置依赖(决策 9):plan 进 paper 之前必须先 backtest 通过(夏普 > 0 + drawdown < 25%),否则拿垃圾策略 paper 8 周是浪费时间——backtest 失败的策略根本不进 paper
- `plan_runs` 表(或 audit_log)必须可靠记录每个 plan 的 run 历史,用于条件 1/2 验证
- 事故检测(决策 10)必须就位,用于条件 3 验证
- paper P&L 追踪必须就位(已有 `holdings` + `trades` 表,够用),用于条件 4 验证
- Cockpit 新增「plan 可靠性进度卡」:每 plan 显示「8 周进度条 / 40 run 计数 / 事故计数 / paper DD / 是否 backtest 通过」——条件 5 签字的数据支撑
- 翻 auto 后可单 plan 回滚(`auto_execute_enabled = false` 回去),不必「全或无」

## 关联

- 决策来源:`docs/active/redesign-decisions.md` 决策 5
- 分阶段执行:ADR-0002
- 验证机制(前置 backtest):决策 9
- 事故定义:决策 10
- Q5/Q11 冲突松解:决策 12
