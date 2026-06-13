# 重审 production-readiness-plan: 7 项决策

> 日期：2026-06-13
> 状态：已确认 (grill-me 会话产出)
> 关联：`docs/active/production-readiness-plan.md` (原 6 阶段计划) | `docs/progress/STATUS.md` (实测数据)

## 背景

`production-readiness-plan.md` (2026-06-12) 完整执行了 S0-S5，但实测发现：

```
trades:        2 (仅 seed 数据)
holdings:      0
drafts:        0   ← 关键
backtests:     0   ← 关键
alerts:       14 (silent,仅 in_app)
candidates:  296 (生成中,但全部被闸门吞掉)
```

4 个内置预案全部 active，2026-06-13 04:18 正常运行：

```
core_value:      62 passed
resource_macro: 122 passed
bank_anchor:     11 passed
contrarian_scan:101 passed
─────────────────────────────
296 candidates → 0 drafts
```

**根因**：`plan_runner.py:494 if code not in watchlisted: return` 把所有未手动提升的候选股静默过滤，**296 个机会从未变成可执行 draft**。

用户三原则：

1. 除了真实下单券商，其余尽可能自动
2. 架构尽可能简化，易于使用
3. 交易系统来自 `docs/reference/invest{1,2,3}.md`

基于此重审原计划的 11 项决策 (Q1-Q13) + 6 阶段 (S0-S6)。

## 决策

| # | 决策 | 推理 |
|---|------|------|
| 1 | **删除 PROMOTE 闸门** | PROMOTE 是纯内部步骤，无外部依赖。它把"自动化候选股筛选"卡在"用户手动确认"上，违背原则 1。原意是"人脑介入点"，实际作用是"静默吞 296 候选"。 |
| 2 | **EXECUTE + TRADE_ENTRY 合并为单 modal** | 两个步骤都在 broker 回报后，本质是同一动作。点"执行" → modal 预填 draft 信息 → 用户填 broker 实际成交 → 存 = trade 写入 + draft 关闭。原则 2。 |
| 3 | **保留回测引擎 (S4B+C+D)** | 0 runs ever, 但回测是验证策略 (原则 3) 的唯一工具。回测引擎不是过度工程，是**未使用**。决策 #7 的前置依赖。 |
| 4 | **watchlist 去闸门语义，留股池语义** | watchlist 当前纠缠三用途：闸门 / 扫描范围 / 用户分组。闸门语义随 #1 去掉；表与 watchlist_groups 保留，仅作"手动股池"用于 `scan_scope=watchlist` 或自定义分组。 |
| 5 | **跳过 S6 (Docker / DR)** | 0 实盘使用，先跑通 dev 模式 2-4 周养成使用习惯，再容器化。原则 2：不提前优化。dev 模式失败成本 = 重新 ./dev.sh，可接受。 |
| 6 | **draft 全表现，按 Qiu 评分排序** | 原则 1 最大化：所有过交易规则的 draft 都展示。配 #7 的"人工评审"层：用户扫排序表，自选 Top N 深审。不强制 Top-N 阈值，让时间天然约束。 |
| **7B** | **双层闸门：backtest 验证 + 严格人工评审** | Gate 1 (策略层，一次性)：backtest 5-10 年 CAGR/Sharpe/MaxDD 验证。Gate 2 (draft 层，每笔)：`DisciplineChecklistModal` 10 项纪律全勾才能执行。原则 3：不验证不执行。 |

## 7 项决策的依赖图

```
#3 保留 backtest ─────► #7B backtest 验证
                              │
#1+#4 去闸门 ──────► 30-100 draft/天流入
                              │
#6 Qiu 排序展示 ────► 排序列表
                              │
                              ▼
                    DisciplineChecklistModal (10 项)
                              │
                    #2 合并 modal ─► broker → trade
```

## 与原计划的差异表

| 原计划项 | 原决策 | 现决策 | 变化 |
|---|---|---|---|
| Q1 成交回报 | 手动录入 | 手动录入 + 合并 EXECUTE | #2 |
| Q2 trades 流水 | 事件源 + 派生 | 不变 | — |
| Q3 T+1 双层强制 | plan_runner 软 + trade 硬 | 不变 | — |
| Q4 资金模型 | cash_balance + adjustments | 不变 | — |
| Q5 fee configs | 历史化 | 不变 | — |
| Q6 价格 / 涨跌停 / 停牌 | 三层校验 | 不变 | — |
| Q7 Lixinger 防御 | retry + staleness + sanity + alerts | 不变 (实测 14 alerts 正常工作) | — |
| Q8 回测 | 完整引擎 | 不变 (但 0 runs, 需先跑) | #3 |
| Q9 公司行为 | 自动同步 + 应用 | 不变 (无持仓，未触发) | — |
| Q10 盘中 / 告警 / 止损 | 多通道 + 50-80 股监控 | 不变 (但仅 in_app 通道，需补 server_chan) | — |
| Q11 Docker / DR | Docker Compose + 备份 + healthcheck | **跳过** | #5 |
| Q12 税务 | 不做 | 不做 | — |
| Q13 CSV 导入 | 不做 | 不做 | — |
| (新增) PROMOTE | 手动提升 | **删除** | #1 |
| (新增) watchlist 角色 | 闸门 + 范围 + 分组 | **仅股池** | #4 |
| (新增) draft 展示 | (未明确) | **全表现 + Qiu 排序** | #6 |
| (新增) 执行信任 | (隐式: 信任策略) | **双层闸门** | #7B |

## 实施序列 (按依赖)

```
1. 解 Lixinger token (否则一切停摆)
2. 跑首个 backtest (验证 6 策略, 你说"不信任先回测")
3. 改 plan_runner: 去 watchlist gate (line 494)  ← #1+#4
4. 改 drafts UI: 合并 execute/entry modal          ← #2
5. 改 Cockpit: draft 按 Qiu 评分排序               ← #6
6. 强制 DisciplineChecklistModal 通过才能执行      ← #7B
7. 跑通首笔实盘 trade
8. 跑通后再考虑 S6 / server_chan                  ← #5
```

## 未解的实操张力

**#6 + #7B 的张力**：30-100 draft/天 × 严格评审 (DisciplineChecklistModal 10 项) = 每天 50 分钟+。

**当前解读**：严格评审只针对"用户决定深审的 draft"，不针对"扫一眼跳过的"。用户扫排序列表 → 选 Top N → 严格评审 → 执行 / 拒绝。N 不由系统强制，由用户时间天然约束。

如实操后发现 N 过载，候选缓解：
- 加 strategy-level daily cap (每策略 N draft/天上限)
- 加预估金额阈值 (≥ X 元才进池)
- 加 AUTO 项失败即拒 (in_plan / position_ok 已自动,可扩到 read_report 检测)

## 与原则的对应

| 原则 | 服务决策 |
|---|---|
| 1 自动化 (除 broker) | #1 删 PROMOTE, #2 合并 modal, #6 全表现 |
| 2 简化易用 | #2 合并 modal, #4 去 watchlist 闸门, #5 跳过 S6 |
| 3 交易系统来自 docs | #3 保留 backtest, #7B 双层闸门 (DisciplineChecklistModal 10 项 = invest 地阶功法) |

## 参考

- 原计划: `docs/active/production-readiness-plan.md`
- 现状: `docs/progress/STATUS.md`
- 最新审计: `docs/reports/completed/full-audit-round6-2026-06-11.md`
- DisciplineChecklistModal 实现: `frontend/src/components/DisciplineChecklistModal.tsx`
- plan_runner 闸门代码: `backend/app/services/plan_runner.py:494`
